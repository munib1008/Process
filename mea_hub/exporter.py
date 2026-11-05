"""Server-side exports (DOCX / PDF / HTML / ZIP of .drawio) generated from one consistent snapshot."""
import base64
import datetime as dt
import hashlib
import html as htmllib
import io
import json
import os
import re
import zipfile
from html.parser import HTMLParser

from . import config, db, drawio, service as svc
from .db import jloads, one, q
from .security import strip_tags

# ------------------------------------------------------------------ snapshot
def build_snapshot(user, scope: str, ids=None, dept=None, include_unapproved=True, version_id=None):
    staff = svc.can(user, "view_all")
    if include_unapproved and not svc.can(user, "export_draft"):
        include_unapproved = False
    c = db.db()
    c.execute("BEGIN")                                    # one read transaction = one consistent revision set
    try:
        if scope == "handbook":
            procs = q("SELECT p.* FROM processes p LEFT JOIN departments d ON d.id=p.department_id ORDER BY d.sort,p.sort_order,p.id")
        elif scope == "department":
            d = one("SELECT * FROM departments WHERE code=?", (dept,))
            if not d:
                raise svc.NotFound("Department not found")
            procs = q("SELECT * FROM processes WHERE department_id=? ORDER BY sort_order,id", (d["id"],))
        elif scope in ("process", "selected"):
            if not ids:
                raise svc.Invalid("No processes selected.")
            procs = [svc.get_process(i) for i in ids]
        else:
            raise svc.Invalid("Unknown export scope.")
        depts = {d["id"]: d for d in q("SELECT * FROM departments")}
        items = []
        for p in procs:
            if version_id and scope == "process":
                v = svc.get_version(int(version_id))
                if v["process_id"] != p["id"]:
                    raise svc.Invalid("Version does not belong to the process.")
                if v["status"] not in ("published", "superseded") and not svc.can(user, "export_draft", p):
                    raise svc.Forbidden("You may not export a draft revision.")
            else:
                v = svc.published_version(p["id"])
                if not v and include_unapproved:
                    v = svc.latest_version(p["id"])
                elif v and include_unapproved and scope == "process":
                    lv = svc.latest_version(p["id"])
                    v = lv
            if not v:
                continue
            if not staff and v["status"] not in ("published", "superseded"):
                continue
            item = dict(process_id=p["process_id"], chart_id=p["chart_id"], name=p["name"], kind=p["kind"], dept_id=p["department_id"],
                        owner=p["owner"], reviewer=p["reviewer"], countries=p["countries"], category=p["category"],
                        version=v["version"], version_id=v["id"], status=v["status"], status_label=svc.STATUS_LABEL[v["status"]],
                        reviewed_by=v["reviewed_by"], approved_by=v["approved_by"], approved_at=v["approved_at"], published_at=v["published_at"],
                        change_summary=v["change_summary"], author=v["author"], content=v["content"], diagram=None)
            if v.get("diagram_version_id"):
                dv = one("SELECT dv.*,d.code FROM diagram_versions dv JOIN diagrams d ON d.id=dv.diagram_id WHERE dv.id=?", (v["diagram_version_id"],))
                png = None
                if dv["preview_asset_id"]:
                    try:
                        png = svc.asset_bytes(dv["preview_asset_id"])[1]
                    except svc.NotFound:
                        png = None
                item["diagram"] = dict(code=dv["code"], ver_no=dv["ver_no"], xml=dv["xml"], png=png, validation=dv["validation"], sha=dv["sha256"])
            item["sources"] = q("SELECT s.filename,s.version_text,m.heading,m.role FROM mappings m JOIN sources s ON s.id=m.source_id WHERE m.process_id=? ORDER BY m.id", (p["id"],))
            item["relations"] = q("SELECT r.rel_type,p2.process_id,p2.name,'out' dir FROM relationships r JOIN processes p2 ON p2.id=r.to_id WHERE r.from_id=?", (p["id"],))
            items.append(item)
        asset_cache = {}
        c.execute("COMMIT")
    except BaseException:
        c.execute("ROLLBACK")
        raise
    grouped = []
    for d in sorted({i["dept_id"] for i in items}, key=lambda x: depts[x]["sort"] if x in depts else 99):
        grouped.append(dict(name=depts[d]["name"] if d in depts else "Unassigned", code=depts[d]["code"] if d in depts else "", processes=[i for i in items if i["dept_id"] == d]))
    unapproved = sum(1 for i in items if i["status"] not in ("published", "superseded"))
    title = {"handbook": "MEA Integrated Process Handbook", "department": f"{grouped[0]['name']} – Process Manual" if grouped else "Department Manual",
             "process": f"{items[0]['process_id']} – {items[0]['name']}" if items else "Process", "selected": "Selected Processes"}[scope]
    snap = dict(org=svc.cfg("org_name", "dormakaba MEA"), footer=svc.cfg("export_footer", ""), title=title, scope=scope, generated_by=user["username"],
                generated_at=svc.now(), departments=grouped, count=len(items), unapproved=unapproved,
                versions={i["process_id"]: i["version_id"] for i in items}, user_display=user["display_name"])
    snap["hash"] = hashlib.sha256(json.dumps(
        dict(v=snap["versions"], d={i["process_id"]: (i["diagram"] or {}).get("sha") for g in grouped for i in g["processes"]}), sort_keys=True).encode()).hexdigest()[:16]
    return snap


def asset_png(url):
    m = re.fullmatch(r"/api/assets/(\d+)", url or "")
    if not m:
        return None
    try:
        mime, data = svc.asset_bytes(int(m.group(1)))
        return data if mime in ("image/png", "image/jpeg") else None
    except svc.NotFound:
        return None


def diagram_image(diagram):
    """PNG bytes for a diagram: editor/imported preview, else the shared server-side renderer."""
    if not diagram:
        return None
    if diagram["png"]:
        return diagram["png"]
    try:
        return drawio.to_png(diagram["xml"])
    except Exception:
        return None


# ------------------------------------------------------------------ html -> blocks
class _Blocks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks, self.runs, self.fmt, self.lists = [], [], {"b": 0, "i": 0, "u": 0}, []
        self.table, self.row, self.cell, self.href, self.heading = None, None, None, None, None

    def flush(self, kind="p", level=0):
        runs = [r for r in self.runs]
        self.runs = []
        if not any(r[0].strip() for r in runs):
            return
        if self.cell is not None:
            self.cell.append(runs)
            return
        self.blocks.append(dict(t=kind, runs=runs, level=level))

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("b", "strong"): self.fmt["b"] += 1
        elif tag in ("i", "em"): self.fmt["i"] += 1
        elif tag == "u": self.fmt["u"] += 1
        elif tag == "a": self.href = a.get("href")
        elif tag in ("ul", "ol"): self.flush(); self.lists.append(tag)
        elif tag == "li": self.flush()
        elif tag in ("p", "div", "blockquote"): self.flush()
        elif tag == "br": self.runs.append(("\n", 0, 0, 0, None))
        elif tag in ("h3", "h4", "h5", "h6"): self.flush(); self.heading = tag
        elif tag == "table": self.flush(); self.table = []
        elif tag == "tr": self.row = []
        elif tag in ("td", "th"): self.cell = []; self.cell_attr = (tag == "th", int(a.get("colspan", "1") if str(a.get("colspan", "1")).isdigit() else 1))
        elif tag == "img": self.blocks.append(dict(t="img", src=a.get("src", "")))

    def handle_endtag(self, tag):
        if tag in ("b", "strong"): self.fmt["b"] = max(0, self.fmt["b"] - 1)
        elif tag in ("i", "em"): self.fmt["i"] = max(0, self.fmt["i"] - 1)
        elif tag == "u": self.fmt["u"] = max(0, self.fmt["u"] - 1)
        elif tag == "a": self.href = None
        elif tag in ("ul", "ol"):
            self.flush("li", len(self.lists))
            if self.lists: self.lists.pop()
        elif tag == "li": self.flush("li", max(1, len(self.lists)))
        elif tag in ("p", "div", "blockquote"): self.flush()
        elif tag in ("h3", "h4", "h5", "h6"): self.flush("h", int(tag[1])); self.heading = None
        elif tag in ("td", "th"):
            self.flush()
            cell = self.cell or []
            self.cell = None
            if self.row is not None:
                self.row.append(dict(head=self.cell_attr[0], span=self.cell_attr[1], paras=cell))
        elif tag == "tr":
            if self.table is not None and self.row is not None: self.table.append(self.row)
            self.row = None
        elif tag == "table":
            if self.table: self.blocks.append(dict(t="table", rows=self.table))
            self.table = None

    def handle_data(self, data):
        if data.strip() or (self.runs and data):
            self.runs.append((re.sub(r"\s+", " ", data), self.fmt["b"] > 0, self.fmt["i"] > 0, self.fmt["u"] > 0, self.href))

    def close(self):
        super().close()
        self.flush()


def html_blocks(html: str):
    p = _Blocks()
    p.feed(html or "")
    p.close()
    return p.blocks


# ------------------------------------------------------------------ DOCX
def build_docx(snap) -> bytes:
    from docx import Document
    from docx.enum.section import WD_ORIENT
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_BREAK, WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor

    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(2)
    sec.top_margin, sec.bottom_margin = Cm(2.2), Cm(2)
    st = doc.styles
    st["Normal"].font.name = "Calibri"
    st["Normal"].font.size = Pt(10.5)
    for name, size in (("Heading 1", 18), ("Heading 2", 14), ("Heading 3", 12)):
        st[name].font.name = "Calibri"
        st[name].font.size = Pt(size)
        st[name].font.color.rgb = RGBColor(0x1F, 0x4E, 0x79)
    BLUE = "1F4E79"

    def field(par, instr):
        for t, txt in (("begin", None), ("instr", instr), ("separate", None), ("text", "1"), ("end", None)):
            r = par.add_run()
            if t == "instr":
                e = OxmlElement("w:instrText"); e.set(qn("xml:space"), "preserve"); e.text = txt; r._r.append(e)
            elif t == "text":
                r.text = txt
            else:
                e = OxmlElement("w:fldChar"); e.set(qn("w:fldCharType"), t); r._r.append(e)

    def shade(cell, color):
        tcPr = cell._tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd"); shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto"); shd.set(qn("w:fill"), color); tcPr.append(shd)

    def repeat_header(row):
        trPr = row._tr.get_or_add_trPr()
        h = OxmlElement("w:tblHeader"); h.set(qn("w:val"), "true"); trPr.append(h)

    def add_runs(par, runs, size=None):
        for text, b, i, u, href in runs:
            r = par.add_run(text)
            r.bold, r.italic, r.underline = bool(b), bool(i), bool(u)
            if size: r.font.size = Pt(size)
            if href:
                r.font.color.rgb = RGBColor(0x05, 0x63, 0xC1); r.underline = True
                r.add_text(f" ({href})") if href.startswith("http") else None

    def table(headers, rows, widths=None):
        t = doc.add_table(rows=1, cols=len(headers))
        t.style = "Table Grid"
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        for i, h in enumerate(headers):
            cell = t.rows[0].cells[i]
            cell.text = ""
            r = cell.paragraphs[0].add_run(h); r.bold = True; r.font.color.rgb = RGBColor(255, 255, 255); r.font.size = Pt(9.5)
            shade(cell, BLUE)
        repeat_header(t.rows[0])
        for row in rows:
            cells = t.add_row().cells
            for i, v in enumerate(row):
                cells[i].text = ""
                rr = cells[i].paragraphs[0].add_run(str(v or "")); rr.font.size = Pt(9.5)
        if widths:
            for row in t.rows:
                for i, w in enumerate(widths):
                    row.cells[i].width = Cm(w)
        doc.add_paragraph()
        return t

    def kv_table(pairs):
        t = doc.add_table(rows=0, cols=2)
        t.style = "Table Grid"
        for k, v in pairs:
            cells = t.add_row().cells
            cells[0].text = ""
            r = cells[0].paragraphs[0].add_run(k); r.bold = True; r.font.size = Pt(9.5)
            shade(cells[0], "DEEAF6")
            cells[1].text = ""
            cells[1].paragraphs[0].add_run(str(v or "—")).font.size = Pt(9.5)
            cells[0].width, cells[1].width = Cm(4.2), Cm(12.8)
        doc.add_paragraph()

    def render_blocks(html):
        for b in html_blocks(html):
            if b["t"] == "p":
                add_runs(doc.add_paragraph(), b["runs"])
            elif b["t"] == "li":
                add_runs(doc.add_paragraph(style="List Bullet"), b["runs"])
            elif b["t"] == "h":
                add_runs(doc.add_paragraph(style="Heading 3"), b["runs"])
            elif b["t"] == "img":
                data = asset_png(b["src"])
                if data:
                    doc.add_picture(io.BytesIO(data), width=Cm(15))
            elif b["t"] == "table":
                ncols = max(sum(c["span"] for c in r) for r in b["rows"])
                t = doc.add_table(rows=0, cols=ncols)
                t.style = "Table Grid"
                for ri, r in enumerate(b["rows"]):
                    cells = t.add_row().cells
                    ci = 0
                    for c in r:
                        cell = cells[ci]
                        if c["span"] > 1:
                            cell = cell.merge(cells[min(ci + c["span"] - 1, ncols - 1)])
                        cell.text = ""
                        first = True
                        for runs in c["paras"] or [[]]:
                            par = cell.paragraphs[0] if first else cell.add_paragraph()
                            first = False
                            add_runs(par, runs, 9.5)
                            if c["head"]:
                                for rr in par.runs: rr.bold = True
                        if c["head"]:
                            shade(cell, "DEEAF6")
                        ci += c["span"]
                    if ri == 0:
                        repeat_header(t.rows[0])
                doc.add_paragraph()

    # ----- cover
    for _ in range(5): doc.add_paragraph()
    p = doc.add_paragraph(); r = p.add_run(snap["org"]); r.font.size = Pt(16); r.font.color.rgb = RGBColor(0x59, 0x59, 0x59)
    p = doc.add_paragraph(); r = p.add_run(snap["title"]); r.font.size = Pt(30); r.bold = True; r.font.color.rgb = RGBColor(0x1F, 0x4E, 0x79)
    p = doc.add_paragraph(); r = p.add_run(f"Generated {snap['generated_at'][:10]} · snapshot {snap['hash']}"); r.font.size = Pt(11)
    if snap["unapproved"]:
        p = doc.add_paragraph(); r = p.add_run(f"UNCONTROLLED DRAFT – {snap['unapproved']} of {snap['count']} included processes are not yet approved/published. "
                                                "Status is shown on every process."); r.bold = True; r.font.color.rgb = RGBColor(0xC0, 0, 0)
    doc.add_page_break()
    def plain_h(text):
        p_ = doc.add_paragraph(); r_ = p_.add_run(text); r_.bold = True; r_.font.size = Pt(18); r_.font.color.rgb = RGBColor(0x1F, 0x4E, 0x79)
        return p_
    plain_h("Document control")
    kv_table([("Document", snap["title"]), ("Scope", snap["scope"]), ("Processes included", snap["count"]), ("Generated by", snap["user_display"]),
              ("Generated at (UTC)", snap["generated_at"]), ("Snapshot hash", snap["hash"]),
              ("Control status", "Contains unapproved content" if snap["unapproved"] else "All content published / approved")])
    plain_h("Contents")
    entries = []
    for g_ in snap["departments"]:
        entries.append((0, g_["name"]))
        entries += [(1, f"{p_['process_id']} – {p_['name']}") for p_ in g_["processes"]]
    entries.append((0, "Appendix A – Revision history (included processes)"))
    # pre-populated TOC field (Word refreshes it with page numbers on update)
    for i, (lvl, text) in enumerate(entries):
        par = doc.add_paragraph()
        par.paragraph_format.left_indent = Cm(0.8 * lvl)
        par.paragraph_format.space_after = Pt(2)
        if i == 0:
            for t_, txt_ in (("begin", None), ("instr", 'TOC \\o "1-2" \\h \\z \\u'), ("separate", None)):
                r_ = par.add_run()
                if t_ == "instr":
                    e_ = OxmlElement("w:instrText"); e_.set(qn("xml:space"), "preserve"); e_.text = txt_; r_._r.append(e_)
                else:
                    e_ = OxmlElement("w:fldChar"); e_.set(qn("w:fldCharType"), t_); r_._r.append(e_)
        rr_ = par.add_run(text); rr_.bold = lvl == 0
        if i == len(entries) - 1:
            r_ = par.add_run(); e_ = OxmlElement("w:fldChar"); e_.set(qn("w:fldCharType"), "end"); r_._r.append(e_)
    note = doc.add_paragraph("Page numbers appear after Word updates the field (right-click the list → Update Field; Word may offer to do this on opening).")
    note.runs[0].italic = True; note.runs[0].font.size = Pt(8.5)
    settings = doc.settings.element
    uf = OxmlElement("w:updateFields"); uf.set(qn("w:val"), "true"); settings.append(uf)
    doc.add_page_break()
    # ----- body
    history = []
    for g in snap["departments"]:
        doc.add_paragraph(g["name"], style="Heading 1")
        for pr in g["processes"]:
            c = pr["content"]
            doc.add_paragraph(f"{pr['process_id']} – {pr['name']}", style="Heading 2")
            kv_table([("Process ID", pr["process_id"]), ("Source chart ID", pr["chart_id"]), ("Type", pr["kind"]), ("Department", g["name"]),
                      ("Owner", pr["owner"]), ("Reviewer", pr["reviewer"]), ("Countries / region", pr["countries"]),
                      ("Version / status", f"{pr['version']} · {pr['status_label']}"),
                      ("Approved by", f"{pr['approved_by']} ({pr['approved_at']})" if pr["approved_by"] else None)])
            for label, key in (("Objective", "objective"), ("Scope", "scope"), ("Trigger", "trigger"), ("Inputs", "inputs"), ("Outputs", "outputs")):
                if c.get(key):
                    doc.add_paragraph(label, style="Heading 3")
                    doc.add_paragraph(c[key])
            if c.get("responsible"):
                doc.add_paragraph("Responsible", style="Heading 3")
                for x in c["responsible"]:
                    doc.add_paragraph(x, style="List Bullet")
            if pr["diagram"]:
                doc.add_paragraph(f"Process Flow – {pr['process_id']}", style="Heading 3")
                png = diagram_image(pr["diagram"])
                if png:
                    doc.add_picture(io.BytesIO(png), width=Cm(16))
                    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
                cap = doc.add_paragraph(f"Figure – {pr['process_id']} flowchart preview (diagram {pr['diagram']['code']}, revision {pr['diagram']['ver_no']}). "
                                        f"Editable source: {pr['diagram']['code']}_rev{pr['diagram']['ver_no']}.drawio in the diagram package (open with draw.io / Flow Studio). "
                                        + ("STATUS: imported reference image – requires functional validation." if pr["diagram"]["validation"] == "requires_validation" else ""))
                cap.runs[0].italic = True; cap.runs[0].font.size = Pt(8.5)
            for label, key, heads in (("Detailed activities", "activities", ["No", "Activity", "Role", "SAP / system", "Output"]),
                                      ("RACI", "raci", ["Activity", "R", "A", "C", "I"]), ("SAP references", "sap", ["Transaction", "Purpose"]),
                                      ("KPIs", "kpis", ["KPI", "Definition", "Target"]), ("Escalation & SLA", "escalation", ["Stage", "Task / reminder to", "Time period", "Escalation", "Previous SLA"])):
                if c.get(key):
                    doc.add_paragraph(label, style="Heading 3")
                    table(heads, [list(r.values()) for r in c[key]])
            for label, key in (("Risks and controls", "risks"), ("Required evidence", "evidence"), ("Forms and templates", "forms"), ("Notes", "notes")):
                if c.get(key):
                    doc.add_paragraph(label, style="Heading 3")
                    doc.add_paragraph(c[key])
            for s in c.get("sections", []):
                if s["title"]:
                    doc.add_paragraph(s["title"], style="Heading 3")
                render_blocks(s["html"])
            if pr["sources"]:
                doc.add_paragraph("Source references", style="Heading 3")
                table(["Source document", "Version", "Section", "Role"], [[s["filename"], s["version_text"], s["heading"], s["role"]] for s in pr["sources"]])
            history.append([pr["process_id"], pr["version"], pr["status_label"], pr["author"], pr["change_summary"]])
    doc.add_page_break()
    doc.add_paragraph("Appendix A – Revision history (included processes)", style="Heading 1")
    table(["Process", "Version", "Status", "Author", "Change summary"], history)
    # header / footer
    s0 = doc.sections[0]
    hp = s0.header.paragraphs[0]
    hp.text = f"{snap['org']} – {snap['title']}" + ("   |   UNCONTROLLED DRAFT" if snap["unapproved"] else "")
    hp.runs[0].font.size = Pt(8.5)
    fp = s0.footer.paragraphs[0]
    fr = fp.add_run(f"{snap['footer']}   |   snapshot {snap['hash']}   |   Page "); fr.font.size = Pt(8)
    field(fp, "PAGE")
    fp.add_run(" of ").font.size = Pt(8)
    field(fp, "NUMPAGES")
    bio = io.BytesIO()
    doc.save(bio)
    return bio.getvalue()


# ------------------------------------------------------------------ PDF
def build_pdf(snap) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle)
    from reportlab.platypus.tableofcontents import TableOfContents
    import reportlab

    fdir = os.path.join(os.path.dirname(reportlab.__file__), "fonts")
    base, bold, ital = "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"
    try:
        pdfmetrics.registerFont(TTFont("Vera", os.path.join(fdir, "Vera.ttf")))
        pdfmetrics.registerFont(TTFont("Vera-B", os.path.join(fdir, "VeraBd.ttf")))
        pdfmetrics.registerFont(TTFont("Vera-I", os.path.join(fdir, "VeraIt.ttf")))
        pdfmetrics.registerFont(TTFont("Vera-BI", os.path.join(fdir, "VeraBI.ttf")))
        pdfmetrics.registerFontFamily("Vera", normal="Vera", bold="Vera-B", italic="Vera-I", boldItalic="Vera-BI")
        base, bold, ital = "Vera", "Vera-B", "Vera-I"
    except Exception:
        pass
    ss = getSampleStyleSheet()
    BLUE = colors.HexColor("#1F4E79")
    sN = ParagraphStyle("N", parent=ss["Normal"], fontName=base, fontSize=9, leading=12)
    sSmall = ParagraphStyle("S", parent=sN, fontSize=7.5, leading=9, textColor=colors.HexColor("#555555"))
    sH1 = ParagraphStyle("H1", parent=sN, fontName=bold, fontSize=17, leading=21, textColor=BLUE, spaceBefore=6, spaceAfter=8)
    sH2 = ParagraphStyle("H2", parent=sN, fontName=bold, fontSize=13, leading=16, textColor=BLUE, spaceBefore=10, spaceAfter=5)
    sH3 = ParagraphStyle("H3", parent=sN, fontName=bold, fontSize=10, leading=13, textColor=BLUE, spaceBefore=7, spaceAfter=3)
    sLi = ParagraphStyle("Li", parent=sN, leftIndent=14, bulletIndent=4)
    sH1n = ParagraphStyle("H1n", parent=sH1)
    sCell = ParagraphStyle("C", parent=sN, fontSize=8, leading=10)
    sCellB = ParagraphStyle("CB", parent=sCell, fontName=bold, textColor=colors.white)

    def esc(t):
        return htmllib.escape(t).replace("\n", "<br/>")

    def runs_markup(runs):
        out = []
        for text, b, i, u, href in runs:
            t = esc(text)
            if b: t = f"<b>{t}</b>"
            if i: t = f"<i>{t}</i>"
            if u: t = f"<u>{t}</u>"
            if href and href.startswith("http"): t = f'<a href="{htmllib.escape(href)}" color="blue">{t}</a>'
            out.append(t)
        return "".join(out)

    class Doc(SimpleDocTemplate):
        def afterFlowable(self, f):
            if isinstance(f, Paragraph) and f.style.name in ("H1", "H2"):
                key = f"h{id(f)}"
                self.canv.bookmarkPage(key)
                self.notify("TOCEntry", (0 if f.style.name == "H1" else 1, f.getPlainText(), self.page, key))

    def head_foot(canv, d):
        canv.saveState()
        canv.setFont(base, 7.5)
        canv.setFillColor(colors.HexColor("#555555"))
        canv.drawString(2 * cm, 28.9 * cm, f"{snap['org']} – {snap['title']}" + ("  |  UNCONTROLLED DRAFT" if snap["unapproved"] else ""))
        canv.drawString(2 * cm, 1.2 * cm, f"{snap['footer']} | snapshot {snap['hash']}")
        canv.drawRightString(19 * cm, 1.2 * cm, f"Page {d.page}")
        canv.restoreState()

    def tbl(headers, rows, widths):
        data = [[Paragraph(esc(h), sCellB) for h in headers]] + [[Paragraph(esc(str(v or "")), sCell) for v in r] for r in rows]
        t = Table(data, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), BLUE), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#999999")),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F7FB")])]))
        return t

    def kv(pairs):
        data = [[Paragraph(f"<b>{esc(k)}</b>", sCell), Paragraph(esc(str(v or "—")), sCell)] for k, v in pairs]
        t = Table(data, colWidths=[4 * cm, 13 * cm])
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#999999")), ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#DEEAF6")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        return t

    def fit_image(data, maxw=17 * cm, maxh=19 * cm):
        from PIL import Image as PI
        w, h = PI.open(io.BytesIO(data)).size
        sc = min(maxw / w, maxh / h)
        return Image(io.BytesIO(data), width=w * sc, height=h * sc)

    def block_flow(html):
        out = []
        for b in html_blocks(html):
            if b["t"] == "p":
                out.append(Paragraph(runs_markup(b["runs"]), sN))
            elif b["t"] == "li":
                out.append(Paragraph(runs_markup(b["runs"]), sLi, bulletText="•"))
            elif b["t"] == "h":
                out.append(Paragraph(runs_markup(b["runs"]), sH3))
            elif b["t"] == "img":
                d = asset_png(b["src"])
                if d: out.append(fit_image(d))
            elif b["t"] == "table":
                ncols = max(sum(c["span"] for c in r) for r in b["rows"])
                data, spans = [], []
                for ri, r in enumerate(b["rows"]):
                    row, ci = [], 0
                    for c in r:
                        txt = "<br/>".join(runs_markup(p) for p in c["paras"])
                        row.append(Paragraph(txt, sCellB if c["head"] else sCell))
                        if c["span"] > 1:
                            spans.append(("SPAN", (ci, ri), (ci + c["span"] - 1, ri)))
                        row += [""] * (c["span"] - 1)
                        ci += c["span"]
                    data.append(row + [""] * (ncols - len(row)))
                t = Table(data, colWidths=[17 * cm / ncols] * ncols, repeatRows=1)
                style = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#999999")), ("VALIGN", (0, 0), (-1, -1), "TOP")] + spans
                if any(c["head"] for c in b["rows"][0]):
                    style.append(("BACKGROUND", (0, 0), (-1, 0), BLUE))
                t.setStyle(TableStyle(style))
                out += [t, Spacer(1, 6)]
        return out

    story = [Spacer(1, 5 * cm), Paragraph(esc(snap["org"]), ParagraphStyle("o", parent=sN, fontSize=15, textColor=colors.HexColor("#555555"))),
             Paragraph(esc(snap["title"]), ParagraphStyle("t", parent=sN, fontName=bold, fontSize=28, leading=33, textColor=BLUE, spaceBefore=10)),
             Spacer(1, 8), Paragraph(f"Generated {snap['generated_at'][:10]} · snapshot {snap['hash']}", sN)]
    if snap["unapproved"]:
        story.append(Paragraph(f"<font color='#C00000'><b>UNCONTROLLED DRAFT – {snap['unapproved']} of {snap['count']} included processes are not yet approved/published.</b></font>", sN))
    story += [PageBreak(), Paragraph("Document control", sH1n),
              kv([("Document", snap["title"]), ("Scope", snap["scope"]), ("Processes included", snap["count"]), ("Generated by", snap["user_display"]),
                  ("Generated at (UTC)", snap["generated_at"]), ("Snapshot hash", snap["hash"]),
                  ("Control status", "Contains unapproved content" if snap["unapproved"] else "All content published / approved")]),
              Spacer(1, 14), Paragraph("Contents", sH1n)]
    toc = TableOfContents()
    toc.levelStyles = [ParagraphStyle("t1", parent=sN, fontName=bold, leftIndent=0, spaceBefore=4),
                       ParagraphStyle("t2", parent=sN, leftIndent=14)]
    story += [toc, PageBreak()]
    history = []
    for g in snap["departments"]:
        story.append(Paragraph(esc(g["name"]), sH1))
        for pr in g["processes"]:
            c = pr["content"]
            story.append(Paragraph(esc(f"{pr['process_id']} – {pr['name']}"), sH2))
            story.append(kv([("Process ID", pr["process_id"]), ("Source chart ID", pr["chart_id"]), ("Type", pr["kind"]), ("Owner", pr["owner"]), ("Reviewer", pr["reviewer"]),
                             ("Countries / region", pr["countries"]), ("Version / status", f"{pr['version']} · {pr['status_label']}"),
                             ("Approved by", f"{pr['approved_by']} ({pr['approved_at']})" if pr["approved_by"] else None)]))
            for label, key in (("Objective", "objective"), ("Scope", "scope"), ("Trigger", "trigger"), ("Inputs", "inputs"), ("Outputs", "outputs")):
                if c.get(key):
                    story += [Paragraph(label, sH3), Paragraph(esc(c[key]), sN)]
            if c.get("responsible"):
                story.append(Paragraph("Responsible", sH3))
                story += [Paragraph(esc(x), sLi, bulletText="•") for x in c["responsible"]]
            if pr["diagram"]:
                story.append(Paragraph(f"Process Flow – {pr['process_id']}", sH3))
                png = diagram_image(pr["diagram"])
                if png:
                    story.append(KeepTogether([fit_image(png, 17 * cm, 16 * cm), Paragraph(
                        f"Figure – {pr['process_id']} flowchart preview (diagram {pr['diagram']['code']} rev {pr['diagram']['ver_no']}); editable source = {pr['diagram']['code']}_rev{pr['diagram']['ver_no']}.drawio"
                        + (" – imported reference image, requires functional validation" if pr["diagram"]["validation"] == "requires_validation" else ""), sSmall)]))
            for label, key, heads, widths in (
                    ("Detailed activities", "activities", ["No", "Activity", "Role", "SAP / system", "Output"], [1.2 * cm, 6 * cm, 3.3 * cm, 3 * cm, 3.5 * cm]),
                    ("RACI", "raci", ["Activity", "R", "A", "C", "I"], [6.5 * cm, 2.6 * cm, 2.6 * cm, 2.6 * cm, 2.7 * cm]),
                    ("SAP references", "sap", ["Transaction", "Purpose"], [4 * cm, 13 * cm]),
                    ("KPIs", "kpis", ["KPI", "Definition", "Target"], [6 * cm, 8 * cm, 3 * cm]),
                    ("Escalation & SLA", "escalation", ["Stage", "Task / reminder to", "Time period", "Escalation", "Previous SLA"], [2 * cm, 4 * cm, 3.6 * cm, 4.2 * cm, 3.2 * cm])):
                if c.get(key):
                    story += [Paragraph(label, sH3), tbl(heads, [list(r.values()) for r in c[key]], widths)]
            for label, key in (("Risks and controls", "risks"), ("Required evidence", "evidence"), ("Forms and templates", "forms"), ("Notes", "notes")):
                if c.get(key):
                    story += [Paragraph(label, sH3), Paragraph(esc(c[key]), sN)]
            for s in c.get("sections", []):
                if s["title"]:
                    story.append(Paragraph(esc(s["title"]), sH3))
                story += block_flow(s["html"])
            if pr["sources"]:
                story += [Paragraph("Source references", sH3), tbl(["Source document", "Version", "Section", "Role"], [[s["filename"], s["version_text"], s["heading"], s["role"]] for s in pr["sources"]],
                                                                  [7 * cm, 2 * cm, 5.5 * cm, 2.5 * cm])]
            history.append([pr["process_id"], pr["version"], pr["status_label"], pr["author"], pr["change_summary"]])
    story += [PageBreak(), Paragraph("Appendix A – Revision history (included processes)", sH1), tbl(["Process", "Version", "Status", "Author", "Change summary"], history, [3.5 * cm, 1.8 * cm, 3 * cm, 2.7 * cm, 6 * cm])]
    bio = io.BytesIO()
    d = Doc(bio, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2.2 * cm, bottomMargin=2 * cm, title=snap["title"], author=snap["generated_by"])
    d.multiBuild(story, onFirstPage=head_foot, onLaterPages=head_foot)
    return bio.getvalue()


# ------------------------------------------------------------------ HTML / ZIP
def build_html(snap) -> bytes:
    e = htmllib.escape
    out = [f"<!doctype html><html><head><meta charset=utf-8><title>{e(snap['title'])}</title><style>body{{font-family:Segoe UI,Arial;max-width:980px;margin:2em auto;line-height:1.45}}"
           "table{border-collapse:collapse;margin:.6em 0}td,th{border:1px solid #999;padding:4px 8px;vertical-align:top}th{background:#1F4E79;color:#fff}h1,h2,h3{color:#1F4E79}"
           ".warn{color:#c00;font-weight:bold}img{max-width:100%}</style></head><body>",
           f"<h1>{e(snap['org'])} – {e(snap['title'])}</h1><p>Generated {e(snap['generated_at'])} · snapshot {snap['hash']}</p>"]
    if snap["unapproved"]:
        out.append(f"<p class=warn>UNCONTROLLED DRAFT – {snap['unapproved']} of {snap['count']} processes are not approved.</p>")
    out.append("<h2>Contents</h2><ul>")
    for g in snap["departments"]:
        out.append(f"<li>{e(g['name'])}<ul>" + "".join(f"<li><a href='#{e(p['process_id'])}'>{e(p['process_id'])} – {e(p['name'])}</a></li>" for p in g["processes"]) + "</ul></li>")
    out.append("</ul>")
    for g in snap["departments"]:
        out.append(f"<h1>{e(g['name'])}</h1>")
        for p in g["processes"]:
            c = p["content"]
            out.append(f"<h2 id='{e(p['process_id'])}'>{e(p['process_id'])} – {e(p['name'])}</h2><p><b>{e(p['status_label'])}</b> · v{e(p['version'])} · owner: {e(p['owner'] or '—')}</p>")
            for label, key in (("Objective", "objective"), ("Scope", "scope"), ("Trigger", "trigger"), ("Inputs", "inputs"), ("Outputs", "outputs")):
                if c.get(key):
                    out.append(f"<h3>{label}</h3><p>{e(c[key])}</p>")
            if c.get("responsible"):
                out.append("<h3>Responsible</h3><ul>" + "".join(f"<li>{e(x)}</li>" for x in c["responsible"]) + "</ul>")
            if p["diagram"]:
                png = diagram_image(p["diagram"])
                if png:
                    out.append(f"<h3>Process Flow</h3><img alt='{e(p['process_id'])} flow' src='data:image/png;base64,{base64.b64encode(png).decode()}'>")
            for label, key, heads in (("Detailed activities", "activities", ["No", "Activity", "Role", "SAP", "Output"]), ("RACI", "raci", ["Activity", "R", "A", "C", "I"]),
                                      ("SAP references", "sap", ["Transaction", "Purpose"]), ("KPIs", "kpis", ["KPI", "Definition", "Target"]),
                                      ("Escalation", "escalation", ["Stage", "To", "Time", "Escalation", "SLA"])):
                if c.get(key):
                    out.append(f"<h3>{label}</h3><table><tr>" + "".join(f"<th>{h}</th>" for h in heads) + "</tr>" +
                               "".join("<tr>" + "".join(f"<td>{e(v)}</td>" for v in r.values()) + "</tr>" for r in c[key]) + "</table>")
            for s in c.get("sections", []):
                html = re.sub(r'src="/api/assets/(\d+)"', lambda m: _data_uri(int(m.group(1))), s["html"])
                out.append(f"<h3>{e(s['title'])}</h3>{html}")
    out.append("</body></html>")
    return "".join(out).encode()


def _data_uri(aid):
    try:
        mime, data = svc.asset_bytes(aid)
        return f'src="data:{mime};base64,{base64.b64encode(data).decode()}"'
    except svc.NotFound:
        return 'src=""'


def build_zip(snap) -> bytes:
    bio = io.BytesIO()
    manifest = []
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as z:
        for g in snap["departments"]:
            for p in g["processes"]:
                d = p["diagram"]
                if not d:
                    continue
                base = f"diagrams/{d['code']}_rev{d['ver_no']}"
                z.writestr(base + ".drawio", d["xml"])
                png = diagram_image(d)
                if png:
                    z.writestr(base + ".png", png)
                z.writestr(base + ".svg", drawio.to_svg(d["xml"]))
                manifest.append(dict(process_id=p["process_id"], diagram=d["code"], revision=d["ver_no"], validation=d["validation"], sha256=d["sha"]))
        z.writestr("manifest.json", json.dumps(dict(snapshot=snap["hash"], generated_at=snap["generated_at"], diagrams=manifest), indent=2))
        z.writestr("README.txt", "Open the .drawio files with draw.io (diagrams.net) or with Flow Studio in MEA Process Hub. "
                                 "PNG/SVG files are previews only; the .drawio file is the editable source.")
    return bio.getvalue()


FORMATS = {"docx": (build_docx, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"), "pdf": (build_pdf, "application/pdf"),
           "html": (build_html, "text/html; charset=utf-8"), "zip": (build_zip, "application/zip")}


def run_export(user, scope, fmt, ids=None, dept=None, include_unapproved=True, version_id=None):
    if fmt not in FORMATS:
        raise svc.Invalid("Unsupported format.")
    ts = svc.now()
    cur = db.db().execute("INSERT INTO exports(ts,username,scope,fmt,status) VALUES(?,?,?,?,?)", (ts, user["username"], scope + (f":{dept}" if dept else "") + (f":{','.join(ids)}" if ids else ""), fmt, "running"))
    eid = cur.lastrowid
    try:
        snap = build_snapshot(user, scope, ids, dept, include_unapproved, version_id)
        if not snap["count"]:
            raise svc.Invalid("Nothing to export for this scope (no visible content).")
        data = FORMATS[fmt][0](snap)
        sha = hashlib.sha256(data).hexdigest()
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", snap["title"])[:60]
        fname = f"{safe}_{snap['generated_at'][:10]}_{snap['hash'][:6]}.{fmt}"
        path = os.path.join(config.EXPORT_DIR, f"{eid}_{fname}")
        with open(path, "wb") as f:
            f.write(data)
        db.db().execute("UPDATE exports SET status='done', filename=?, sha256=?, size=?, snapshot_hash=?, snapshot=? WHERE id=?",
                        (fname, sha, len(data), snap["hash"], json.dumps(snap["versions"]), eid))
        svc.audit(user, "export", "export", eid, f"{scope} {fmt} {snap['count']} processes sha {sha[:12]}")
        return one("SELECT * FROM exports WHERE id=?", (eid,))
    except BaseException as ex:
        db.db().execute("UPDATE exports SET status='failed', error=? WHERE id=?", (str(ex)[:500], eid))
        raise


def export_file(user, eid):
    e = one("SELECT * FROM exports WHERE id=?", (eid,))
    if not e or e["status"] != "done":
        raise svc.NotFound("Export not found")
    if e["username"] != user["username"] and user["role"] not in ("admin", "controller"):
        raise svc.Forbidden("You can only download your own exports.")
    path = os.path.join(config.EXPORT_DIR, f"{eid}_{e['filename']}")
    with open(path, "rb") as f:
        return e, f.read()
