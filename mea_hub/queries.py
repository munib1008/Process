"""Read models for the UI plus reports, register workbook, backup/restore."""
import datetime as dt
import io
import json
import os
import shutil
import sqlite3
import zipfile

from . import config, db, service as svc
from .db import jloads, one, q


def _summary_rows(user):
    rows = q("""SELECT p.id, p.process_id, p.chart_id, p.name, p.kind, p.category, p.countries, p.owner, p.reviewer, p.next_review, p.validation,
                       p.department_id, d.name AS department, d.code AS dept_code, p.parent_id, p.sort_order
                FROM processes p LEFT JOIN departments d ON d.id=p.department_id ORDER BY d.sort, p.sort_order, p.id""")
    out = []
    staff = svc.can(user, "view_all")
    for r in rows:
        lv = svc.latest_version(r["id"])
        pv = svc.published_version(r["id"])
        if not staff and not pv:
            continue
        shown = lv if staff else pv
        dv = shown.get("diagram_version_id") if shown else None
        dvr = one("SELECT validation, diagram_id FROM diagram_versions WHERE id=?", (dv,)) if dv else None
        content = shown["content"] if shown else {}
        r.update(status=shown["status"], status_label=svc.STATUS_LABEL[shown["status"]], version=shown["version"], version_id=shown["id"],
                 published_version=pv["version"] if pv else None, has_diagram=bool(dv), diagram_validation=dvr["validation"] if dvr else None,
                 diagram_id=dvr["diagram_id"] if dvr else None, has_kpi=bool(content.get("kpis")), has_raci=bool(content.get("raci")),
                 updated_at=shown["updated_at"])
        out.append(r)
    return out


def library(user, dept=None, status=None, kind=None, text=None):
    rows = _summary_rows(user)
    if dept:
        rows = [r for r in rows if r["dept_code"] == dept]
    if status:
        rows = [r for r in rows if r["status"] == status]
    if kind:
        rows = [r for r in rows if r["kind"] == kind]
    if text:
        t = text.lower()
        rows = [r for r in rows if t in r["name"].lower() or t in r["process_id"].lower()]
    return rows


def tree(user):
    depts = q("SELECT * FROM departments ORDER BY sort")
    rows = _summary_rows(user)
    for d in depts:
        d["processes"] = [r for r in rows if r["department_id"] == d["id"]]
    return depts


def process_detail(user, pid_text, version_id=None):
    p = svc.get_process(pid_text)
    staff = svc.can(user, "view_all")
    pv = svc.published_version(p["id"])
    if version_id:
        v = svc.get_version(int(version_id))
        if v["process_id"] != p["id"]:
            raise svc.NotFound("Version not found")
        if not staff and v["status"] != "published":
            raise svc.Forbidden("Only published versions are visible to your role.")
    else:
        v = svc.latest_version(p["id"]) if staff else pv
    if not v:
        raise svc.Forbidden("This process has no published version yet.")
    versions = q("SELECT id,version,status,change_summary,author,created_at,submitted_at,reviewed_by,reviewed_at,approved_by,approved_at,published_at,review_note FROM process_versions WHERE process_id=? ORDER BY major DESC, minor DESC, id DESC", (p["id"],))
    if not staff:
        versions = [x for x in versions if x["status"] in ("published", "superseded")]
    diagram = None
    if v.get("diagram_version_id"):
        dv = one("SELECT dv.id,dv.ver_no,dv.validation,dv.origin,dv.preview_asset_id,dv.created_at,dv.author,dv.diagram_id,d.code,d.title,d.lock_user,d.lock_expires FROM diagram_versions dv JOIN diagrams d ON d.id=dv.diagram_id WHERE dv.id=?", (v["diagram_version_id"],))
        if dv:
            latest = one("SELECT ver_no FROM diagram_versions WHERE diagram_id=? ORDER BY ver_no DESC LIMIT 1", (dv["diagram_id"],))
            dv["latest_ver"] = latest["ver_no"]
            dv["locked_by"] = dv["lock_user"] if dv["lock_user"] and dv["lock_expires"] and dv["lock_expires"] > svc.now() else None
            dv["nodes"] = svc.diagram_nodes(dv["id"]) if staff else []
            dv["checks"] = svc.flow_checks(dv["id"]) if staff else None
            dv["picture"] = svc.picture_info(dv["id"]) if staff else None
            diagram = dv
    rels = q("""SELECT r.id,r.rel_type,r.note,r.inferred,'out' AS dir,p.process_id,p.name FROM relationships r JOIN processes p ON p.id=r.to_id WHERE r.from_id=?
                UNION ALL SELECT r.id,r.rel_type,r.note,r.inferred,'in' AS dir,p.process_id,p.name FROM relationships r JOIN processes p ON p.id=r.from_id WHERE r.to_id=?""", (p["id"], p["id"]))
    maps = q("""SELECT m.id,m.role,m.heading,m.chart_id,m.similarity,m.location,m.asset_ids,s.id AS source_id,s.filename,s.version_text FROM mappings m
                JOIN sources s ON s.id=m.source_id WHERE m.process_id=?""", (p["id"],)) if staff else []
    for m in maps:
        m["asset_ids"] = jloads(m["asset_ids"], [])
    comments = q("SELECT * FROM comments WHERE process_id=? ORDER BY id DESC LIMIT 400", (p["id"],)) if staff else []
    findings = q("SELECT * FROM findings WHERE process_id=? ORDER BY id", (p["id"],)) if staff else []
    ov = svc.open_version(p["id"])
    perms = dict(
        edit=svc.can(user, "edit", p), review=svc.can(user, "review", p), approve=svc.can(user, "approve", p), publish=svc.can(user, "publish", p),
        accept_import=svc.can(user, "accept_import", p), comment=svc.can(user, "comment", p), manage_relationships=svc.can(user, "manage_relationships", p),
        manage_findings=svc.can(user, "manage_findings", p), export_draft=svc.can(user, "export_draft", p), rename_id=svc.can(user, "rename_id", p))
    return dict(process=p, version=v, versions=versions, diagram=diagram, relationships=rels, mappings=maps, comments=comments, findings=findings,
                open_version=dict(id=ov["id"], status=ov["status"], version=ov["version"], author=ov["author"]) if ov else None,
                published_version=pv["version"] if pv else None, perms=perms, status_label=svc.STATUS_LABEL[v["status"]],
                editable=bool(perms["edit"] and v["status"] in svc.EDITABLE or (perms["edit"] and not ov)))


def dashboard(user):
    rows = _summary_rows(user)
    today = dt.date.today().isoformat()
    by_status, by_dept = {}, {}
    for r in rows:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
        d = by_dept.setdefault(r["dept_code"], dict(name=r["department"], total=0, published=0, with_flow=0))
        d["total"] += 1
        d["published"] += r["status"] == "published"
        d["with_flow"] += r["has_diagram"]
    real = [r for r in rows if r["kind"] in ("sop", "approval", "department", "e2e", "work_instruction")]
    all_depts = q("SELECT code,name FROM departments ORDER BY sort")
    cover = [dict(by_dept.get(d["code"], dict(total=0, published=0, with_flow=0)), code=d["code"], name=d["name"]) for d in all_depts]
    pend = [dict(process_id=r["process_id"], name=r["name"], status=r["status"], version=r["version"]) for r in rows if r["status"] in ("under_review", "pending_approval", "approved", "changes_requested")]
    imported = sum(1 for r in rows if r["status"] == "imported")
    accepted = sum(1 for r in rows if r["validation"] in ("accepted", "approved", "authored"))
    f = q("SELECT status,severity,kind,COUNT(*) n FROM findings GROUP BY status,severity,kind")
    return dict(
        total=len(rows), by_status=by_status, coverage=cover, pending=pend,
        overdue_reviews=[dict(process_id=r["process_id"], name=r["name"], next_review=r["next_review"]) for r in rows if r["next_review"] and r["next_review"] < today],
        no_review_schedule=sum(1 for r in real if not r["next_review"]),
        missing_owner=[dict(process_id=r["process_id"], name=r["name"]) for r in real if not r["owner"]],
        missing_flowchart=[dict(process_id=r["process_id"], name=r["name"]) for r in rows if r["kind"] in ("sop", "approval", "department") and not r["has_diagram"]],
        needs_flow_validation=sum(1 for r in rows if r["diagram_validation"] == "requires_validation"),
        no_kpi=sum(1 for r in real if not r["has_kpi"]), no_raci=sum(1 for r in real if not r["has_raci"]),
        orphan=len(process_map(user)["orphans"]),
        import_progress=dict(imported=imported, accepted=accepted, total=len(rows)),
        recent=sorted([dict(process_id=r["process_id"], name=r["name"], status=r["status"], updated_at=r["updated_at"]) for r in rows], key=lambda x: x["updated_at"], reverse=True)[:8],
        findings=dict(open=one("SELECT COUNT(*) n FROM findings WHERE status='open'")["n"], high=one("SELECT COUNT(*) n FROM findings WHERE status='open' AND severity='high'")["n"],
                      duplicates=one("SELECT COUNT(*) n FROM findings WHERE status='open' AND kind='duplicate'")["n"], breakdown=f),
        sources=one("SELECT COUNT(*) n FROM sources")["n"])


def search(user, text, dept=None, status=None, limit=60):
    terms = [t for t in (text or "").lower().split() if t]
    if not terms:
        return []
    staff = svc.can(user, "view_all")
    col = "body" if staff else "body_pub"
    where = " AND ".join(f"si.{col} LIKE ?" for _ in terms)
    rows = q(f"SELECT p.process_id,p.name,p.kind,d.name department,d.code dept_code,si.{col} body FROM search_index si JOIN processes p ON p.id=si.process_id "
             f"LEFT JOIN departments d ON d.id=p.department_id WHERE {where} AND si.{col}<>'' LIMIT ?", [f"%{t}%" for t in terms] + [limit * 3])
    out = []
    summaries = {r["process_id"]: r for r in _summary_rows(user)}
    for r in rows:
        s = summaries.get(r["process_id"])
        if not s or (dept and r["dept_code"] != dept) or (status and s["status"] != status):
            continue
        b = r.pop("body")
        i = b.find(terms[0])
        r["snippet"] = ("…" + b[max(0, i - 60): i + 120] + "…") if i >= 0 else ""
        r["status"] = s["status"]
        r["status_label"] = s["status_label"]
        out.append(r)
    return out[:limit]


def process_map(user):
    rows = _summary_rows(user)
    ids = {r["id"] for r in rows}
    edges = [e for e in q("SELECT r.id,r.from_id,r.to_id,r.rel_type,r.inferred FROM relationships r") if e["from_id"] in ids and e["to_id"] in ids]
    linked = {e["from_id"] for e in edges} | {e["to_id"] for e in edges}
    nodes = [dict(id=r["id"], process_id=r["process_id"], name=r["name"], dept=r["dept_code"], kind=r["kind"], status=r["status"]) for r in rows if r["kind"] != "reference"]
    orphans = [n for n in nodes if n["id"] not in linked]
    no_next = [n for n in nodes if n["kind"] in ("sop", "approval") and n["id"] not in {e["from_id"] for e in edges if e["rel_type"] in ("next", "triggers")}]
    return dict(nodes=nodes, edges=edges, orphans=orphans, no_handover=[n for n in no_next if n["id"] in linked or True][:500])


def trace(user, pid_text, direction="down", depth=6):
    p = svc.get_process(pid_text)
    seen, frontier, out = {p["id"]}, [p["id"]], []
    for _ in range(depth):
        nxt = []
        for fid in frontier:
            qs = ("SELECT to_id x, rel_type FROM relationships WHERE from_id=?" if direction == "down" else "SELECT from_id x, rel_type FROM relationships WHERE to_id=?")
            for e in q(qs, (fid,)):
                if e["x"] not in seen:
                    seen.add(e["x"])
                    nxt.append(e["x"])
                    pr = one("SELECT process_id,name FROM processes WHERE id=?", (e["x"],))
                    out.append(dict(**pr, rel_type=e["rel_type"]))
        frontier = nxt
    return out


def raci_report(user):
    rows = []
    for r in _summary_rows(user):
        if r["kind"] == "reference":
            continue
        v = svc.latest_version(r["id"]) if svc.can(user, "view_all") else svc.published_version(r["id"])
        raci = v["content"].get("raci", [])
        issues = []
        if not raci:
            issues.append("No RACI defined")
        for a in raci:
            if not a["A"].strip():
                issues.append(f"Missing accountable owner: {a['activity']}")
            elif "," in a["A"] or "/" in a["A"]:
                issues.append(f"Conflicting accountability (multiple A): {a['activity']}")
            if not a["R"].strip():
                issues.append(f"Unassigned responsibility: {a['activity']}")
        rows.append(dict(process_id=r["process_id"], name=r["name"], department=r["department"], owner=r["owner"], raci=raci,
                         responsible_listed=v["content"].get("responsible", []), issues=issues))
    return rows


def kpi_report(user):
    out = []
    for r in _summary_rows(user):
        v = svc.latest_version(r["id"]) if svc.can(user, "view_all") else svc.published_version(r["id"])
        for k in v["content"].get("kpis", []):
            out.append(dict(process_id=r["process_id"], process=r["name"], department=r["department"], **k))
    return out


def escalation_report(user):
    out = []
    for r in _summary_rows(user):
        v = svc.latest_version(r["id"]) if svc.can(user, "view_all") else svc.published_version(r["id"])
        for e in v["content"].get("escalation", []):
            out.append(dict(process_id=r["process_id"], process=r["name"], department=r["department"], **e))
    return out


def approvals_queue(user):
    rows = []
    for r in _summary_rows(user):
        if r["status"] in ("under_review", "pending_approval", "approved", "changes_requested"):
            v = svc.open_version(r["id"])
            rows.append(dict(process_id=r["process_id"], name=r["name"], department=r["department"], status=v["status"], status_label=svc.STATUS_LABEL[v["status"]],
                             version=v["version"], author=v["author"], submitted_at=v["submitted_at"], summary=v["change_summary"]))
    return rows


def change_log(user, process_id=None, limit=200):
    if process_id:
        return q("SELECT * FROM audit WHERE entity='process' AND entity_id=? ORDER BY id DESC LIMIT ?", (process_id, limit))
    return q("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,))


def recommendation(f):
    t, k = f["title"], f["kind"]
    if k == "duplicate":
        return "Keep the primary definition; owner compares wording if similarity is below 90%." if "differs" in f["detail"] else "Accept: content is essentially identical – keep one controlled definition."
    if t.startswith("Provisional ID"):
        return "Accept the provisional ID until the Document Controller issues the permanent ID (process page > Change ID)."
    if t.startswith("Chart ID") and "provisional" in t:
        return "Document Controller issues a permanent unique ID (process page > Change ID); keep both processes until then."
    if t.startswith("Source document not supplied"):
        return "Obtain and upload the document (or its flowcharts)."
    if "No 'Responsible'" in t:
        return "Process owner names the responsible roles."
    if "Source title does not match" in t:
        return "Confirm with the owner that the correct file was supplied."
    if "ID prefix" in t:
        return "Decide the ID scheme (prefix per department) and re-issue IDs."
    if "Proposed" in t:
        return "Keep labelled [PROPOSED] until the owner approves it as procedure."
    if "extracted automatically" in t or "flowcharts imported" in t:
        return "Process owner validates against the original; then mark resolved."
    return "Owner decision required."


def findings(status=None, kind=None):
    sql, args = "SELECT f.*,s.filename,p.process_id AS pid_text,p.name AS pname FROM findings f LEFT JOIN sources s ON s.id=f.source_id LEFT JOIN processes p ON p.id=f.process_id WHERE 1=1", []
    if status:
        sql += " AND f.status=?"
        args.append(status)
    if kind:
        sql += " AND f.kind=?"
        args.append(kind)
    rows = q(sql + " ORDER BY CASE f.severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, f.id", args)
    for r in rows:
        r["recommended"] = recommendation(r)
    return rows


def bulk_update_findings(user, ids, status, decision):
    svc.need(user, "manage_findings")
    if status not in ("accepted", "resolved", "wont_fix", "open") or not ids:
        raise svc.Invalid("Choose a status and at least one finding.")
    if not (decision or "").strip():
        raise svc.Invalid("A decision / rationale is required.")
    with db.tx():
        for fid in ids[:500]:
            db.db().execute("UPDATE findings SET status=?, decision=?, resolved_by=? WHERE id=?", (status, decision[:2000], user["username"], int(fid)))
        svc.audit(user, "findings_bulk_updated", "finding", None, f"{len(ids)} -> {status}: {decision[:120]}")
    return dict(updated=len(ids[:500]))


def update_finding(user, fid, status, decision=""):
    svc.need(user, "manage_findings")
    if status not in ("open", "accepted", "resolved", "wont_fix"):
        raise svc.Invalid("Unknown status")
    with db.tx():
        db.db().execute("UPDATE findings SET status=?, decision=?, resolved_by=? WHERE id=?", (status, decision[:2000], user["username"], fid))
        svc.audit(user, "finding_updated", "finding", fid, f"{status}: {decision[:200]}")


def sources_register():
    out = []
    names = {d["code"]: d["name"] for d in q("SELECT code,name FROM departments")}
    for s in q("SELECT * FROM sources ORDER BY id"):
        s["stats"] = jloads(s["stats"], {})
        s["declared_name"] = names.get(s["declared_dept"])
        s["actual_name"] = names.get(s["actual_dept"])
        s["processes"] = q("SELECT p.process_id,p.name,m.role,m.similarity,m.heading FROM mappings m JOIN processes p ON p.id=m.process_id WHERE m.source_id=? ORDER BY m.id", (s["id"],))
        s["findings"] = q("SELECT id,kind,severity,title,status FROM findings WHERE source_id=? ORDER BY id", (s["id"],))
        out.append(s)
    return out


def users_list():
    return q("SELECT u.id,u.username,u.display_name,u.role,u.department_id,u.active,u.created_at,d.name AS department FROM users u LEFT JOIN departments d ON d.id=u.department_id ORDER BY u.id")


# ------------------------------------------------------------------ Excel register
def register_xlsx(user) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook()
    hdr_fill = PatternFill("solid", fgColor="1F4E79")

    def sheet(title, headers, rows):
        ws = wb.create_sheet(title)
        ws.append(headers)
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = hdr_fill
        for r in rows:
            ws.append(r)
        for i, h in enumerate(headers, 1):
            ws.column_dimensions[ws.cell(1, i).column_letter].width = min(60, max(14, len(h) + 4))
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
    wb.remove(wb.active)
    rows = _summary_rows(user)
    sheet("Ownership", ["Process ID", "Name", "Department", "Owner", "Reviewer", "Review months"],
          [[r["process_id"], r["name"], r["department"], r["owner"], r["reviewer"], ""] for r in rows])
    sheet("Master Process Inventory", ["Process ID", "Source Chart ID", "Name", "Department", "Type", "Countries", "Owner", "Version", "Status", "Published", "Has flowchart", "Flowchart validation", "Next review"],
          [[r["process_id"], r["chart_id"], r["name"], r["department"], r["kind"], r["countries"], r["owner"], r["version"], r["status_label"], r["published_version"] or "", "Yes" if r["has_diagram"] else "No", r["diagram_validation"] or "", r["next_review"] or ""] for r in rows])
    sheet("Source Document Mapping", ["Source file", "Source version", "Section", "Chart ID in source", "Process ID", "Role", "Similarity to primary"],
          [[m["filename"], m["version_text"], m["heading"], m["chart_id"], m["process_id"], m["role"], m["similarity"]] for m in q("SELECT s.filename,s.version_text,m.heading,m.chart_id,p.process_id,m.role,m.similarity FROM mappings m JOIN sources s ON s.id=m.source_id JOIN processes p ON p.id=m.process_id ORDER BY s.id,m.id")])
    sheet("Source Audit Register", ["File", "Declared dept", "Actual dept", "Cover title", "Version", "Confidence", "Sections", "Flowcharts", "Tables", "Open findings"],
          [[s["filename"], s["declared_name"], s["actual_name"], s["title"], s["version_text"], s["confidence"], s["stats"].get("sections"), s["stats"].get("diagrams"), s["stats"].get("tables"), sum(1 for f in s["findings"] if f["status"] == "open")] for s in sources_register()])
    sheet("Findings (Gaps & Conflicts)", ["#", "Kind", "Severity", "Status", "Source", "Process", "Title", "Detail", "Decision"],
          [[f["id"], f["kind"], f["severity"], f["status"], f["filename"], f["pid_text"], f["title"], f["detail"], f["decision"]] for f in findings()])
    sheet("Escalation & SLA", ["Process ID", "Department", "Stage", "Task / Reminder to", "Time period", "Escalation", "Previous SLA"],
          [[e["process_id"], e["department"], e["stage"], e["to"], e["time"], e["action"], e["sla"]] for e in escalation_report(user)])
    sheet("KPI Register", ["Process ID", "Department", "KPI", "Definition", "Target"], [[k["process_id"], k["department"], k["name"], k["definition"], k["target"]] for k in kpi_report(user)])
    sheet("Editable Flowchart Index", ["Diagram code", "Process ID", "Latest revision", "Validation", "Origin"],
          [[d["code"], d["pid"], d["ver_no"], d["validation"], d["origin"]] for d in q("SELECT d.code,p.process_id pid,dv.ver_no,dv.validation,dv.origin FROM diagrams d LEFT JOIN processes p ON p.id=d.process_id JOIN diagram_versions dv ON dv.diagram_id=d.id AND dv.ver_no=(SELECT MAX(ver_no) FROM diagram_versions WHERE diagram_id=d.id)")])
    sheet("Cross-Functional RACI", ["Process ID", "Activity", "R", "A", "C", "I"],
          [[r["process_id"], a["activity"], a["R"], a["A"], a["C"], a["I"]] for r in raci_report(user) for a in r["raci"]])
    sheet("Revision History", ["Process ID", "Version", "Status", "Author", "Created", "Published", "Summary"],
          [[v["process_id"], v["version"], v["status"], v["author"], v["created_at"], v["published_at"], v["change_summary"]] for v in q("SELECT p.process_id,v.* FROM process_versions v JOIN processes p ON p.id=v.process_id ORDER BY p.process_id,v.major,v.minor")])
    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


# ------------------------------------------------------------------ backup / restore
def make_backup() -> str:
    os.makedirs(config.BACKUP_DIR, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = os.path.join(config.BACKUP_DIR, f"mea_hub_backup_{stamp}.zip")
    tmp = os.path.join(config.BACKUP_DIR, f"_snap_{stamp}.sqlite3")
    dst = sqlite3.connect(tmp)
    db.db().backup(dst)                           # consistent online snapshot
    dst.close()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(tmp, "mea_hub.sqlite3")
        for folder, arc in ((config.ASSET_DIR, "assets"), (config.SOURCE_DIR, "sources")):
            for f in os.listdir(folder):
                z.write(os.path.join(folder, f), f"{arc}/{f}")
        z.writestr("MANIFEST.json", json.dumps(dict(created=svc.now(), app="MEA Process Hub", version="1")))
    os.remove(tmp)
    return path


def restore_backup(zip_path: str):
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        if "mea_hub.sqlite3" not in names or "MANIFEST.json" not in names:
            raise svc.Invalid("Not a MEA Process Hub backup.")
        for n in names:
            if n.startswith("/") or ".." in n.split("/"):
                raise svc.Invalid("Unsafe path in backup.")
        db.close_all_for_thread()
        for ext in ("", "-wal", "-shm"):
            if os.path.exists(config.DB_PATH + ext):
                os.remove(config.DB_PATH + ext)
        z.extract("mea_hub.sqlite3", config.DATA_DIR)
        os.replace(os.path.join(config.DATA_DIR, "mea_hub.sqlite3"), config.DB_PATH)
        for n in names:
            if n.startswith(("assets/", "sources/")) and not n.endswith("/"):
                target = os.path.join(config.DATA_DIR, n)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with z.open(n) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out)


# ------------------------------------------------------------------ reconciliation report (markdown)
def reconcile_markdown() -> str:
    import re
    clean = lambda n: re.sub(r"^[0-9a-f]{8}-", "", n or "")
    names = {d["code"]: d["name"] for d in q("SELECT code,name FROM departments")}
    out = ["# Source Reconciliation Report", "", f"Generated {svc.now()} by MEA Process Hub. Regenerate with `run.py --reconcile-report <file>`.", ""]
    srcs = sources_register()
    out += ["## 1. Source audit register", "", "| File | Cover title | Version | Declared (file name) | Actual content | Match | Confidence | Sections | Flowcharts | Tables | Processes created | Duplicate mappings |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for s in srcs:
        prim = sum(1 for p in s["processes"] if p["role"] == "primary")
        dup = sum(1 for p in s["processes"] if p["role"] == "duplicate")
        out.append(f"| {clean(s['filename'])} | {s['title'][:60]} | {s['version_text'] or '?'} | {s['declared_name']} | {s['actual_name']} | {'n/a' if not s['declared_dept'] else ('✔' if s['declared_dept'] == s['actual_dept'] else '✘ MISMATCH')} | {s['confidence']} | "
                   f"{s['stats'].get('sections')} | {s['stats'].get('diagrams')} | {s['stats'].get('tables')} | {prim} | {dup} |")
    out += ["", "## 2. Findings requiring a decision", ""]
    for sev in ("high", "medium", "low"):
        rows = [f for f in findings() if f["severity"] == sev and f["kind"] != "duplicate" or f["severity"] == sev and f["kind"] == "duplicate"]
        if not rows:
            continue
        out += [f"### {sev.title()} severity ({len(rows)})", "", "| Kind | Title | Detail | Status |", "|---|---|---|---|"]
        for f in rows:
            out.append(f"| {f['kind']} | {clean(f['title'])} | {clean(f['detail']).replace('|', '/').replace(chr(10), ' ')} | {f['status']} |")
        out.append("")
    out += ["## 3. Source → destination map (every extracted section is accounted for)", "", "| Source file | Source section | Chart ID in source | → Process ID | Role |", "|---|---|---|---|---|"]
    for m in q("SELECT s.filename,m.heading,m.chart_id,p.process_id,m.role FROM mappings m JOIN sources s ON s.id=m.source_id JOIN processes p ON p.id=m.process_id ORDER BY s.id,m.id"):
        out.append(f"| {clean(m['filename'])} | {m['heading']} | {m['chart_id'] or ''} | {m['process_id']} | {m['role']} |")
    out += ["", "## 4. Departments without documented processes (Documentation Required)", ""]
    for d in q("SELECT d.name FROM departments d WHERE NOT EXISTS (SELECT 1 FROM processes p WHERE p.department_id=d.id) ORDER BY d.sort"):
        out.append(f"- {d['name']}")
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------ register import (round-trip of the exported workbook)
def import_register(user, data: bytes) -> dict:
    """Apply an edited process-register workbook: sheets 'Ownership', 'Cross-Functional RACI', 'KPI Register'.
    Owner data is applied directly; RACI/KPI changes go into DRAFT revisions (never into published versions)."""
    from openpyxl import load_workbook
    if len(data) > 25 * 1024 * 1024 or data[:2] != b"PK":
        raise svc.Invalid("Not a valid .xlsx workbook.")
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception:
        raise svc.Invalid("The workbook could not be read.")
    report = dict(ownership=0, raci_processes=0, kpi_processes=0, errors=[])

    def rows(name):
        if name not in wb.sheetnames:
            return []
        it = wb[name].iter_rows(values_only=True)
        head = next(it, None)
        if not head:
            return []
        h = [str(c or "").strip().lower() for c in head]
        out = []
        for r in it:
            if r and any(c not in (None, "") for c in r):
                out.append({h[i]: ("" if v is None else str(v).strip()) for i, v in enumerate(r) if i < len(h)})
        return out[:5000]
    items = []
    for r in rows("Ownership"):
        if r.get("process id") and (r.get("owner") or r.get("reviewer") or r.get("review months")):
            items.append(dict(process_id=r["process id"], owner=r.get("owner"), reviewer=r.get("reviewer"), review_months=r.get("review months")))
    for it in items:
        try:
            res = svc.assign_ownership(user, [it])
            report["ownership"] += res["updated"]
        except (svc.NotFound, svc.Forbidden, svc.Invalid) as e:
            report["errors"].append(f"Ownership {it['process_id']}: {e}")
    groups = {"raci": {}, "kpis": {}}
    for r in rows("Cross-Functional RACI"):
        if r.get("process id") and r.get("activity"):
            groups["raci"].setdefault(r["process id"], []).append(dict(activity=r["activity"], R=r.get("r", ""), A=r.get("a", ""), C=r.get("c", ""), I=r.get("i", "")))
    for r in rows("KPI Register"):
        if r.get("process id") and r.get("kpi"):
            groups["kpis"].setdefault(r["process id"], []).append(dict(name=r["kpi"], definition=r.get("definition", ""), target=r.get("target", "")))
    for field, per in groups.items():
        for pid_text, table in per.items():
            try:
                p = svc.get_process(pid_text)
                cur = svc.open_version(p["id"]) or svc.latest_version(p["id"])
                content = dict(cur["content"])
                if content.get(field) == table:
                    continue
                content[field] = table
                svc.save_draft(pid_text, user, dict(content=content, change_summary=f"{field.upper()} loaded from register workbook", autosave_check=False))
                report["raci_processes" if field == "raci" else "kpi_processes"] += 1
            except (svc.NotFound, svc.Forbidden, svc.Invalid, svc.Conflict) as e:
                report["errors"].append(f"{field} {pid_text}: {e}")
    svc.audit(user, "register_imported", "system", None, json.dumps({k: v for k, v in report.items() if k != "errors"}) + f" errors={len(report['errors'])}")
    return report


def comments_xlsx(user) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    rows = svc.comments_register(user)
    wb = Workbook()
    ws = wb.active
    ws.title = "Audit comments"
    head = ["#", "Process ID", "Process", "Department", "Raised on version", "Current version", "Category", "Severity", "Section", "Status", "Author", "Raised at", "Comment", "Replies", "Resolution", "Resolved by", "Resolved at"]
    ws.append(head)
    for c_ in ws[1]:
        c_.font = Font(bold=True, color="FFFFFF")
        c_.fill = PatternFill("solid", fgColor="003594")
    for r in rows:
        ws.append([r["id"], r["pid_text"], r["pname"], r["department"], r["version_label"], r["current_version"], r["category"], r["severity"], r["section"], r["status"], r["author"],
                   r["created_at"], r["body"], r["replies"], r["resolution"], r["resolved_by"], r["resolved_at"]])
    for i, w in enumerate([6, 14, 34, 24, 10, 10, 14, 10, 18, 12, 14, 20, 60, 8, 50, 14, 20], 1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()
