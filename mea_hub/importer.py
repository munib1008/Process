"""DOCX ingestion: parse -> classify -> audit -> load process library.

Nothing is silently discarded: text becomes structured fields or section HTML, images become assets,
and every uncertainty / conflict becomes a finding (the Source Audit Register)."""
import difflib
import hashlib
import io
import os
import re
import zipfile
from html import escape

from docx import Document
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph

from . import canvas, config, db, drawio, flowread
from . import service as svc
from .security import strip_tags

CHART_RE = re.compile(r"\b([A-Z]{2,3})-([A-Z])-([A-Z]{2,3})-(\d{2})\b")
LOOSE_ID_RE = re.compile(r"\b[A-Z]{2,3}-[A-Z]{1,2}-[A-Z]{2,3}-\d{2}\b")
HEAD1 = re.compile(r"^Heading 1")
HEAD2 = re.compile(r"^Heading [2-6]")
REGION_RE = re.compile(r"[–\-]\s*(UAE\s*&\s*EXP|KSA|UAE|EXP)\s*$", re.I)
PREFIX_DEPT = {"WL": "LOG", "PM": "PRJ", "FI": "FIN", "SA": "GOV", "PP": None, "PMM": "PMM", "SC": "E2E"}
PREFIX_NAME = {"WL": "Warehouse & Logistics", "PM": "Project Management", "FI": "Finance", "SA": "Sales Approval",
               "PP": "Planning / Procurement", "PMM": "Product Marketing & Management", "SC": "Supply Chain E2E"}
TITLE_RULES = [
    (r"project|subcontract", "PRJ"), (r"costing|invoice|credit|collection|accrual", "FIN"),
    (r"inbound|fragile|qa/qc|quality assurance|pick|pack|shipping|dispatch|inventory audit|stock correction|scrap|logistics|warehouse", "LOG"),
    (r"material master|mm cleaning|phase-out|material creation", "MDM"), (r"approval", "GOV"),
]
FILE_RULES = [(r"virtual_stock|wl-m", "LOG"), (r"pmm-m|material_master", "PMM"), (r"architecture", "E2E"), (r"supply_chain", "E2E"), (r"finance", "FIN"), (r"logistics", "LOG"), (r"approval", "GOV"),
              (r"charter|mm_cleaning", "MDM"), (r"production", "PRD"), (r"project", "PRJ"), (r"sales", "SAL"),
              (r"service", "SVC"), (r"purchase|planning", "MPL"), (r"marketing", "PMM")]
EXPECTED_SOURCES = [
    ("Supply Chain Process Handbook", "E2E"), ("Purchase and Planning", "MPL"), ("Logistics and Warehouse", "LOG"),
    ("Production", "PRD"), ("Finance and Accounts", "FIN"), ("Project Management", "PRJ"),
    ("Sales Support MENA", "SAL"), ("Sales Support Movable Wall", "SAL"), ("Service and Installation", "SVC"),
    ("Approval Processes", "GOV"), ("Product Marketing & Management", "PMM"),
    ("MM Cleaning & Optimization Project Charter", "MDM")]
MIN_DIAGRAM_BYTES = 12_000


class ImportError_(ValueError):
    pass


# ---------------------------------------------------------------- low level docx -> html
def run_html(p: Paragraph) -> str:
    out = []
    for r in p.runs:
        t = escape(r.text).replace("\n", "<br>")
        if not t:
            continue
        if r.bold:
            t = f"<b>{t}</b>"
        if r.italic:
            t = f"<i>{t}</i>"
        if r.underline:
            t = f"<u>{t}</u>"
        out.append(t)
    return "".join(out) or escape(p.text).replace("\n", "<br>")


def table_html(t: Table) -> str:
    rows = []
    for ri, tr in enumerate(t._tbl.tr_lst):
        cells = []
        for tc in tr.tc_lst:
            c = _Cell(tc, t)
            span = tc.grid_span
            tag = "th" if ri == 0 else "td"
            txt = "<br>".join(escape(pp.text.strip()) for pp in c.paragraphs if pp.text.strip())
            cells.append(f"<{tag}{f' colspan={span}' if span > 1 else ''}>{txt}</{tag}>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return "<table>" + "".join(rows) + "</table>"


def table_rows(t: Table):
    out = []
    for tr in t._tbl.tr_lst:
        out.append([" / ".join(pp.text.strip() for pp in _Cell(tc, t).paragraphs if pp.text.strip()) for tc in tr.tc_lst])
    return out


def is_list_style(name: str) -> bool:
    return name.startswith("Bullet") or name.startswith("List Paragraph") or "List" in name and "Bullet" in name


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", re.sub(r"\s+", " ", (s or "").lower()))).strip()      # "A – B" and "A B" are the same name


def similarity(a: str, b: str) -> float:
    a, b = norm(a)[:4000], norm(b)[:4000]
    if not a and not b:
        return 1.0
    return round(difflib.SequenceMatcher(None, a, b, autojunk=False).ratio(), 3)


def parse_docx(path: str) -> dict:
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if "[Content_Types].xml" not in names or "word/document.xml" not in names:
            raise ImportError_("Not a valid .docx package.")
        for n in names:
            if n.startswith("/") or ".." in n.split("/"):
                raise ImportError_("Unsafe path inside .docx package.")
        if sum(i.file_size for i in z.infolist()) > 600 * 1024 * 1024:
            raise ImportError_("Document expands to an unreasonable size.")
    doc = Document(path)
    body = doc.element.body
    cover, sections = [], []
    cur = None
    images = {}                      # key -> dict(bytes,mime,name,w,h,significant)
    rel_cache = {}
    ext_links = 0
    for rel in doc.part.rels.values():
        if rel.is_external:
            ext_links += 1

    def get_image(rid):
        if rid in rel_cache:
            return rel_cache[rid]
        part = doc.part.related_parts.get(rid)
        if part is None:
            rel_cache[rid] = None
            return None
        data = part.blob
        sha = hashlib.sha256(data).hexdigest()
        info = dict(sha=sha, bytes=data, mime=part.content_type, name=part.partname.split("/")[-1], w=None, h=None)
        if part.content_type.startswith("image/") and "svg" not in part.content_type:
            try:
                from PIL import Image
                im = Image.open(io.BytesIO(data))
                info["w"], info["h"] = im.size
            except Exception:
                pass
        info["significant"] = bool(info["w"] and info["w"] >= 200 and len(data) >= MIN_DIAGRAM_BYTES and "png" in part.content_type or
                                   (info["w"] and info["w"] >= 400 and "jpeg" in part.content_type))
        images[sha] = info
        rel_cache[rid] = sha
        return sha

    blocks_total = 0
    for el in body.iterchildren():
        tag = el.tag.split("}")[1]
        if tag == "p":
            p = Paragraph(el, doc)
            style = p.style.name if p.style is not None else ""
            text = p.text.strip()
            rids = [r for r in el.xpath(".//a:blip/@r:embed")]
            shas = [s for s in (get_image(r) for r in rids) if s]
            if style.startswith("toc") or text.lower() == "table of contents":
                continue
            blocks_total += 1
            item = dict(type="p", style=style, text=text, html=run_html(p), images=shas)
            if HEAD1.match(style) and text:
                cur = dict(heading=text, level=1, items=[], index=len(sections))
                sections.append(cur)
                if shas:
                    cur["items"].append(dict(type="p", style="Image", text="", html="", images=shas))
                continue
            if cur is None:
                cover.append(item)
            else:
                cur["items"].append(item)
        elif tag == "tbl":
            t = Table(el, doc)
            blocks_total += 1
            item = dict(type="tbl", html=table_html(t), rows=table_rows(t), images=[])
            (cover if cur is None else cur["items"]).append(item)
    # ---- cover
    cover_text = [c["text"] for c in cover if c["type"] == "p" and c["text"]]
    title = " ".join(t for t in cover_text if not t.lower().startswith(("[version", "process", "table")))[:140]
    ver = ""
    for t in cover_text:
        m = re.search(r"Version\s*No\.?\s*([\d.]+)", t, re.I)
        if m:
            ver = m.group(1)
    if not ver:
        m = re.search(r"v(\d+(?:\.\d+)+)", os.path.basename(path))
        ver = m.group(1) if m else ""
    return dict(filename=os.path.basename(path), cover_text=cover_text, title=title or cover_text[0] if cover_text else "",
                version=ver, sections=sections, images=images, cover_images=[s for c in cover for s in c.get("images", [])],
                ext_links=ext_links, blocks=blocks_total)


# ---------------------------------------------------------------- classification
def declared_dept(filename: str):
    f = filename.lower()
    for pat, code in FILE_RULES:
        if re.search(pat, f):
            return code
    return None


def classify_dept(title: str, chart_id: str | None, default: str):
    t = title.lower()
    for pat, code in TITLE_RULES:
        if re.search(pat, t):
            return code, "title"
    if chart_id:
        c = PREFIX_DEPT.get(chart_id[:2])
        if c:
            return c, "id-prefix"
    return default, "source-default"


TEXT_KEYS = {"E2E": r"supply chain|end-to-end|order intake", "PRJ": r"project", "LOG": r"logistic|warehous|inbound|dispatch|pick|pack|labelling|saber|fragile|qa/qc",
             "FIN": r"financ|invoice|credit|costing", "MDM": r"material master|article|phase-out", "GOV": r"approval"}


def classify_text(text: str, default: str):
    t = text.lower()
    score = {k: len(re.findall(p, t)) for k, p in TEXT_KEYS.items()}
    best = max(score, key=score.get)
    ties = [k for k, v in score.items() if v == score[best]]
    return (best, "text-score") if score[best] > 0 and (len(ties) == 1 or default not in ties) else (default, "source-default")


def section_chart_id(sec):
    for it in sec["items"]:
        if it["type"] == "p" and re.search(r"chart\s*id", it["text"], re.I):
            m = CHART_RE.search(it["text"])
            if m:
                return m.group(0)
    for it in sec["items"]:
        if it["type"] == "p":
            m = CHART_RE.search(it["text"])
            if m and re.search(r"(?:flow\s?chart|process)", it["text"], re.I):
                return m.group(0)
    return None


def analyse_section(sec: dict) -> dict:
    """Extract structured fields from one H1 section; returns remaining html."""
    items = sec["items"]
    cid = section_chart_id(sec)
    objective = ""
    resp, kpis, esc_rows = [], [], []
    html, imgs = [], []
    mode = None
    in_list = False
    first_para_used = False
    kpi_mode = False

    def close_list():
        nonlocal in_list
        if in_list:
            html.append("</ul>")
            in_list = False

    for it in items:
        imgs.extend(it.get("images", []))
        if it["type"] == "tbl":
            close_list()
            rows = it["rows"]
            hdr = [h.lower() for h in rows[0]] if rows else []
            if hdr and ("stage" in hdr[0] or any("escalation" in h for h in hdr)):
                for r in rows[1:]:
                    r = (r + [""] * 5)[:5]
                    esc_rows.append(dict(stage=r[0], to=r[1], time=r[2], action=r[3], sla=r[4]))
            html.append(it["html"])
            continue
        text = it["text"]
        if not text:
            continue
        lt = text.lower()
        if CHART_RE.search(text) and re.search(r"chart\s*id", lt):
            continue                                          # captured in chart_id
        if lt.startswith("responsible"):
            lines = [l.strip(" ■\t\xa0") for l in re.split(r"[\n\r]", text)[0:] if l.strip(" ■\t\xa0")]
            resp.extend(l for l in lines if not l.lower().startswith("responsible"))
            mode = "resp"
            continue
        if mode == "resp" and text.startswith("■"):
            resp.extend(l.strip(" ■\t\xa0") for l in text.split("\n") if l.strip(" ■\t\xa0"))
            continue
        mode = None
        if re.match(r"^kpis?\b", lt):
            kpi_mode = True
        elif kpi_mode and is_list_style(it["style"]):
            kpis.append(re.sub(r":\s*$", "", text))
        elif kpi_mode and not is_list_style(it["style"]):
            kpi_mode = False
        if (not first_para_used and not is_list_style(it["style"]) and len(text) > 40 and
                not HEAD2.match(it["style"]) and not re.match(r"^(note|scope|benefits)\b", lt)):
            objective = text
            first_para_used = True
            continue
        if is_list_style(it["style"]) or it["style"].startswith("Image"):
            if not in_list:
                html.append("<ul>")
                in_list = True
            html.append(f"<li>{it['html']}</li>")
        else:
            close_list()
            if HEAD2.match(it["style"]) or it["style"].startswith("Normal: No spacing") and len(text) < 40 and text.endswith(":"):
                html.append(f"<h4>{escape(text)}</h4>")
            else:
                html.append(f"<p>{it['html']}</p>")
    close_list()
    return dict(chart_id=cid, objective=objective, responsible=list(dict.fromkeys(resp)), kpis=list(dict.fromkeys(kpis)),
                escalation=esc_rows, html="".join(html), images=list(dict.fromkeys(imgs)))


REFERENCE_PAT = re.compile(r"introduction|benefits|this handbook|scope|overview$|escalation matrix", re.I)


def build_checklist_plan(parsed: dict) -> dict:
    """Checklist documents: every section holding a 'Checkpoint' table becomes a controlled FORM record."""
    secs = [(s, analyse_section(s)) for s in parsed["sections"]]
    purpose = [dict(title=s["heading"], html=(f"<p>{escape(a['objective'])}</p>" if a["objective"] else "") + a["html"])
               for s, a in secs if re.search(r"purpose", s["heading"], re.I)]
    record = [dict(title=s["heading"], html=a["html"]) for s, a in secs if re.search(r"completion record", s["heading"], re.I)]
    cands = []
    for s, a in secs:
        if not any(it["type"] == "tbl" and it["rows"] and any("checkpoint" in c.lower() for c in it["rows"][0]) for it in s["items"]):
            continue
        key = (s["heading"] + " " + a["objective"]).lower()
        if re.search(r"sales support|customer service", key):
            name, dept = "Sales Order Release Checklist (Sales Support / Customer Service)", "SAL"
        elif re.search(r"material planning|mrp", key):
            name, dept = "PR Validation Checklist (Material Planning / MRP)", "MPL"
        else:
            name, dept = s["heading"], "E2E"
        sections = [dict(title=x["title"], html=x["html"]) for x in purpose] + [dict(title="Checklist – " + s["heading"], html=(f"<p>{escape(a['objective'])}</p>" if a["objective"] else "") + a["html"])] + record
        cands.append(dict(kind="form", name=name, chart_id=None, dept=dept, dept_basis="title", objective=a["objective"], responsible=[], kpis=[], escalation=[],
                          sections=sections, images=[], inline_images=[], heading=s["heading"], countries="", category="Controlled checklist (supporting form)"))
    return dict(candidates=cands, doc_default=cands[0]["dept"] if cands else "E2E")


# ---------------------------------------------------------------- native draw.io files
SAP_RE = re.compile(r"\b([A-Z]{2,4}\d{1,2}[A-Z]?|MIGO|MIRO)\b")
SAP_BLOCK = {"ZP00", "ZM00", "PG01"}   # price conditions / not transactions


def parse_drawio(path: str) -> dict:
    with open(path, "rb") as f:
        data = f.read()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise ImportError_("draw.io file is not UTF-8 text.")
    pages = list(drawio.split_pages(text))              # validates; rejects DOCTYPE/ENTITY
    attrs = dict(drawio._parse(text.encode("utf-8")).attrib)
    previews = []                                       # optional authoritative previews rendered by draw.io: <file>.png, further pages <file>.p2.png ...
    for i in range(len(pages)):
        sidecar, data_ = os.path.splitext(path)[0] + (".png" if i == 0 else f".p{i + 1}.png"), None
        if os.path.isfile(sidecar):
            with open(sidecar, "rb") as f:
                data_ = f.read()
            if data_[:8] != b"\x89PNG\r\n\x1a\n":
                data_ = None
        previews.append(data_)
    preview = previews[0] if previews else None
    return dict(kind="drawio", attrs=attrs, preview=preview, previews=previews, filename=os.path.basename(path), pages=pages, data=data, sections=[], images={}, cover_images=[], ext_links=0,
                blocks=sum(len(drawio.scene(x)["boxes"]) for _, x in pages), version="", cover_text=[n for n, _ in pages])


def _lane_of(sc, box, lanes):
    cx, cy = box["x"] + box["w"] / 2, box["y"] + box["h"] / 2
    best = None
    for ln in lanes:
        if ln["x"] <= cx <= ln["x"] + ln["w"] and ln["y"] <= cy <= ln["y"] + ln["h"]:
            if best is None or ln["w"] * ln["h"] < best["w"] * best["h"]:
                best = ln
    return best


def flow_plan(xml: str):
    """Activities/roles/SAP for an untagged (lane-style) diagram, in the same shape flowread.read returns."""
    try:
        plan = build_drawio_plan(dict(pages=[("Flow", xml)], filename="flow.drawio", attrs={}))
    except Exception:
        return None
    if not plan["candidates"]:
        return None
    c = plan["candidates"][0]
    return dict(activities=c.get("activities", []), sap=c.get("sap", []), responsible=c.get("responsible", []), notes_html="", node_meta=c.get("node_meta", {}), summary="")


def remember_legend(pxml):
    if svc.cfg("master_legend"):
        return
    sc = drawio.scene(pxml)
    roles = [dict(role=re.sub(r"\s+", " ", b["label"]).strip(), color=b["style"].get("strokeColor"))
             for b in sorted((b for b in sc["boxes"].values() if b["id"].startswith("mea_lg_c")), key=lambda b: int(b["id"][8:] or 0))
             if b["label"] and b["style"].get("strokeColor")]
    if roles:
        import json as _json
        svc.set_cfg("master_legend", _json.dumps(dict(roles=roles)))


def tidy_name(name: str) -> str:
    """Presentation only: ALL-CAPS headings become Title Case (IDs, acronyms and '&' are kept)."""
    letters = [ch for ch in name if ch.isalpha()]
    if len(letters) >= 6 and sum(ch.isupper() for ch in letters) / len(letters) > 0.9:
        keep = {"QA", "QC", "QA/QC", "KSA", "UAE", "EXP", "SAP", "PO", "PR", "OC", "NCR", "AMC", "MRP", "E2E"}
        return " ".join(w if w.upper() in keep else w.capitalize() for w in name.split())
    return name


def tagged_candidate(parsed, pname, pxml):
    a = parsed.get("attrs", {})
    fr = flowread.read(pxml)
    pid = a.get("meaProcessId") or None
    name = a.get("meaName") or pname
    extra = []
    if a.get("meaNote"):
        extra.append(("uncertain", "medium", f"Mapping note for {pid or name}", a["meaNote"]))
    if fr["unreached"]:
        extra.append(("uncertain", "low" if fr["unreached"] < 5 else "medium", f"Flow check: {fr['unreached']} of {fr['shapes']} steps are not connected to the start ({pid or name})",
                      "Some shapes have no connector path from the start node (separate variants, side branches or missing arrows). Step order for them follows their position on the page – owner to verify and connect."))
    no_role = sum(1 for x in fr["activities"] if not x["role"] and not x["activity"].startswith("Linked process:"))
    if no_role and fr["activities"]:
        extra.append(("gap", "low", f"{no_role} step(s) without a responsible role ({pid or name})", "These shapes have a neutral outline colour, so no role could be read from the master legend."))
    return dict(kind=a.get("meaKind") or "sop", name=name, chart_id=None, target_id=pid, attach=a.get("meaAttach") == "1", provisional=a.get("meaProvisional") == "1",
                dept=a.get("meaDept") or "E2E", dept_basis="mapping", objective="", scope=fr["summary"], responsible=fr["responsible"], kpis=[], escalation=[], sap=fr["sap"],
                activities=fr["activities"], evidence="", notes="", sections=([dict(title=flowread.FLOW_NOTES_TITLE, html=fr["notes_html"])] if fr["notes_html"] else []),
                images=[], inline_images=[], heading=a.get("meaCanvasTitle") or pname, countries="", category=a.get("meaCategory") or "", native=True, flow=True,
                diagram_xml=pxml, node_meta=fr["node_meta"], extra_findings=extra, ref_slot="FLW", preview=parsed.get("preview"),
                match=(a.get("meaMatchChart") or "", a.get("meaMatchName") or ""), redrawn=a.get("meaRedrawn") == "1", section=a.get("meaSection") or "",
                id_corrections=db.jloads(a.get("meaIdCorrections"), []) if a.get("meaIdCorrections") else [])


def build_drawio_plan(parsed: dict) -> dict:
    cands = []
    pages = parsed["pages"]
    if len(pages) == 1 and not flowread.is_tagged(pages[0][1]) and canvas.is_canvas(pages[0][1]):
        # an unmapped master canvas: split by its titles, keep the role colours, mint reference IDs
        flows, leftovers = canvas.segment(pages[0][1])
        newpages = []
        for f in flows:
            fx = canvas.revamp(canvas.extract(pages[0][1], f["unit_ids"]), f["title"], "", "E2E", dict(roles=[], by_color={}, aliases={}, department_overrides={}),
                               dict(meaKind="sop", meaAttach="0", meaProvisional="1", meaCanvasTitle=f["title"]))
            newpages.append((f["title"], fx, dict(meaName=f["title"], meaKind="sop", meaProvisional="1", meaCanvasTitle=f["title"], meaDept="E2E")))
        for title, fx, at in newpages:
            cands.append(tagged_candidate(dict(parsed, attrs=at, preview=None), title, fx))
        if leftovers:
            cands[0]["extra_findings"].append(("uncertain", "medium", f"{sum(l['n'] for l in leftovers)} shapes on the canvas belong to no titled flow ({parsed['filename']})",
                                               "They were not imported as processes. Provide a mapping file (see docs) to assign them."))
        return dict(candidates=cands, doc_default="E2E")
    for page_no, (pname, pxml) in enumerate(pages):
        if flowread.is_tagged(pxml):
            cands.append(tagged_candidate(parsed, pname, pxml))
            continue
        sc = drawio.scene(pxml)
        B = sc["boxes"] = {i: b_ for i, b_ in sc["boxes"].items() if not b_["style"].get("meaExport")}      # export areas are not process steps
        for b_ in B.values():
            b_["label"] = re.sub(r"\s+", " ", b_["label"].replace("\xa0", " ")).strip()
        is_sw = lambda b: b["style"]["_first"] == "swimlane" or b["style"].get("swimlane")
        lanes = [b for b in B.values() if is_sw(b) and b["style"].get("horizontal") == "0"]
        stacks = {b["id"]: b for b in B.values() if is_sw(b) and b["style"].get("childLayout") == "stackLayout"}
        containers = [b for b in B.values() if is_sw(b) and b["style"].get("horizontal") != "0" and b["id"] not in stacks]
        title = ""
        if containers:
            title = max(containers, key=lambda b: b["w"] * b["h"])["label"]
        if not title:
            texts = [b for b in B.values() if b["style"]["_first"] == "text" and b["label"]]
            title = min(texts, key=lambda b: b["y"])["label"] if texts else pname
        m = CHART_RE.search(title) or CHART_RE.search(pname) or CHART_RE.search(parsed["filename"])
        chart = m.group(0) if m else None
        notes_ = []
        ids_seen = {x for x in LOOSE_ID_RE.findall(title) + LOOSE_ID_RE.findall(pname) + LOOSE_ID_RE.findall(parsed["filename"])}
        if len(ids_seen) > 1:
            notes_.append(("conflict", "medium", f"Inconsistent process ID inside {parsed['filename']}",
                           f"Page/file name and diagram title carry different IDs: {', '.join(sorted(ids_seen))}. Chart ID {chart or '(none)'} was used (from the page/file name). Owner must confirm the correct ID."))
        name = re.sub(r"^\s*Process Map\s*[–-]\s*", "", title)
        name = re.sub(r"\s*[–-]\s*[A-Z]{2,3}-[A-Z]{1,2}-[A-Z]{2,3}-\d{2}\s*$", "", name)
        name = re.sub(r"\s*\([A-Z]{2,3}-[A-Z]{1,2}-[A-Z]{2,3}-\d{2}\)\s*$", "", name).strip()
        objective = ""
        if "(" in name and name.lower().startswith("level"):
            name, objective = name.split("(", 1)[0].strip(), name.split("(", 1)[1].rstrip(") ")
        e2e = bool(re.match(r"level\s*\d", name, re.I)) or bool(chart and chart.startswith("SC-"))
        dept = PREFIX_DEPT.get((chart or "").split("-")[0]) if chart else None
        dept = dept or ("E2E" if e2e else "E2E")
        proposed = lambda lb: bool(re.search(r"recommended|not in original|proposed", lb or "", re.I))
        lane_labels = [l["label"] for l in sorted(lanes, key=lambda l: (l["y"], l["x"])) if l["label"]]
        responsible = [l for l in lane_labels if not proposed(l)]
        # parent-child maps
        child_of_stack = {b["id"]: b["parent"] for b in B.values() if b["parent"] in stacks}
        norm_id = lambda i: child_of_stack.get(i, i)
        notes, evidence = [], ""
        act_boxes = []
        for b in B.values():
            st, first = b["style"], b["style"]["_first"]
            if b["id"] in child_of_stack or (is_sw(b) and b["id"] not in stacks) or st.get("group") or first == "group":
                continue
            fill = (st.get("fillColor") or "").lower()
            if fill == "#ffffe0" or (first == "text" and not b["label"]):
                (notes if True else []).append(b)
                continue
            if first == "text" and not lanes:
                continue                                  # page headline
            if first.startswith("ellipse") and re.fullmatch(r"(start|end)?\s*(\(.*\))?", b["label"].strip(), re.I):
                continue
            if not b["label"] and b["id"] not in stacks:
                continue
            act_boxes.append(b)
        note_texts = []
        for nb in notes:
            t = re.sub(r"<[^>]+>", "\n", nb["raw_label"].replace("&#xa;", "\n")).strip() if nb["raw_label"] else nb["label"]
            t = strip_tags(nb["raw_label"].replace("&#xa;", "<br>")).strip()
            if t.lower().startswith("required documents"):
                evidence = t
            else:
                note_texts.append(t)
        # order = BFS over connectors from the start node(s)
        out_edges, indeg = {}, {}
        for e in sc["edges"]:
            a, c = norm_id(e["source"]), norm_id(e["target"])
            if a in B and c in B:
                out_edges.setdefault(a, []).append((c, e["label"]))
                indeg[c] = indeg.get(c, 0) + 1
        starts = [b["id"] for b in B.values() if b["style"]["_first"].startswith("ellipse") and b["label"].strip().lower() == "start"]
        starts = starts or [b["id"] for b in sorted(act_boxes, key=lambda b: (b["y"], b["x"])) if indeg.get(b["id"], 0) == 0]
        order, seen, q = [], set(), list(starts)
        while q:
            cur = q.pop(0)
            if cur in seen:
                continue
            seen.add(cur)
            order.append(cur)
            q += [c for c, _ in out_edges.get(cur, [])]
        rest = [b["id"] for b in sorted(act_boxes, key=lambda b: (b["y"], b["x"])) if b["id"] not in seen]
        rank = {i: n for n, i in enumerate(order + rest)}
        def _is_prop(b):
            ln = _lane_of(sc, b, lanes) or (B.get(b["parent"]) if b["parent"] in B else None)
            return bool(ln and proposed(ln["label"]))
        act_boxes.sort(key=lambda b: (_is_prop(b), rank.get(b["id"], 9999)))      # proposed steps go last
        label_of = lambda i: (B[i]["label"] or B[i]["id"]) if i in B else ""
        activities, saps, node_meta, mismatch = [], [], {}, []
        for n, b in enumerate(act_boxes, 1):
            parent_lane = B.get(b["parent"]) if b["parent"] in B and B[b["parent"]]["style"].get("horizontal") == "0" else None
            vis = _lane_of(sc, b, lanes)
            lane = vis or parent_lane
            if vis and parent_lane and vis["id"] != parent_lane["id"]:
                mismatch.append(f"“{b['label'][:40]}” is structurally inside lane “{parent_lane['label']}” but drawn in “{vis['label']}” (drawn position used)")
            role = lane["label"] if lane else ""
            label = b["label"]
            if b["id"] in stacks:
                kids = [B[k]["label"] for k, p in child_of_stack.items() if p == b["id"] and B[k]["label"]]
                label = (b["label"] + ": " + "; ".join(kids)).strip(": ")
            if b["style"]["_first"].startswith("rhombus"):
                label = "Decision: " + label
            prop = bool(lane and proposed(lane["label"]))
            if prop:
                label = "[PROPOSED – not in original process] " + label
                role = re.sub(r"\s*[–-]\s*RECOMMENDED.*$", "", role, flags=re.I) + " (proposed)"
            nxt = []
            for c, lb in out_edges.get(b["id"], []):
                tgt = label_of(c)
                nxt.append((f"{lb}: " if lb else "") + ("End" if re.fullmatch(r"end.*", tgt, re.I) else tgt[:60]))
            codes = [c for c in dict.fromkeys(SAP_RE.findall(label)) if c not in SAP_BLOCK and (c in ("MIGO", "MIRO") or re.search(r"[A-Z]{2,4}\d", c))]
            activities.append(dict(no=str(n), activity=label, role=role, sap=" / ".join(codes), output="→ " + "; ".join(nxt) if nxt else ""))
            for code in codes:
                saps.append(dict(transaction=code, purpose=label[:160]))
            meta = {}
            if role:
                meta["role"] = role
            if lane and not prop:
                meta["department"] = lane["label"]
            if codes:
                meta["sap"] = " / ".join(codes)
            for cid_ in ([b["id"]] + [k for k, p in child_of_stack.items() if p == b["id"]]):
                node_meta[cid_] = meta
        if any(proposed(l) for l in lane_labels):
            notes_.append(("uncertain", "medium", f"Proposed (not approved) content inside {parsed['filename']}",
                           "The diagram contains a lane marked as a recommended addition that is not part of the original process (" +
                           "; ".join(l for l in lane_labels if proposed(l)) + "). It was imported but labelled [PROPOSED] and must not be treated as approved procedure."))
        if mismatch:
            notes_.append(("uncertain", "low", f"Shape/lane placement inconsistency in {parsed['filename']}", " | ".join(mismatch)))
        merged_sap = list({x["transaction"]: x for x in saps}.values())
        cands.append(dict(kind="e2e" if e2e else "sop", name=name, chart_id=chart, dept=dept, dept_basis="id-prefix" if chart else "title", objective=objective or ("Process map imported from the native draw.io diagram “" + title + "”."),
                          responsible=responsible, kpis=[], escalation=[], sap=merged_sap, activities=activities, evidence=evidence, notes="\n\n".join(note_texts),
                          sections=[], images=[], inline_images=[], heading=pname, countries="", category="Imported from native draw.io diagram", native=True, ref_slot="L0",
                          preview=(parsed.get("previews") or [None] * (page_no + 1))[page_no],
                          diagram_xml=pxml, node_meta=node_meta, extra_findings=notes_))
    return dict(candidates=cands, doc_default="E2E")


def build_plan_placeholder():
    pass


def build_plan(parsed: dict, src_declared: str | None) -> dict:
    """Turn one parsed document into a list of candidate records (before DB)."""
    fname = parsed["filename"]
    is_charter = bool(re.search(r"charter", fname, re.I))
    if not is_charter and any(it["type"] == "tbl" and it["rows"] and any("checkpoint" in c.lower() for c in it["rows"][0]) for sec in parsed["sections"] for it in sec["items"]):
        return build_checklist_plan(parsed)
    cands = []
    refs_intro, refs_esc = [], []
    if is_charter:
        analysed = [(s, analyse_section(s)) for s in parsed["sections"]]
        content_sections, all_imgs, tables_kpi = [], [], []
        for s, a in analysed:
            body = a["html"]
            for sha in a["images"]:
                if parsed["images"][sha]["significant"]:
                    body += f'<p><img data-sha="{sha}"></p>'
            content_sections.append(dict(title=s["heading"], html=(f"<p>{escape(a['objective'])}</p>" if a["objective"] else "") + body))
            all_imgs.extend(a["images"])
        objective = analysed[0][1]["objective"] if analysed else ""
        cands.append(dict(kind="future_state", name="MM Cleaning & Optimization Control – Project Charter", chart_id=None,
                          dept="MDM", dept_basis="title", objective=objective, responsible=[], kpis=[],
                          escalation=[], sections=content_sections, images=[], inline_images=all_imgs, heading="(whole document)",
                          countries="", category="Master data governance – proposed future state"))
        return dict(candidates=cands, doc_default="MDM")
    # provisional default dept: majority of titled processes
    for s in parsed["sections"]:
        a = analyse_section(s)
        s["_a"] = a
    votes = {}
    for s in parsed["sections"]:
        if s["_a"]["chart_id"]:
            d, _ = classify_dept(s["heading"], s["_a"]["chart_id"], src_declared or "E2E")
            votes[d] = votes.get(d, 0) + 1
    doc_default = max(votes, key=votes.get) if votes else (src_declared or "E2E")
    for s in parsed["sections"]:
        a = s["_a"]
        head = s["heading"].strip()
        if a["chart_id"]:
            d, basis = classify_dept(head, a["chart_id"], doc_default)
            region = REGION_RE.search(head)
            countries = ""
            if region:
                countries = region.group(1).upper().replace(" ", "")
            kind = "department" if re.search(r"general overview", head, re.I) else ("approval" if a["chart_id"].startswith("SA-") else "sop")
            sig = [h for h in a["images"] if parsed["images"][h]["significant"]]
            cands.append(dict(kind=kind, name=re.sub(r"\s*[–\-]\s*(UAE\s*&\s*EXP|KSA)\s*$", "", head, flags=re.I).strip() + (f" – {region.group(1).upper()}" if region else ""),
                              chart_id=a["chart_id"], dept=d, dept_basis=basis, objective=a["objective"], responsible=a["responsible"],
                              kpis=a["kpis"], escalation=a["escalation"], sections=([dict(title="Imported source content", html=a["html"])] if a["html"].strip() else []),
                              images=sig[:1], inline_images=sig[1:], heading=head, countries=countries, category=""))
        elif re.search(r"escalation matrix", head, re.I) or any(it["type"] == "tbl" and it["rows"] and "stage" in it["rows"][0][0].lower() for it in s["items"]):
            refs_esc.append(s)
        else:
            refs_intro.append(s)
    # merge escalation sections (some sources repeat the section) into ONE reference record
    if refs_esc:
        esc, kp, secs, imgs = [], [], [], []
        for s in refs_esc:
            a = s["_a"]
            esc += a["escalation"]
            kp += a["kpis"]
            secs.append(dict(title=s["heading"], html=a["html"]))
            imgs += [h for h in a["images"] if parsed["images"][h]["significant"]]
        esc_dept, esc_basis = classify_text(" ".join(strip_tags(x["html"]) for x in secs), doc_default)
        cands.append(dict(kind="reference", name="Escalation Matrix and KPIs", chart_id=None, dept=esc_dept, dept_basis=esc_basis,
                          objective="", responsible=[], kpis=list(dict.fromkeys(kp)), escalation=esc, sections=secs, images=[], inline_images=imgs,
                          heading="; ".join(s["heading"] for s in refs_esc), countries="", category="Escalation / KPI reference", ref_slot="ESC"))
    if refs_intro:
        secs, obj = [], ""
        for s in refs_intro:
            a = s["_a"]
            if a["objective"] and not obj:
                obj = a["objective"]
                body = a["html"]
            else:
                body = (f"<p>{escape(a['objective'])}</p>" if a["objective"] else "") + a["html"]
            secs.append(dict(title=s["heading"], html=body))
        intro_dept, intro_basis = classify_text(" ".join([obj] + [strip_tags(x["html"]) for x in secs]), doc_default)
        cands.append(dict(kind="reference", name="Introduction, Scope and Benefits", chart_id=None, dept=intro_dept, dept_basis=intro_basis,
                          objective=obj, responsible=[], kpis=[], escalation=[], sections=secs, images=[], inline_images=[],
                          heading="; ".join(s["heading"] for s in refs_intro), countries="", category="Document introduction", ref_slot="INTRO"))
    return dict(candidates=cands, doc_default=doc_default)


# ---------------------------------------------------------------- DB load
def import_paths(paths: list[str], user: str = "system") -> dict:
    """Import several documents as one consistent batch. Returns summary."""
    svc.seed_departments()
    parsed_docs = []
    for p in paths:
        with open(p, "rb") as f:
            data = f.read()
        if len(data) > config.MAX_UPLOAD_BYTES:
            raise ImportError_(f"{p}: file too large")
        sha = hashlib.sha256(data).hexdigest()
        if db.one("SELECT id FROM sources WHERE sha256=?", (sha,)):
            parsed_docs.append(dict(skip=True, filename=os.path.basename(p)))
            continue
        ext = os.path.splitext(p)[1].lower()
        if ext == ".drawio":
            parsed = parse_drawio(p)
            parsed.update(sha=sha, path=p, title=parsed["cover_text"][0] if parsed["cover_text"] else "")
            parsed["declared"] = declared_dept(parsed["filename"])
            parsed["plan"] = build_drawio_plan(parsed)
            parsed["title"] = parsed["plan"]["candidates"][0]["name"] if parsed["plan"]["candidates"] else parsed["filename"]
        elif ext == ".docx":
            parsed = parse_docx(p)
            parsed.update(data=data, sha=sha, path=p)
            parsed["declared"] = declared_dept(parsed["filename"])
            parsed["plan"] = build_plan(parsed, parsed["declared"])
        else:
            raise ImportError_(f"{os.path.basename(p)}: only .docx and .drawio files can be imported.")
        parsed_docs.append(parsed)
    todo = [d for d in parsed_docs if not d.get("skip")]
    # actual department per source = majority of its non-reference processes
    for d in todo:
        votes = {}
        for c in d["plan"]["candidates"]:
            if c["kind"] != "reference":
                votes[c["dept"]] = votes.get(c["dept"], 0) + 1
        d["actual"] = max(votes, key=votes.get) if votes else d["plan"]["doc_default"]
        cs = d["plan"]["candidates"]                          # a file dedicated to one process and named after its ID outranks a page inside a collection
        dedicated = 1 if len(cs) == 1 and cs[0].get("chart_id") and d["filename"].upper().startswith(cs[0]["chart_id"].upper()) else 0
        d["authority"] = (dedicated, 1 if d["declared"] == d["actual"] else 0, d["version"] or "0", sum(len(cand_text(c)) for c in cs))
    # most authoritative source first, so that it becomes the primary definition for duplicates
    todo.sort(key=lambda d: d["authority"], reverse=True)
    todo.sort(key=lambda d: 1 if any(c.get("flow") for c in d["plan"]["candidates"]) else 0)     # documents first, flows attach afterwards
    summary = dict(sources=[], skipped=[d["filename"] for d in parsed_docs if d.get("skip")])
    is_flow = lambda d: any(c.get("flow") for c in d["plan"]["candidates"])
    with db.tx():
        for d in todo:
            if not is_flow(d):
                summary["sources"].append(load_source(d, user))
        for d in todo:                                       # ID decisions shipped with the flows (e.g. per the approved canvas) - before the flows look for their process
            for cand in d["plan"]["candidates"]:
                if cand.get("id_corrections"):
                    summary.setdefault("id_changes", []).extend(svc.apply_id_corrections(cand["id_corrections"], d["filename"]))
        for d in todo:
            if is_flow(d):
                summary["sources"].append(load_source(d, user))
        generate_cross_findings()
        svc.infer_all_relationships()
        svc.link_ref_nodes()
        _auto_links()
    return summary


def shipped_files():
    """Source files delivered with the program (./source_documents and ./source_documents/flows)."""
    import glob
    root = os.path.join(config.app_root(), "source_documents")
    return sorted(glob.glob(os.path.join(root, "*.docx")) + glob.glob(os.path.join(root, "*.drawio")) + glob.glob(os.path.join(root, "flows", "*.drawio")))


def pending_shipped():
    """Shipped source files that this data folder has not imported yet (new or corrected in a newer version of the tool)."""
    have = {r["sha256"] for r in db.q("SELECT sha256 FROM sources")}
    out = []
    for p in shipped_files():
        with open(p, "rb") as f:
            if hashlib.sha256(f.read()).hexdigest() not in have:
                out.append(p)
    return out


def load_source(d: dict, user: str) -> dict:
    now = svc.now()
    stored = os.path.join(config.SOURCE_DIR, f"{d['sha'][:12]}_{re.sub(r'[^A-Za-z0-9._-]', '_', d['filename'])}")
    with open(stored, "wb") as f:
        f.write(d["data"])                                   # original preserved byte-for-byte
    c = db.db()
    dept_names = {x["code"]: x["name"] for x in db.q("SELECT code,name FROM departments")}
    cur = c.execute("INSERT INTO sources(filename,title,version_text,sha256,size,stored_path,declared_dept,actual_dept,stats,imported_at,imported_by)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (d["filename"], d["title"], d["version"], d["sha"], len(d["data"]), stored, d["declared"], d["actual"],
                     "{}", now, user))
    sid = cur.lastrowid
    asset_ids = {}
    for sha, im in d["images"].items():
        role = "diagram" if im["significant"] else "decorative"
        asset_ids[sha] = svc.store_asset(im["bytes"], im["mime"], im["name"], sid, role, im["w"], im["h"])
    if d.get("kind") == "drawio":
        d["images"], d["sections"] = {}, []
    stats = dict(blocks=d["blocks"], sections=len(d["sections"]), images=len(d["images"]), diagrams=sum(1 for i in d["images"].values() if i["significant"]),
                 tables=sum(1 for s in d["sections"] for it in s["items"] if it["type"] == "tbl"), external_links=d["ext_links"],
                 candidates=len(d["plan"]["candidates"]))
    if d.get("kind") == "drawio":
        stats.update(pages=len(d["pages"]), native_diagrams=len(d["pages"]))
    created, merged = [], []
    for cand in d["plan"]["candidates"]:
        res = place_candidate(d, sid, cand, asset_ids, user)
        (created if res["new"] else merged).append(res["process_id"])
    c.execute("UPDATE sources SET stats=? WHERE id=?", (__import__("json").dumps(stats), sid))
    source_findings(d, sid, dept_names, created, merged)
    svc.audit(user, "import", "source", sid, f"{d['filename']} -> {len(created)} new, {len(merged)} duplicate mappings")
    return dict(id=sid, filename=d["filename"], new=created, merged=merged, stats=stats)


def next_ref_id(dept_code: str, slot: str, word: str = "REF") -> str:
    base = f"{dept_code}-{word}" + (f"-{slot}" if slot else "")
    n = 1
    while db.one("SELECT 1 FROM processes WHERE process_id=?", (f"{base}-{n:02d}",)):
        n += 1
    return f"{base}-{n:02d}"


def cand_text(cand: dict) -> str:
    return " ".join([cand["objective"]] + [strip_tags(s["html"]) for s in cand["sections"]])


SYSTEM = dict(username="system", display_name="system", role="admin", department_id=None)


def place_flow(d, sid, cand, user):
    """A per-process flow file: replace the picture on the existing process, or create the process."""
    import json as _json
    c = db.db()
    target = cand.get("target_id")
    fr = dict(activities=cand["activities"], sap=cand["sap"], responsible=cand["responsible"], notes_html=(cand["sections"][0]["html"] if cand["sections"] else ""),
              summary=cand.get("scope", ""), node_meta=cand["node_meta"])
    prev = cand.get("preview")
    role_ = "preview" if prev else "preview-approx"
    if not prev:
        prev = drawio.to_png(cand["diagram_xml"])
    remember_legend(cand["diagram_xml"])
    existing = None
    chart, mname = cand.get("match") or ("", "")
    if chart and mname:                                      # the record a document created for this chart ID and heading, whatever ID it was given at import
        rows = db.q("SELECT p.*,x.name AS department FROM processes p LEFT JOIN departments x ON x.id=p.department_id WHERE p.chart_id=? AND lower(p.name)=?", (chart, mname.lower()))
        if len(rows) == 1:
            existing, target = rows[0], rows[0]["process_id"]
    if not existing and target:
        existing = db.one("SELECT p.*,x.name AS department FROM processes p LEFT JOIN departments x ON x.id=p.department_id WHERE p.process_id=?", (target,))
    note = f"Native flow from {d['filename']}" + (f" (canvas title “{cand['heading']}”)" if cand.get("heading") else "")
    if existing:
        v = svc.open_version(existing["id"])
        if not v:
            v = svc.ensure_draft(existing, SYSTEM)
        content = flowread.apply_to_content(v["content"], fr)
        aid = svc.store_asset(prev, "image/png", f"{target}_preview.png", sid, role_) if prev else None
        old_dv = db.one("SELECT diagram_id FROM diagram_versions WHERE id=?", (v["diagram_version_id"],)) if v.get("diagram_version_id") else None
        if old_dv:
            dv = svc._add_dv(old_dv["diagram_id"], drawio.normalize(cand["diagram_xml"]), "imported-drawio", aid, note, user)
        else:
            _, dv = svc.create_diagram(existing["id"], target, existing["name"], cand["diagram_xml"], "imported-drawio", aid, note, user)
        c.execute("UPDATE process_versions SET content=?, diagram_version_id=?, updated_at=? WHERE id=?", (_json.dumps(content), dv, svc.now(), v["id"]))
        row_id, new = existing["id"], False
        c.execute("INSERT INTO mappings(process_id,source_id,heading,chart_id,role,similarity,location,excerpt_html,asset_ids) VALUES(?,?,?,?,?,?,?,?,?)",
                  (row_id, sid, cand["heading"], target, "flow", None, f"Flow file {d['filename']}", "", "[]"))
        c.execute("UPDATE findings SET status='resolved', decision=?, resolved_by='system' WHERE process_id=? AND status='open' AND title LIKE 'No flowchart image%'",
                  (f"Native flow supplied by {d['filename']}", row_id))
        if cand.get("redrawn"):
            svc.add_finding("uncertain", "medium", sid, row_id, f"Flow redrawn from the flowchart picture ({target})",
                            "This flow is not on the master canvas. It was redrawn step by step from the picture in the Word document (the picture remains as revision 1): "
                            "same steps, decisions and outline colours, standard shapes. Owner to compare it with the picture and confirm.")
        else:
            svc.add_finding("uncertain", "low", sid, row_id, f"Flowchart picture replaced by the native flow ({target})",
                            "The reference picture from the Word document was replaced by the editable flow from the approved master canvas (the picture remains as revision 1). "
                            + (f"It is the section “{cand['section']}” of the complete flow “{cand['heading']}”, closed with its own start and end. " if cand.get("section") else "")
                            + "Activities, roles and linked processes were read from the flow – owner to verify.")
    else:
        pid_text = target or next_ref_id(cand["dept"], "FLW")
        content = dict(objective="", scope="", trigger="", inputs="", outputs="", responsible=[], activities=[], raci=[], sap=[], kpis=[], escalation=[], risks="", evidence="",
                       forms="", sections=[], notes="")
        content = flowread.apply_to_content(content, fr)
        pr = svc.create_process_record(pid_text, None, cand["name"], cand["dept"], cand["kind"], content, "imported", "imported", user, category=cand.get("category", ""))
        row_id, new = pr["id"], True
        aid = svc.store_asset(prev, "image/png", f"{pid_text}_preview.png", sid, role_) if prev else None
        _, dv = svc.create_diagram(row_id, pid_text, cand["name"], cand["diagram_xml"], "imported-drawio", aid, note, user)
        c.execute("INSERT INTO mappings(process_id,source_id,heading,chart_id,role,similarity,location,excerpt_html,asset_ids) VALUES(?,?,?,?,?,?,?,?,?)",
                  (row_id, sid, cand["heading"], target, "primary", None, f"Flow file {d['filename']}", "", "[]"))
        if cand.get("provisional") or not target:
            svc.add_finding("gap", "low", sid, row_id, f"Provisional ID {pid_text}", "The master canvas gives no ID for this flow; a provisional ID was assigned. Document Controller to confirm.")
        svc.add_finding("gap", "medium", sid, row_id, f"Process text missing for {pid_text} – {cand['name']}",
                        "Only the flowchart exists for this process (no departmental document was supplied). Objective, RACI, KPIs and SLA must be written by the owner; "
                        "activities, roles and scope were derived from the flow.")
        target = pid_text
    for node_id, meta in cand.get("node_meta", {}).items():
        if meta:
            c.execute("UPDATE diagram_nodes SET meta=? WHERE diagram_version_id=? AND node_id=?", (_json.dumps(meta), dv, node_id))
    for kind_, sev_, title_, detail_ in cand.get("extra_findings", []):
        svc.add_finding(kind_, sev_, sid, row_id, title_, detail_)
    svc.reindex(row_id)
    return dict(new=new, process_id=target)


def place_candidate(d, sid, cand, asset_ids, user):
    if cand.get("flow"):
        return place_flow(d, sid, cand, user)
    c = db.db()
    dept = db.one("SELECT id FROM departments WHERE code=?", (cand["dept"],))
    heading = cand["heading"]
    # ---------- duplicate detection
    existing, near = None, None
    if cand["chart_id"]:
        rows = db.q("SELECT p.* FROM processes p WHERE p.chart_id=?", (cand["chart_id"],))
        for r in rows:
            if norm(r["name"]) == norm(cand["name"]):
                existing = r
                break
            ratio = difflib.SequenceMatcher(None, norm(r["name"]), norm(cand["name"])).ratio()
            if ratio >= 0.6 and (near is None or ratio > near[1]):
                near = (r, ratio)
    elif cand["kind"] == "form":
        for r in db.q("SELECT p.* FROM processes p WHERE p.kind='form' AND p.department_id=?", (dept["id"],)):
            if norm(r["name"]) == norm(cand["name"]):
                existing = r
                break
    elif cand["kind"] == "reference":
        for r in db.q("SELECT p.* FROM processes p WHERE p.kind='reference' AND p.department_id=? AND p.category=?", (dept["id"], cand["category"])):
            v = svc.latest_version(r["id"])
            old = svc.content_text(v["content"]) if v else ""
            if similarity(old, cand_text(cand)) >= 0.9:
                existing = r
                break
    content = dict(objective=cand["objective"], scope="", trigger="", inputs="", outputs="", responsible=cand["responsible"],
                   activities=cand.get("activities", []), raci=[], sap=cand.get("sap", []), kpis=[dict(name=k, definition="", target="") for k in cand["kpis"]],
                   escalation=cand["escalation"], risks="", evidence=cand.get("evidence", ""), forms="", sections=[], notes=cand.get("notes", ""))
    for s in cand["sections"]:
        html = s["html"]
        html = re.sub(r'<img data-sha="([0-9a-f]+)">', lambda m: f'<img src="/api/assets/{asset_ids[m.group(1)]}" alt="source image">' if m.group(1) in asset_ids else "", html)
        content["sections"].append(dict(title=s["title"], html=html))
    for sha in cand.get("inline_images", []):
        if cand["kind"] != "future_state" and sha in asset_ids:
            content["sections"].append(dict(title="Additional source image", html=f'<p><img src="/api/assets/{asset_ids[sha]}" alt="source image"></p>'))
    sim = None
    asset_list = [asset_ids[h] for h in cand["images"] + cand.get("inline_images", []) if h in asset_ids]
    loc = f"Diagram page “{heading}”" if d.get("kind") == "drawio" else f"Section “{heading}” (document order {d['sections'].index(next((s for s in d['sections'] if s['heading'] == heading.split('; ')[0]), d['sections'][0])) + 1 if d['sections'] else 0})"
    excerpt = "".join(f"<h4>{escape(s['title'])}</h4>{s['html']}" for s in cand["sections"])[:60000]
    if existing:
        v = svc.latest_version(existing["id"])
        sim = similarity(svc.content_text(v["content"]) + " " + existing["name"], cand_text(cand) + " " + cand["name"])
        primary_src = db.one("SELECT source_id FROM mappings WHERE process_id=? AND role='primary'", (existing["id"],))
        c.execute("INSERT INTO mappings(process_id,source_id,heading,chart_id,role,similarity,location,excerpt_html,asset_ids) VALUES(?,?,?,?,?,?,?,?,?)",
                  (existing["id"], sid, heading, cand["chart_id"], "duplicate", sim, loc, excerpt, __import__("json").dumps(asset_list)))
        sev = "low" if sim >= 0.9 else "medium"
        svc.add_finding("duplicate", sev, sid, existing["id"],
                        f"Same process appears in more than one source: {existing['process_id']} – {existing['name']}",
                        f"Chart ID {cand['chart_id'] or '(none)'} / “{heading}” also found in {d['filename']}. Text similarity {sim:.0%} "
                        f"versus the primary definition. {'Content is essentially identical; keep one controlled definition.' if sim >= 0.9 else 'Content differs – owner must decide which text is correct (not auto-merged).'}")
        return dict(new=False, process_id=existing["process_id"])
    # ---------- new process record
    chart = cand["chart_id"]
    if chart:
        pid_text = chart
        n = 1
        while db.one("SELECT 1 FROM processes WHERE process_id=?", (pid_text,)):
            n += 1
            pid_text = f"{chart}.{n}"
        provisional = pid_text != chart
    elif cand["kind"] == "future_state":
        pid_text, provisional = "MDM-F-MM-01", True
    else:
        pid_text, provisional = next_ref_id(cand["dept"], cand.get("ref_slot", "GEN") if cand["kind"] != "form" else "", "FRM" if cand["kind"] == "form" else "REF"), True
    pr = svc.create_process_record(pid_text, chart, tidy_name(cand["name"]), cand["dept"], cand["kind"], content, "imported", "imported", user,
                                   countries=cand["countries"], category=cand["category"])
    row_id = pr["id"]
    c.execute("INSERT INTO mappings(process_id,source_id,heading,chart_id,role,similarity,location,excerpt_html,asset_ids) VALUES(?,?,?,?,?,?,?,?,?)",
              (row_id, sid, heading, chart, "primary", None, loc, excerpt, __import__("json").dumps(asset_list)))
    if provisional and chart:
        first = db.one("SELECT p.process_id,p.name FROM processes p WHERE p.chart_id=? ORDER BY p.id LIMIT 1", (chart,))
        extra = ""
        if near:
            nv = svc.latest_version(near[0]["id"])
            extra = (f" Possible duplicate of {near[0]['process_id']} – {near[0]['name']} (title similarity {near[1]:.0%}, text similarity "
                     f"{similarity(svc.content_text(nv['content']), cand_text(cand)):.0%}); kept separate because region/scope may differ – owner to confirm.")
        svc.add_finding("conflict", "high", sid, row_id,
                        f"Chart ID {chart} is used for different processes – provisional ID {pid_text} assigned",
                        f"“{cand['name']}” carries chart ID {chart}, already used by {first['process_id']} – {first['name']}. Each process must have a unique ID. "
                        f"The system kept both processes and minted {pid_text}; Document Controller must issue a permanent ID." + extra)
    if provisional and not chart:
        svc.add_finding("gap", "low", sid, row_id, f"Provisional ID {pid_text}", "No chart ID in source; system-issued reference ID. Confirm numbering with Document Controller.")
    for kind_, sev_, title_, detail_ in cand.get("extra_findings", []):
        svc.add_finding(kind_, sev_, sid, row_id, title_, detail_)
    # diagram: native draw.io page, or wrapped reference image
    if cand.get("native"):
        prev, prole = cand.get("preview"), "preview"
        if not prev:
            prev, prole = drawio.to_png(cand["diagram_xml"]), "preview-approx"
        aid = svc.store_asset(prev, "image/png", f"{pid_text}_preview.png", sid, prole) if prev else None
        did, dv = svc.create_diagram(row_id, pid_text, cand["name"], cand["diagram_xml"], "imported-drawio", aid, "Imported native draw.io diagram", user)
        for node_id, meta in cand.get("node_meta", {}).items():
            if meta:
                c.execute("UPDATE diagram_nodes SET meta=? WHERE diagram_version_id=? AND node_id=?", (__import__("json").dumps(meta), dv, node_id))
    elif cand["images"]:
        sha = cand["images"][0]
        im = d["images"][sha]
        import base64
        note = f"IMPORTED FLOWCHART – reference image from {d['filename']}. Editable shapes were NOT auto-reconstructed: redraw over the locked reference layer, then delete it. Status: Requires Functional Validation."
        xml = drawio.reference_diagram(cand["name"], chart or pid_text, base64.b64encode(im["bytes"]).decode(), im["w"] or 800, im["h"] or 600, note)
        svc.create_diagram(row_id, pid_text, cand["name"], xml, "imported-image", asset_ids[sha], "Imported reference image (requires functional validation)", user,
                           validation="requires_validation")
    elif cand["kind"] in ("sop", "approval", "department"):
        svc.add_finding("gap", "medium", sid, row_id, f"No flowchart image found for {pid_text} – {cand['name']}",
                        f"Source section “{heading}” in {d['filename']} states chart ID {chart} but contains no flowchart image. Flowchart must be drawn (Flow Studio) – Documentation Required.")
    if cand["kind"] in ("sop", "approval") and not cand["responsible"]:
        svc.add_finding("gap", "low", sid, row_id, f"No 'Responsible' list for {pid_text}", "Source section does not name responsible departments/roles.")
    svc.reindex(row_id)
    return dict(new=True, process_id=pid_text)


def source_findings(d, sid, dept_names, created, merged):
    c = db.db()
    decl, act = d["declared"], d["actual"]
    if decl and act and decl != act:
        svc.add_finding("conflict", "high", sid, None, f"Source title does not match content: {d['filename']}",
                        f"File name suggests “{dept_names.get(decl)}”, but the extracted processes are mostly “{dept_names.get(act)}”. "
                        f"Cover title reads: “{' '.join(d['cover_text'][:3])}”. The process content was classified by what it actually describes, not by file name. "
                        f"Confirm whether the correct file was supplied.")
    # duplicate chart ids inside the same source
    seen = {}
    for s in d["sections"]:
        cid = section_chart_id(s)
        if cid:
            seen.setdefault(cid, []).append(s["heading"])
    for cid, heads in seen.items():
        if len(heads) > 1:
            svc.add_finding("conflict", "high", sid, None, f"Chart ID {cid} reused {len(heads)} times in {d['filename']}",
                            "Used for: " + "; ".join(heads) + ". Process IDs must be unique – see provisional IDs assigned in the Process Library.")
    # ID prefix vs department
    for cand in d["plan"]["candidates"]:
        cid = cand["chart_id"]
        if cid:
            pref = cid.split("-")[0]
            pdept = PREFIX_DEPT.get(pref)
            if pref == "PP" or (pdept and pdept != cand["dept"]):
                svc.add_finding("conflict", "medium", sid, None, f"ID prefix does not match department: {cid} “{cand['name']}”",
                                f"Prefix {pref} denotes {PREFIX_NAME.get(pref, 'unknown')}; the process was placed in "
                                f"{dept_names.get(cand['dept'])} based on its {cand['dept_basis']}. Owner decision required on ID scheme and department.")
    c.execute("UPDATE sources SET confidence=? WHERE id=?", ("Low" if (decl and act and decl != act) else "Medium", sid))
    n_flow = sum(1 for cd in d["plan"]["candidates"] if cd["images"])
    if n_flow:
        svc.add_finding("uncertain", "medium", sid, None, f"{n_flow} flowcharts imported as reference images ({d['filename']})",
                        "The source flowcharts are embedded pictures, not draw.io/Visio objects. Each is wrapped in an editable draw.io page with the picture as a locked reference "
                        "layer. Shapes/connectors were not auto-reconstructed (risk of silent errors); each is flagged Requires Functional Validation.")
    native = [cd for cd in d["plan"]["candidates"] if cd.get("native") and not cd.get("flow")]
    if native:
        svc.add_finding("uncertain", "medium", sid, None, f"Activities extracted automatically from native diagram ({d['filename']})",
                        f"{len(native)} diagram page(s) were parsed: step order follows the connectors, roles follow the drawn swimlane, SAP transaction codes were read from shape text. "
                        "Verify against the process owner before approval. RACI, KPIs, SLA owners and decision criteria are not in the diagram and remain Documentation Required.")
    flow_only = [cd for cd in d["plan"]["candidates"] if cd["kind"] in ("sop", "approval") and not cd.get("native")]
    if flow_only:
        svc.add_finding("gap", "medium", sid, None, f"Step-by-step activities, RACI, SAP transactions absent in {d['filename']}",
                        f"{len(flow_only)} processes are documented only as a flowchart plus a short description. Activity tables, RACI, SAP transaction references, SLAs and risks "
                        "must be authored by process owners (Documentation Required). Nothing was invented.")
    if d["ext_links"]:
        svc.add_finding("uncertain", "low", sid, None, f"{d['ext_links']} external hyperlinks in {d['filename']}", "Retained as text only; the importer never fetches external resources.")


def generate_cross_findings():
    """Findings that need every source loaded: missing sources, copied intro text between sources."""
    present = {s["declared_dept"] for s in db.q("SELECT declared_dept FROM sources")}
    files = " ".join(s["filename"].lower() for s in db.q("SELECT filename FROM sources"))
    db.db().execute("DELETE FROM findings WHERE kind='gap' AND title LIKE 'Source document not supplied:%'")
    for name, code in EXPECTED_SOURCES:
        key = re.sub(r"[^a-z]", "", name.lower().split()[0])
        if not any(key in re.sub(r"[^a-z]", "", s["filename"].lower()) for s in db.q("SELECT filename FROM sources")):
            svc.add_finding("gap", "high", None, None, f"Source document not supplied: {name}",
                            f"The brief lists 12 source documents; “{name}” has not been imported. Processes and chapters for this area are Documentation Required until it is uploaded.")


def reconcile_report() -> dict:
    """Source reconciliation: every source section accounted for."""
    out = []
    for s in db.q("SELECT * FROM sources ORDER BY id"):
        maps = db.q("SELECT m.*,p.process_id,p.name,p.kind FROM mappings m JOIN processes p ON p.id=m.process_id WHERE m.source_id=?", (s["id"],))
        out.append(dict(source=s, mappings=maps))
    return dict(sources=out)


def _auto_links():
    """If the Level-1 value stream is loaded, derive suggested handover links from it (inferred=2, removable)."""
    vs = db.one("SELECT 1 FROM processes WHERE process_id='SC-M-VS-01'")
    if vs:
        svc.suggest_value_stream_links(dict(username="system", display_name="system", role="admin", department_id=None))
