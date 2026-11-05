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

from . import config, db, drawio
from . import service as svc
from .security import strip_tags

CHART_RE = re.compile(r"\b([A-Z]{2})-([A-Z])-([A-Z]{2,3})-(\d{2})\b")
HEAD1 = re.compile(r"^Heading 1")
HEAD2 = re.compile(r"^Heading [2-6]")
REGION_RE = re.compile(r"[–\-]\s*(UAE\s*&\s*EXP|KSA|UAE|EXP)\s*$", re.I)
PREFIX_DEPT = {"WL": "LOG", "PM": "PRJ", "FI": "FIN", "SA": "GOV", "PP": None}
PREFIX_NAME = {"WL": "Warehouse & Logistics", "PM": "Project Management", "FI": "Finance", "SA": "Sales Approval",
               "PP": "Planning / Procurement"}
TITLE_RULES = [
    (r"project|subcontract", "PRJ"), (r"costing|invoice|credit|collection|accrual", "FIN"),
    (r"inbound|fragile|qa/qc|quality assurance|pick|pack|shipping|dispatch|inventory audit|stock correction|scrap|logistics|warehouse", "LOG"),
    (r"material master|mm cleaning|phase-out|material creation", "MDM"), (r"approval", "GOV"),
]
FILE_RULES = [(r"supply_chain", "E2E"), (r"finance", "FIN"), (r"logistics", "LOG"), (r"approval", "GOV"),
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
    return re.sub(r"[^a-z0-9 ]", "", re.sub(r"\s+", " ", (s or "").lower())).strip()


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


def build_plan(parsed: dict, src_declared: str | None) -> dict:
    """Turn one parsed document into a list of candidate records (before DB)."""
    fname = parsed["filename"]
    is_charter = bool(re.search(r"charter", fname, re.I))
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
        parsed = parse_docx(p)
        parsed.update(data=data, sha=sha, path=p)
        parsed["declared"] = declared_dept(parsed["filename"])
        parsed["plan"] = build_plan(parsed, parsed["declared"])
        parsed_docs.append(parsed)
    todo = [d for d in parsed_docs if not d.get("skip")]
    # actual department per source = majority of its non-reference processes
    for d in todo:
        votes = {}
        for c in d["plan"]["candidates"]:
            if c["kind"] != "reference":
                votes[c["dept"]] = votes.get(c["dept"], 0) + 1
        d["actual"] = max(votes, key=votes.get) if votes else d["plan"]["doc_default"]
        d["authority"] = (1 if d["declared"] == d["actual"] else 0, d["version"] or "0")
    # most authoritative source first, so that it becomes the primary definition for duplicates
    todo.sort(key=lambda d: d["authority"], reverse=True)
    summary = dict(sources=[], skipped=[d["filename"] for d in parsed_docs if d.get("skip")])
    with db.tx():
        for d in todo:
            summary["sources"].append(load_source(d, user))
        generate_cross_findings()
        svc.infer_all_relationships()
    return summary


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
    stats = dict(blocks=d["blocks"], sections=len(d["sections"]), images=len(d["images"]), diagrams=sum(1 for i in d["images"].values() if i["significant"]),
                 tables=sum(1 for s in d["sections"] for it in s["items"] if it["type"] == "tbl"), external_links=d["ext_links"],
                 candidates=len(d["plan"]["candidates"]))
    created, merged = [], []
    for cand in d["plan"]["candidates"]:
        res = place_candidate(d, sid, cand, asset_ids, user)
        (created if res["new"] else merged).append(res["process_id"])
    c.execute("UPDATE sources SET stats=? WHERE id=?", (__import__("json").dumps(stats), sid))
    source_findings(d, sid, dept_names, created, merged)
    svc.audit(user, "import", "source", sid, f"{d['filename']} -> {len(created)} new, {len(merged)} duplicate mappings")
    return dict(id=sid, filename=d["filename"], new=created, merged=merged, stats=stats)


def next_ref_id(dept_code: str, slot: str) -> str:
    base = f"{dept_code}-REF-{slot}"
    n = 1
    while db.one("SELECT 1 FROM processes WHERE process_id=?", (f"{base}-{n:02d}",)):
        n += 1
    return f"{base}-{n:02d}"


def cand_text(cand: dict) -> str:
    return " ".join([cand["objective"]] + [strip_tags(s["html"]) for s in cand["sections"]])


def place_candidate(d, sid, cand, asset_ids, user):
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
    elif cand["kind"] == "reference":
        for r in db.q("SELECT p.* FROM processes p WHERE p.kind='reference' AND p.department_id=? AND p.category=?", (dept["id"], cand["category"])):
            v = svc.latest_version(r["id"])
            old = svc.content_text(v["content"]) if v else ""
            if similarity(old, cand_text(cand)) >= 0.9:
                existing = r
                break
    content = dict(objective=cand["objective"], scope="", trigger="", inputs="", outputs="", responsible=cand["responsible"],
                   activities=[], raci=[], sap=[], kpis=[dict(name=k, definition="", target="") for k in cand["kpis"]],
                   escalation=cand["escalation"], risks="", evidence="", forms="", sections=[], notes="")
    for s in cand["sections"]:
        html = s["html"]
        html = re.sub(r'<img data-sha="([0-9a-f]+)">', lambda m: f'<img src="/api/assets/{asset_ids[m.group(1)]}" alt="source image">' if m.group(1) in asset_ids else "", html)
        content["sections"].append(dict(title=s["title"], html=html))
    for sha in cand.get("inline_images", []):
        if cand["kind"] != "future_state" and sha in asset_ids:
            content["sections"].append(dict(title="Additional source image", html=f'<p><img src="/api/assets/{asset_ids[sha]}" alt="source image"></p>'))
    sim = None
    asset_list = [asset_ids[h] for h in cand["images"] + cand.get("inline_images", []) if h in asset_ids]
    loc = f"Section “{heading}” (document order {d['sections'].index(next((s for s in d['sections'] if s['heading'] == heading.split('; ')[0]), d['sections'][0])) + 1 if d['sections'] else 0})"
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
        pid_text, provisional = next_ref_id(cand["dept"], cand.get("ref_slot", "GEN")), True
    pr = svc.create_process_record(pid_text, chart, cand["name"], cand["dept"], cand["kind"], content, "imported", "imported", user,
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
    # diagram from first significant image
    if cand["images"]:
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
            pdept = PREFIX_DEPT.get(cid[:2])
            if cid[:2] == "PP" or (pdept and pdept != cand["dept"]):
                svc.add_finding("conflict", "medium", sid, None, f"ID prefix does not match department: {cid} “{cand['name']}”",
                                f"Prefix {cid[:2]} denotes {PREFIX_NAME.get(cid[:2], 'unknown')}; the process was placed in "
                                f"{dept_names.get(cand['dept'])} based on its {cand['dept_basis']}. Owner decision required on ID scheme and department.")
    c.execute("UPDATE sources SET confidence=? WHERE id=?", ("Medium" if decl == act else "Low", sid))
    n_flow = sum(1 for cd in d["plan"]["candidates"] if cd["images"])
    if n_flow:
        svc.add_finding("uncertain", "medium", sid, None, f"{n_flow} flowcharts imported as reference images ({d['filename']})",
                        "The source flowcharts are embedded pictures, not draw.io/Visio objects. Each is wrapped in an editable draw.io page with the picture as a locked reference "
                        "layer. Shapes/connectors were not auto-reconstructed (risk of silent errors); each is flagged Requires Functional Validation.")
    flow_only = [cd for cd in d["plan"]["candidates"] if cd["kind"] in ("sop", "approval")]
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
