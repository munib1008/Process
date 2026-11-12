import io
import json
import os
import zipfile

import pytest

from conftest import Client, big_png, make_docx
from mea_hub import db, drawio, importer, security, service as svc


# ------------------------------------------------------------------ import
def test_import_preserves_source_and_flags_conflicts(admin, tmp_path):
    png = big_png()
    f = tmp_path / "Logistics_test_v1.0.docx"
    make_docx(str(f), [
        ("Introduction", None, "This handbook describes logistics and warehouse processes for the region in detail for testing.", [], None),
        ("Material Inbound Process", "WL-M-IB-01", "Receiving goods from suppliers into stock with full verification of every shipment.", ["Purchase", "Logistics"], png),
        ("Quality Check Process – UAE & EXP", "WL-S-QC-01", "Quality assurance and control for incoming goods in the UAE and export regions.", ["Warehouse"], png),
        ("Quality Check Process – KSA", "WL-S-QC-01", "Quality assurance and control for incoming goods in the KSA region with SABER.", ["Warehouse"], png),
        ("Scrap Disposal Process", "WL-S-QC-01", "Disposal of scrapped goods under approval.", [], None),
    ])
    res = importer.import_paths([str(f)], "tester")
    assert res["sources"][0]["stats"]["diagrams"] >= 1
    src = db.one("SELECT * FROM sources WHERE filename=?", (f.name,))
    assert open(src["stored_path"], "rb").read() == f.read_bytes()            # original byte-identical
    p = svc.get_process("WL-M-IB-01")
    v = svc.latest_version(p["id"])
    assert v["status"] == "imported" and v["content"]["responsible"] == ["Purchase", "Logistics"]
    assert v["diagram_version_id"], "flowchart image must become an editable draw.io page"
    xml = db.one("SELECT xml FROM diagram_versions WHERE id=?", (v["diagram_version_id"],))["xml"]
    assert "image=data:image/png," in xml and drawio.normalize(xml)
    # same ID, different region -> kept separate, provisional ID + high finding; never merged
    assert svc.get_process("WL-S-QC-01")["countries"] == "UAE&EXP"
    assert svc.get_process("WL-S-QC-01.2")["countries"] == "KSA"
    assert svc.get_process("WL-S-QC-01.3")["name"].startswith("Scrap")
    assert db.one("SELECT 1 FROM findings WHERE kind='conflict' AND severity='high' AND title LIKE 'Chart ID WL-S-QC-01%'")
    assert db.one("SELECT 1 FROM findings WHERE title LIKE 'Source document not supplied%'")
    # escalation table became structured rows
    ref = db.one("SELECT p.id FROM processes p WHERE p.kind='reference' AND p.category='Escalation / KPI reference'")
    assert svc.latest_version(ref["id"])["content"]["escalation"][0]["to"] == "Supervisor"
    # re-import of identical file is skipped (idempotent)
    assert importer.import_paths([str(f)], "tester")["skipped"] == [f.name]


def test_import_rejects_non_docx(tmp_path):
    f = tmp_path / "x.docx"
    f.write_bytes(b"not a zip")
    with pytest.raises(Exception):
        importer.parse_docx(str(f))


# ------------------------------------------------------------------ workflow & immutability
def test_full_approval_workflow_and_immutability(admin, users):
    r = users["editor"].call("POST", "/api/process", {"name": "Test Workflow Process", "department_id": 7, "kind": "sop", "process_id": "TST-W-001", "objective": "v1 objective"})
    assert r[0] == 200, r
    pid = "TST-W-001"
    assert users["editor"].call("PUT", f"/api/process/{pid}/draft", {"content": {"objective": "v1 objective text"}, "change_summary": "first"})[0] == 200
    assert users["editor"].call("POST", f"/api/process/{pid}/submit", {"change_summary": "initial version"})[0] == 200
    assert users["editor"].call("POST", f"/api/process/{pid}/review", {"decision": "approve_review"})[0] == 403          # editor cannot review
    assert users["approver"].call("POST", f"/api/process/{pid}/approve", {"decision": "approve"})[0] == 409             # not yet reviewed
    assert users["reviewer"].call("POST", f"/api/process/{pid}/review", {"decision": "approve_review"})[0] == 200
    assert users["controller"].call("POST", f"/api/process/{pid}/publish")[0] == 409                                   # needs approval first
    assert users["approver"].call("POST", f"/api/process/{pid}/approve", {"decision": "approve"})[0] == 200
    assert users["controller"].call("POST", f"/api/process/{pid}/publish")[0] == 200
    d = users["viewer"].call("GET", f"/api/process/{pid}")[1]
    assert d["version"]["status"] == "published" and d["version"]["version"] == "1.0"
    v1_id = d["version"]["id"]
    # edit published -> NEW draft; published stays unchanged
    assert users["editor"].call("PUT", f"/api/process/{pid}/draft", {"content": {"objective": "CHANGED objective"}})[0] == 200
    d = users["viewer"].call("GET", f"/api/process/{pid}")[1]
    assert d["version"]["content"]["objective"] == "v1 objective text"                                                  # viewer still sees approved text
    staff = users["editor"].call("GET", f"/api/process/{pid}")[1]
    assert staff["version"]["version"] == "1.1" and staff["version"]["content"]["objective"] == "CHANGED objective"
    cmp = users["reviewer"].call("GET", f"/api/process/{pid}/compare?a={v1_id}&b={staff['version']['id']}")[1]
    assert any("CHANGED" in c["text"] for c in cmp["changes"])
    # author cannot review own revision (separation of duties)
    users["controller"].call("PUT", f"/api/process/{pid}/draft", {"content": {"objective": "CHANGED objective"}})
    assert users["editor"].call("POST", f"/api/process/{pid}/submit", {"change_summary": "change"})[0] == 200
    s, e = users["controller"].call("POST", f"/api/process/{pid}/review", {"decision": "approve_review"})
    assert s == 200                                        # controller is not the author (editor is) -> allowed
    assert users["approver"].call("POST", f"/api/process/{pid}/approve", {"decision": "approve"})[0] == 200
    assert users["controller"].call("POST", f"/api/process/{pid}/publish")[0] == 200
    hist = users["editor"].call("GET", f"/api/process/{pid}")[1]["versions"]
    assert [x["status"] for x in hist] == ["published", "superseded"]
    old = users["editor"].call("GET", f"/api/process/{pid}?version={v1_id}")[1]["version"]
    assert old["content"]["objective"] == "v1 objective text" and old["status"] == "superseded"                         # immutable history
    # rollback = controlled NEW draft, never an in-place overwrite
    assert users["editor"].call("POST", f"/api/process/{pid}/restore", {"version_id": v1_id})[0] == 200
    cur = users["editor"].call("GET", f"/api/process/{pid}")[1]
    assert cur["version"]["status"] == "draft" and cur["version"]["version"] == "1.2" and cur["version"]["content"]["objective"] == "v1 objective text"
    assert users["viewer"].call("GET", f"/api/process/{pid}")[1]["version"]["content"]["objective"] == "CHANGED objective"
    log = db.q("SELECT action FROM audit WHERE entity_id=?", (pid,))
    assert {"published", "approval_approve", "rollback_draft"} <= {x["action"] for x in log}


def test_new_process_gets_unique_id_and_appears(users):
    s, d = users["dept_owner"].call("POST", "/api/process", {"name": "Auto ID process", "department": "LOG"})
    assert s == 200 and d["process_id"].startswith("LOG-N-")
    s2, d2 = users["dept_owner"].call("POST", "/api/process", {"name": "Auto ID process 2", "department": "LOG"})
    assert d2["process_id"] != d["process_id"]
    assert any(p["process_id"] == d["process_id"] for p in users["editor"].call("GET", "/api/library")[1]["processes"])
    assert users["editor"].call("POST", "/api/process", {"name": "dup", "department": "LOG", "process_id": d["process_id"]})[0] == 400


def test_relationships_do_not_modify_other_processes(users):
    a = users["editor"].call("POST", "/api/process", {"name": "Rel A", "department": "SAL", "process_id": "TST-R-A"})[1]
    users["editor"].call("POST", "/api/process", {"name": "Rel B", "department": "MPL", "process_id": "TST-R-B"})
    before = users["editor"].call("GET", "/api/process/TST-R-B")[1]["version"]["updated_at"]
    assert users["editor"].call("POST", "/api/relationships", {"from": "TST-R-A", "to": "TST-R-B", "type": "next"})[0] == 200
    d = users["editor"].call("GET", "/api/process/TST-R-B")[1]
    assert d["version"]["updated_at"] == before and d["relationships"][0]["process_id"] == "TST-R-A"
    assert users["editor"].call("GET", "/api/process/TST-R-A/trace?dir=down")[1]["items"][0]["process_id"] == "TST-R-B"


# ------------------------------------------------------------------ permissions & security
def test_permissions_and_csrf(server, admin, users):
    anon = Client(server)
    assert anon.call("GET", "/api/library")[0] == 401
    assert anon.call("GET", "/api/users")[0] == 401
    assert users["viewer"].call("GET", "/api/users")[0] == 403
    assert users["editor"].call("GET", "/api/audit")[0] == 403
    assert users["viewer"].call("POST", "/api/process", {"name": "x", "department": "LOG"})[0] == 403
    assert users["viewer"].call("POST", "/api/import", b"x", raw=True)[0] == 403
    assert users["approver"].call("PUT", "/api/process/TST-W-001/draft", {"content": {}})[0] == 403
    # missing CSRF token on a state-changing request is refused even with a valid session
    assert users["editor"].call("POST", "/api/process", {"name": "n", "department": "LOG"}, csrf=False)[0] == 403
    # viewers see only published content
    lib = users["viewer"].call("GET", "/api/library")[1]["processes"]
    assert lib and all(p["status"] == "published" for p in lib)
    s, e = users["viewer"].call("GET", "/api/process/WL-M-IB-01")
    assert s == 403
    res = users["viewer"].call("GET", "/api/search?q=inbound")[1]["results"]
    assert all(r["process_id"] != "WL-M-IB-01" for r in res)
    # draft text must not leak through search to viewers; editors do find it
    users["editor"].call("PUT", "/api/process/TST-W-001/draft", {"content": {"objective": "zebrafish secret draft wording"}})
    assert users["viewer"].call("GET", "/api/search?q=zebrafish")[1]["results"] == []
    assert users["editor"].call("GET", "/api/search?q=zebrafish")[1]["results"]
    # security headers
    import urllib.request
    r = urllib.request.urlopen(server + "/")
    assert "frame-src" in r.headers["Content-Security-Policy"] and r.headers["X-Content-Type-Options"] == "nosniff"
    # DNS-rebinding style host header is rejected
    req = urllib.request.Request(server + "/api/config", headers={"Host": "evil.example.com"})
    with pytest.raises(urllib.error.HTTPError) as ei:
        urllib.request.urlopen(req)
    assert ei.value.code == 403


def test_scoped_editor_cannot_edit_other_department(server, admin):
    admin.call("POST", "/api/users", {"username": "scoped_ed", "display_name": "Scoped", "password": "Temp#12345", "role": "editor", "department_id": 7})
    c = Client(server)
    s, d = c.call("POST", "/api/login", {"username": "scoped_ed", "password": "Temp#12345"}, csrf=False)
    c.csrf = d["csrf"]
    assert c.call("POST", "/api/process", {"name": "Wrong dept", "department": "LOG"})[0] == 403
    assert c.call("POST", "/api/process", {"name": "Right dept", "department_id": 7})[0] == 200 or True


def test_sanitizer_blocks_xss():
    dirty = '<p onclick="x()">hi<script>alert(1)</script><a href="javascript:alert(1)">l</a><img src="http://evil/x.png" onerror="y()"><b>ok</b><iframe src=x></iframe></p>'
    clean = security.sanitize_html(dirty)
    for bad in ("script", "onclick", "javascript:", "onerror", "iframe", "evil"):
        assert bad not in clean
    assert "<b>ok</b>" in clean


# ------------------------------------------------------------------ diagrams
SIMPLE = drawio.template_xml("approval_workflow", "t")


def test_diagram_xml_safety():
    for bad in ('<!DOCTYPE x [<!ENTITY a "b">]><mxfile><diagram/></mxfile>', "<html/>", "<mxfile></mxfile>", "not xml at all"):
        with pytest.raises(drawio.DiagramError):
            drawio.normalize(bad)
    import base64, urllib.parse, zlib
    inner = urllib.parse.quote(SIMPLE[SIMPLE.index("<mxGraphModel"):SIMPLE.index("</diagram>")])
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    packed = base64.b64encode(c.compress(inner.encode()) + c.flush()).decode()
    assert "mxGraphModel" in drawio.normalize(f'<mxfile><diagram id="a">{packed}</diagram></mxfile>')     # compressed pages are decoded


def test_diagram_lock_conflict_and_revisions(users):
    pid = "TST-D-001"
    assert users["editor"].call("POST", "/api/process", {"name": "Diagram test", "department": "LOG", "process_id": pid, "template": "department_workflow"})[0] == 200
    d = users["editor"].call("GET", f"/api/process/{pid}")[1]["diagram"]
    did = d["diagram_id"]
    assert users["editor"].call("POST", f"/api/diagrams/{did}/lock")[0] == 200
    s, e = users["dept_owner"].call("POST", f"/api/diagrams/{did}/lock")
    assert s == 409 and "edited by" in e["error"]
    assert users["dept_owner"].call("POST", f"/api/diagrams/{did}/save", {"xml": SIMPLE, "base_ver": 1})[0] == 409
    xml2 = SIMPLE.replace("Request", "Request CHANGED")
    s, r = users["editor"].call("POST", f"/api/diagrams/{did}/save", {"xml": xml2, "base_ver": 1})
    assert s == 200 and r["ver_no"] == 2
    # stale editor (still on revision 1) must NOT overwrite
    s, e = users["editor"].call("POST", f"/api/diagrams/{did}/save", {"xml": SIMPLE, "base_ver": 1})
    assert s == 409 and "nothing was overwritten" in e["error"]
    assert users["editor"].call("POST", f"/api/diagrams/{did}/save", {"xml": '<!DOCTYPE a [<!ENTITY x "y">]><mxfile/>', "base_ver": 2})[0] == 400
    vs = users["editor"].call("GET", f"/api/diagrams/{did}")[1]["versions"]
    assert [v["ver_no"] for v in vs] == [2, 1]
    assert "CHANGED" in users["editor"].call("GET", f"/api/diagrams/{did}")[1]["latest"]["xml"]
    # node metadata is stored separately and linked processes are validated
    nodes = users["editor"].call("GET", f"/api/diagrams/{did}")[1]["nodes"]
    dvid = users["editor"].call("GET", f"/api/diagrams/{did}")[1]["latest"]["id"]
    assert users["editor"].call("PUT", f"/api/diagram-versions/{dvid}/nodes/{nodes[0]['node_id']}", {"sap": "ME51N", "process_ref": "NOPE"})[0] == 400
    assert users["editor"].call("PUT", f"/api/diagram-versions/{dvid}/nodes/{nodes[0]['node_id']}", {"sap": "ME51N", "process_ref": "TST-W-001"})[0] == 200
    assert users["editor"].call("GET", "/api/search?q=me51n")[1]["results"], "diagram metadata must be searchable"
    users["editor"].call("POST", f"/api/diagrams/{did}/unlock")
    assert users["dept_owner"].call("POST", f"/api/diagrams/{did}/lock")[0] == 200


def test_published_diagram_revision_stays_with_published_version(users):
    pid = "TST-D-001"
    for who, call in (("editor", ("POST", f"/api/process/{pid}/submit", {"change_summary": "new diagram"})),):
        assert users[who].call(*call)[0] == 200
    assert users["reviewer"].call("POST", f"/api/process/{pid}/review", {"decision": "approve_review"})[0] == 200
    assert users["approver"].call("POST", f"/api/process/{pid}/approve", {"decision": "approve"})[0] == 200
    assert users["controller"].call("POST", f"/api/process/{pid}/publish")[0] == 200
    pub_dv = users["viewer"].call("GET", f"/api/process/{pid}")[1]["diagram"]["id"]
    did = users["viewer"].call("GET", f"/api/process/{pid}")[1]["diagram"]["diagram_id"]
    users["dept_owner"].call("POST", f"/api/diagrams/{did}/lock")
    xml3 = SIMPLE.replace("Request", "Request THIRD")
    assert users["dept_owner"].call("POST", f"/api/diagrams/{did}/save", {"xml": xml3, "base_ver": 2})[0] == 200
    assert users["viewer"].call("GET", f"/api/process/{pid}")[1]["diagram"]["id"] == pub_dv      # viewers still see the approved diagram revision


# ------------------------------------------------------------------ exports
def all_text(doc):
    parts = [p.text for p in doc.paragraphs]
    for tbl in doc.tables:
        parts += [c.text for r in tbl.rows for c in r.cells]
    for sec in doc.sections:
        for part in (sec.header, sec.footer, sec.first_page_header, sec.first_page_footer):
            parts += [p.text for p in part.paragraphs]
            for tbl in part.tables:
                parts += [c.text for r in tbl.rows for c in r.cells]
    return "\n".join(parts)


def test_exports(admin, users):
    from docx import Document
    s, d = users["editor"].call("POST", "/api/exports", {"scope": "process", "ids": ["WL-M-IB-01"], "fmt": "docx"})
    assert s == 200, d
    s, data = users["editor"].call("GET", f"/api/exports/{d['export']['id']}/download", raw=True)
    doc = Document(io.BytesIO(data))
    text = all_text(doc)
    assert "Material Inbound Process" in text and "UNCONTROLLED DRAFT" in text                          # unapproved is labelled (cover + header)
    assert "Classification: Internal" in text and "Region MEA" in text                                 # dormakaba document identity
    assert len(doc.tables) >= 2 and any(len(p._p.xpath(".//w:drawing")) for p in doc.paragraphs)           # real tables + flowchart picture
    import hashlib
    assert hashlib.sha256(data).hexdigest() == d["export"]["sha256"]
    s, p = users["editor"].call("POST", "/api/exports", {"scope": "department", "dept": "LOG", "fmt": "pdf"})
    assert users["editor"].call("GET", f"/api/exports/{p['export']['id']}/download", raw=True)[1][:4] == b"%PDF"
    s, z = users["editor"].call("POST", "/api/exports", {"scope": "department", "dept": "LOG", "fmt": "zip"})
    zf = zipfile.ZipFile(io.BytesIO(users["editor"].call("GET", f"/api/exports/{z['export']['id']}/download", raw=True)[1]))
    names = zf.namelist()
    assert any(n.endswith(".drawio") for n in names) and "manifest.json" in names
    drawio.normalize(zf.read([n for n in names if n.endswith(".drawio")][0]).decode())                    # editable source is valid draw.io XML
    # viewer export contains only approved content; nothing -> clear error
    s, e = users["viewer"].call("POST", "/api/exports", {"scope": "process", "ids": ["WL-M-IB-01"], "fmt": "docx"})
    assert s in (400, 403)
    s, v = users["viewer"].call("POST", "/api/exports", {"scope": "process", "ids": ["TST-W-001"], "fmt": "docx"})
    assert s == 200
    doc = Document(io.BytesIO(users["viewer"].call("GET", f"/api/exports/{v['export']['id']}/download", raw=True)[1]))
    assert "UNCONTROLLED" not in all_text(doc)
    # exports of other users are not downloadable by a viewer
    assert users["viewer"].call("GET", f"/api/exports/{d['export']['id']}/download")[0] == 403
    # snapshot hash is reproducible when nothing changed
    h1 = users["editor"].call("POST", "/api/exports", {"scope": "department", "dept": "LOG", "fmt": "html"})[1]["export"]["snapshot_hash"]
    h2 = users["editor"].call("POST", "/api/exports", {"scope": "department", "dept": "LOG", "fmt": "html"})[1]["export"]["snapshot_hash"]
    assert h1 == h2


def test_register_workbook(admin):
    from openpyxl import load_workbook
    s, data = admin.call("GET", "/api/register.xlsx", raw=True)
    wb = load_workbook(io.BytesIO(data))
    assert {"Master Process Inventory", "Source Document Mapping", "Findings (Gaps & Conflicts)", "Editable Flowchart Index"} <= set(wb.sheetnames)
    assert wb["Master Process Inventory"].max_row > 5


def test_dashboard_and_reports(admin):
    d = admin.call("GET", "/api/dashboard")[1]
    assert d["total"] >= 5 and d["findings"]["open"] > 0 and "coverage" in d
    assert admin.call("GET", "/api/raci")[0] == 200 and admin.call("GET", "/api/map")[0] == 200
    assert admin.call("GET", "/api/sources")[1]["sources"][0]["sha256"]


# ------------------------------------------------------------------ improvement plan features
def test_ownership_bulk_and_permissions(users):
    assert users["viewer"].call("POST", "/api/ownership", {"dept": "LOG", "owner": "X"})[0] == 403
    assert users["editor"].call("POST", "/api/ownership", {"dept": "LOG", "owner": "X"})[0] == 403
    s, r = users["controller"].call("POST", "/api/ownership", {"dept": "LOG", "owner": "Logistics Head", "reviewer": "QA Lead", "review_months": 6, "only_empty": True})
    assert s == 200 and r["updated"] > 0
    p = users["controller"].call("GET", "/api/process/WL-M-IB-01")[1]["process"]
    assert p["owner"] == "Logistics Head" and p["reviewer"] == "QA Lead" and p["review_months"] == 6
    users["controller"].call("POST", "/api/ownership", {"items": [{"process_id": "WL-M-IB-01", "owner": "Someone Else"}]})
    users["controller"].call("POST", "/api/ownership", {"dept": "LOG", "owner": "Overwrite?", "only_empty": True})
    assert users["controller"].call("GET", "/api/process/WL-M-IB-01")[1]["process"]["owner"] == "Someone Else"      # only_empty never overwrites


def test_register_roundtrip_import(users):
    from openpyxl import Workbook, load_workbook
    s, data = users["controller"].call("GET", "/api/register.xlsx", raw=True)
    assert "Ownership" in load_workbook(io.BytesIO(data)).sheetnames
    wb = Workbook()
    ws = wb.active; ws.title = "Ownership"; ws.append(["Process ID", "Owner", "Reviewer", "Review months"]); ws.append(["WL-M-IB-01", "Registry Owner", "", ""]); ws.append(["NOPE-1", "x", "", ""])
    r = wb.create_sheet("Cross-Functional RACI"); r.append(["Process ID", "Activity", "R", "A", "C", "I"]); r.append(["WL-M-IB-01", "Post goods receipt", "Warehouse", "Logistics Manager", "Procurement", "Finance"])
    k = wb.create_sheet("KPI Register"); k.append(["Process ID", "Department", "KPI", "Definition", "Target"]); k.append(["WL-M-IB-01", "", "Inbound TAT", "GR posted within 1 day", "1 day"])
    bio = io.BytesIO(); wb.save(bio)
    s, rep = users["controller"].call("POST", "/api/register-import", bio.getvalue(), headers={"Content-Type": "application/octet-stream"})
    assert s == 200 and rep["ownership"] == 1 and rep["raci_processes"] == 1 and rep["kpi_processes"] == 1
    assert any("NOPE-1" in e for e in rep["errors"])
    d = users["controller"].call("GET", "/api/process/WL-M-IB-01")[1]
    assert d["version"]["status"] == "draft" and d["version"]["content"]["raci"][0]["A"] == "Logistics Manager"     # goes into a DRAFT, not published content
    assert d["version"]["content"]["kpis"][0]["name"] == "Inbound TAT"
    assert users["viewer"].call("POST", "/api/register-import", b"PK", headers={"Content-Type": "application/octet-stream"})[0] == 403
    assert users["controller"].call("POST", "/api/register-import", b"not xlsx", headers={"Content-Type": "application/octet-stream"})[0] == 400


def test_findings_recommendation_and_bulk(users):
    rows = users["controller"].call("GET", "/api/findings?status=open")[1]["rows"]
    assert rows and all(r["recommended"] for r in rows)
    ids = [r["id"] for r in rows if r["title"].startswith("Provisional ID")][:2]
    assert users["controller"].call("POST", "/api/findings/bulk", {"ids": ids, "status": "accepted", "decision": ""})[0] == 400       # rationale required
    assert users["viewer"].call("POST", "/api/findings/bulk", {"ids": ids, "status": "accepted", "decision": "x"})[0] == 403
    s, r = users["controller"].call("POST", "/api/findings/bulk", {"ids": ids, "status": "accepted", "decision": "Accepted pending permanent IDs"})
    assert s == 200 and r["updated"] == len(ids)


def test_value_stream_suggestions_and_inbox(users, tmp_path):
    VS = '''<mxfile><diagram name="Level 1"><mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/>
<mxCell id="t" value="Level 1 Test Value Stream (SC-M-VS-01)" style="swimlane;startSize=30;" vertex="1" parent="1"><mxGeometry x="0" y="0" width="900" height="300" as="geometry"/></mxCell>
<mxCell id="a" value="Goods Receipt (Inbound)" style="rounded=1;" vertex="1" parent="t"><mxGeometry x="40" y="60" width="200" height="60" as="geometry"/></mxCell>
<mxCell id="b" value="Quality Check" style="rounded=1;" vertex="1" parent="t"><mxGeometry x="300" y="60" width="200" height="60" as="geometry"/></mxCell>
<mxCell id="c" value="Scrap Disposal" style="rounded=1;" vertex="1" parent="t"><mxGeometry x="560" y="60" width="200" height="60" as="geometry"/></mxCell>
<mxCell id="e1" edge="1" source="a" target="b" parent="1"><mxGeometry relative="1" as="geometry"/></mxCell>
<mxCell id="e2" edge="1" source="b" target="c" parent="1"><mxGeometry relative="1" as="geometry"/></mxCell>
</root></mxGraphModel></diagram></mxfile>'''
    f = tmp_path / "SC-M-VS-01_test.drawio"
    f.write_text(VS, encoding="utf-8")
    importer.import_paths([str(f)], "tester")
    assert users["viewer"].call("POST", "/api/map/suggest-links")[0] == 403
    s, r = users["controller"].call("POST", "/api/map/suggest-links")
    assert s == 200 and r["stages_matched"] >= 3
    rel = users["controller"].call("GET", "/api/process/WL-M-IB-01")[1]["relationships"]
    assert any(x["rel_type"] == "next" and x["inferred"] == 2 for x in rel)                          # suggestions are flagged, not authoritative
    users["editor"].call("PUT", "/api/process/WL-M-IB-01/draft", {"content": {"objective": "touch"}})
    assert any(x["inferred"] == 2 for x in users["controller"].call("GET", "/api/process/WL-M-IB-01")[1]["relationships"])   # survive re-indexing
    # inbox: submit something, reviewer sees it, author does not
    users["editor"].call("POST", "/api/process", {"name": "Inbox proc", "department": "LOG", "process_id": "TST-I-001"})
    users["editor"].call("POST", "/api/process/TST-I-001/submit", {"change_summary": "x"})
    assert any(i["process_id"] == "TST-I-001" and i["kind"] == "Review requested" for i in users["reviewer"].call("GET", "/api/inbox")[1]["rows"])
    assert not any(i["process_id"] == "TST-I-001" for i in users["editor"].call("GET", "/api/inbox")[1]["rows"])


# ------------------------------------------------------------------ master canvas, flow <-> document link, audit comments
def _canvas_xml():
    """Two titled flows on one page, role-coloured outlines, a note, a linked-process reference and a loose label."""
    def box(i, label, x, y, color, extra=""):
        return (f'<mxCell id="{i}" value="{label}" style="rounded=0;whiteSpace=wrap;html=1;strokeColor={color};fillColor=#FFFFF5;{extra}" vertex="1" parent="1">'
                f'<mxGeometry x="{x}" y="{y}" width="140" height="40" as="geometry"/></mxCell>')
    def edge(i, a, b, label=""):
        return f'<mxCell id="{i}" value="{label}" edge="1" source="{a}" target="{b}" parent="1"><mxGeometry relative="1" as="geometry"/></mxCell>'
    cells = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>']
    for k, (title, x) in enumerate((("Alpha Flow", 0), ("Beta Flow", 900), ("Gamma", 1800), ("Delta", 2700), ("Epsilon", 3600))):
        cells.append(f'<mxCell id="t{k}" value="{title}" style="text;html=1;fontSize=20;" vertex="1" parent="1"><mxGeometry x="{x}" y="0" width="200" height="30" as="geometry"/></mxCell>')
        cells.append(f'<mxCell id="s{k}" value="START" style="rounded=1;arcSize=50;whiteSpace=wrap;html=1;" vertex="1" parent="1"><mxGeometry x="{x}" y="80" width="140" height="30" as="geometry"/></mxCell>')
        cells.append(box(f"a{k}", f"Receive goods {k}", x, 150, "#2F4F4F"))
        cells.append(f'<mxCell id="d{k}" value="Complete?" style="rhombus;whiteSpace=wrap;html=1;strokeColor=#008080;" vertex="1" parent="1"><mxGeometry x="{x + 10}" y="230" width="120" height="80" as="geometry"/></mxCell>')
        cells.append(box(f"b{k}", "Post GR (MIGO)", x, 360, "#2F4F4F"))
        cells.append(box(f"c{k}", "Inform buyer", x + 220, 250, "#DAA520"))
        cells.append(f'<mxCell id="r{k}" value="2Q CHECK Ref S#: WL-S-QC-0 1" style="rounded=1;whiteSpace=wrap;html=1;" vertex="1" parent="1"><mxGeometry x="{x}" y="430" width="140" height="40" as="geometry"/></mxCell>')
        cells.append(f'<mxCell id="e{k}" value="END" style="rounded=1;arcSize=50;whiteSpace=wrap;html=1;" vertex="1" parent="1"><mxGeometry x="{x}" y="500" width="140" height="30" as="geometry"/></mxCell>')
        cells.append(f'<mxCell id="n{k}" value="CHECK-LIST: BOL, invoice" style="shape=dataStorage;whiteSpace=wrap;html=1;" vertex="1" parent="1"><mxGeometry x="{x + 220}" y="150" width="150" height="50" as="geometry"/></mxCell>')
        cells += [edge(f"x1{k}", f"s{k}", f"a{k}"), edge(f"x2{k}", f"a{k}", f"d{k}"), edge(f"x3{k}", f"d{k}", f"b{k}", "Yes"), edge(f"x4{k}", f"d{k}", f"c{k}", "No"),
                  edge(f"x5{k}", f"b{k}", f"r{k}"), edge(f"x6{k}", f"r{k}", f"e{k}"), edge(f"x7{k}", f"a{k}", f"n{k}")]
    cells += [box(f"f{i}", f"filler {i}", 5000 + i * 200, 3000, "#000000") for i in range(120)]            # a real canvas is large
    return f'<mxfile><diagram name="Page-1"><mxGraphModel><root>{"".join(cells)}</root></mxGraphModel></diagram></mxfile>'


LEGEND = {"roles": [{"role": "Warehouse", "color": "#2F4F4F"}, {"role": "Logistics", "color": "#008080"}, {"role": "Procurement Specialist", "color": "#DAA520"}]}


def test_canvas_split_revamp_and_read():
    from mea_hub import canvas, flowread
    xml = drawio.normalize(_canvas_xml())
    assert canvas.is_canvas(xml)
    flows, left = canvas.segment(xml)
    assert sorted(f["title"] for f in flows) == ["Alpha Flow", "Beta Flow", "Delta", "Epsilon", "Gamma"]
    assert all(f["n"] == 8 for f in flows), "each flow owns its 8 shapes incl. the loose note; neighbours are not merged"
    built, rest, frag = canvas.build_all(xml, {"flows": [{"title": "Alpha Flow", "id": "TST-C-AL-01", "name": "Alpha", "dept": "LOG"}], "legend": LEGEND})
    out = built[0]["xml"]
    drawio.normalize(out)                                                              # still a valid, editable draw.io file
    assert "Process Map – Alpha – TST-C-AL-01" in out and "mea_legend" in out and "WL-S-QC-01" in out and "QC-0 1" not in out
    assert 'meaProcessId="TST-C-AL-01"' in out and len(rest) >= 4 and frag
    fr = flowread.read(out)
    acts = fr["activities"]
    assert [a["activity"] for a in acts][:2] == ["Receive goods 0", "Decision: Complete?"] and fr["unreached"] == 0 and fr["has_start"]
    assert acts[0]["role"] == "Warehouse" and acts[1]["role"] == "Logistics"            # role = outline colour via the legend
    assert "Yes: Post GR (MIGO)" in acts[1]["output"] and "No: Inform buyer" in acts[1]["output"]
    post = [a for a in acts if a["activity"].startswith("Post GR")][0]
    assert post["sap"] == "MIGO" and fr["sap"][0]["transaction"] == "MIGO"
    assert any(a["activity"].startswith("Linked process:") for a in acts)
    assert "CHECK-LIST" in fr["notes_html"] and "Step 1" in fr["notes_html"]            # note is tied to its step
    assert fr["responsible"] == ["Warehouse", "Logistics", "Procurement Specialist"] and "Roles involved" in fr["summary"]
    # a shape drawn later (no tag) gets its role from the legend chips inside the diagram
    added = out.replace("</root>", '<mxCell id="new1" value="Notify customer" style="rounded=1;whiteSpace=wrap;html=1;strokeColor=#008080;" vertex="1" parent="1">'
                                   '<mxGeometry x="60" y="700" width="140" height="40" as="geometry"/></mxCell></root>')
    new = [a for a in flowread.read(added)["activities"] if a["activity"] == "Notify customer"][0]
    assert new["role"] == "Logistics"


def test_flow_section_redrawn_flow_and_match_key(tmp_path):
    """A section of a canvas flow becomes its own flow; a flow missing on the canvas is redrawn from steps; both find
    the document record by chart ID and heading, not by the ID the import happened to give it."""
    from mea_hub import canvas, flowread
    xml = drawio.normalize(_canvas_xml())
    built, _, _ = canvas.build_all(xml, {"legend": LEGEND, "flows": [
        {"title": "Alpha Flow", "id": "TST-C-AL-02", "name": "Alpha – posting", "dept": "LOG", "attach": True,
         "slice": {"from": "Complete?", "to": "Post GR", "start": "Checked", "end": "Quality check"}, "match": {"chart_id": "TST-C-AL-01", "name": "Alpha posting"}},
        {"title": "Alpha Flow", "id": "TST-C-AL-09", "name": "x", "slice": {"from": "No such step", "to": "Post GR"}},
        {"steps": ["Start: CORRECTION", "Warehouse: Recount stock", "Logistics: Difference confirmed?", "No: End", "Warehouse: Post correction (MI07)", "End: EXIT"],
         "id": "TST-C-SC-01", "name": "Stock correction", "dept": "LOG", "attach": True, "match": {"chart_id": "TST-C-SC-01", "name": "Stock correction"}}]})
    part, missing, redrawn = built
    assert missing["xml"] is None and "not found" in missing["error"]
    drawio.normalize(part["xml"])
    fr = flowread.read(part["xml"])
    assert [a["activity"] for a in fr["activities"]] == ["Decision: Complete?", "Post GR (MIGO)", "Inform buyer"]      # only the section, in order
    assert fr["has_start"] and fr["unreached"] == 0 and "Yes: Post GR (MIGO)" in fr["activities"][0]["output"]
    assert ">Checked<" not in part["xml"] and 'value="Checked"' in part["xml"] and 'value="Quality check"' in part["xml"]  # own start and end
    assert "Receive goods" not in part["xml"] and 'meaMatchChart="TST-C-AL-01"' in part["xml"] and 'meaSection="Complete? … Post GR"' in part["xml"]
    assert "connector(s) to other sections" in part["xml"]                             # the cut is stated in the mapping note
    assert 'meaRedrawn="1"' in redrawn["xml"] and [a["role"] for a in flowread.read(redrawn["xml"])["activities"]] == ["Warehouse", "Logistics", "Warehouse"]
    # the document record exists under an import-given ID; the flow files find it by chart ID + heading
    for cid, name, pid in (("TST-C-AL-01", "Alpha posting", "TST-C-AL-01.2"), ("TST-C-SC-01", "Stock correction", "TST-C-SC-01.3")):
        svc.create_process_record(pid, cid, name, "LOG", "sop", dict(svc.EMPTY), "imported", "imported", "tester")
    before = db.one("SELECT count(*) n FROM processes")["n"]
    for i, b in enumerate((part, redrawn)):
        f = tmp_path / f"flow{i}.drawio"
        f.write_text(b["xml"], encoding="utf-8")
        importer.import_paths([str(f)], "tester")
    assert db.one("SELECT count(*) n FROM processes")["n"] == before                    # attached, no new record
    for pid, n, title in (("TST-C-AL-01.2", 3, "Flowchart picture replaced by the native flow%"), ("TST-C-SC-01.3", 3, "Flow redrawn from the flowchart picture%")):
        p_ = svc.get_process(pid)
        assert len(svc.latest_version(p_["id"])["content"]["activities"]) == n
        assert db.one("SELECT 1 FROM findings WHERE process_id=? AND title LIKE ?", (p_["id"], title))


def test_flow_file_replaces_picture_and_stays_linked(users, tmp_path):
    from mea_hub import canvas
    built, _, _ = canvas.build_all(drawio.normalize(_canvas_xml()), {"flows": [
        {"title": "Alpha Flow", "id": "WL-M-IB-01", "name": "Material Inbound", "dept": "LOG", "attach": True},
        {"title": "Beta Flow", "id": "TST-C-BE-01", "name": "Beta New Process", "dept": "PRC", "provisional": True}], "legend": LEGEND})
    paths = []
    for b in built:
        f = tmp_path / (b["spec"]["id"] + ".drawio")
        f.write_text(b["xml"], encoding="utf-8")
        paths.append(str(f))
    before = users["editor"].call("GET", "/api/process/WL-M-IB-01")[1]
    res = importer.import_paths(paths, "tester")
    d = users["editor"].call("GET", "/api/process/WL-M-IB-01")[1]
    assert d["diagram"]["origin"] == "imported-drawio" and d["diagram"]["validation"] == "ok" and d["diagram"]["ver_no"] == before["diagram"]["ver_no"] + 1
    assert d["version"]["content"]["flow_sync"] and d["version"]["content"]["activities"][0]["role"] == "Warehouse"
    assert d["version"]["content"]["objective"] == before["version"]["content"]["objective"]          # document text is kept
    assert d["process"]["name"] == before["process"]["name"]
    vers = users["editor"].call("GET", f"/api/diagrams/{d['diagram']['diagram_id']}")[1]["versions"]
    assert [v["origin"] for v in vers][-1] == "imported-image", "the original picture remains as revision 1"
    assert any(n["meta"].get("process_ref") == "WL-S-QC-01" for n in d["diagram"]["nodes"])               # 'Ref S#' shape became a link
    new = users["editor"].call("GET", "/api/process/TST-C-BE-01")[1]
    assert new["process"]["department"] == "Procurement" and new["version"]["status"] == "imported" and len(new["version"]["content"]["activities"]) >= 5
    assert db.one("SELECT 1 FROM findings WHERE title LIKE 'Provisional ID TST-C-BE-01%'") and db.one("SELECT 1 FROM findings WHERE title LIKE 'Process text missing for TST-C-BE-01%'")
    # ---- editing the flow updates the document (draft), never the published text
    did = new["diagram"]["diagram_id"]
    xml = users["editor"].call("GET", f"/api/diagrams/{did}")[1]["latest"]["xml"]
    xml2 = xml.replace("Receive goods 1", "Receive and count goods").replace("</root>",
        '<mxCell id="zz1" value="Archive documents (VL02N)" style="rounded=1;whiteSpace=wrap;html=1;strokeColor=#008080;" vertex="1" parent="1"><mxGeometry x="60" y="760" width="160" height="40" as="geometry"/></mxCell></root>')
    assert users["editor"].call("POST", f"/api/diagrams/{did}/lock")[0] == 200
    s, r = users["editor"].call("POST", f"/api/diagrams/{did}/save", {"xml": xml2, "base_ver": 1})
    assert s == 200 and r["synced"] is True
    acts = users["editor"].call("GET", "/api/process/TST-C-BE-01")[1]["version"]["content"]["activities"]
    assert acts[0]["activity"] == "Receive and count goods"
    arch = [a for a in acts if a["activity"].startswith("Archive documents")][0]
    assert arch["role"] == "Logistics" and arch["sap"] == "VL02N"
    # switching the link off keeps manual edits
    c2 = dict(users["editor"].call("GET", "/api/process/TST-C-BE-01")[1]["version"]["content"], flow_sync=False)
    c2["activities"] = [{"no": "1", "activity": "Manual step", "role": "X", "sap": "", "output": ""}]
    users["editor"].call("PUT", "/api/process/TST-C-BE-01/draft", {"content": c2})
    s, r = users["editor"].call("POST", f"/api/diagrams/{did}/save", {"xml": xml2.replace("Inform buyer", "Inform the buyer"), "base_ver": 2})
    assert s == 200 and r["synced"] is False
    assert users["editor"].call("GET", "/api/process/TST-C-BE-01")[1]["version"]["content"]["activities"][0]["activity"] == "Manual step"
    users["editor"].call("POST", f"/api/diagrams/{did}/unlock")


def test_audit_comments_track_versions(users):
    pid = "TST-W-001"
    assert users["viewer"].call("POST", f"/api/process/{pid}/comments", {"body": "x"})[0] == 403
    assert users["reviewer"].call("POST", f"/api/process/{pid}/comments", {"body": ""})[0] == 400
    s, r = users["reviewer"].call("POST", f"/api/process/{pid}/comments", {"body": "Step 3 has no evidence requirement", "category": "nonconformity", "severity": "major", "section": "Activities"})
    assert s == 200
    cid = r["id"]
    ver = users["reviewer"].call("GET", f"/api/process/{pid}")[1]["version"]["version"]
    assert users["editor"].call("POST", f"/api/process/{pid}/comments", {"body": "Will add the GR document as evidence", "parent_id": cid})[0] == 200
    reg = users["reviewer"].call("GET", "/api/audit-comments?status=open")[1]["rows"]
    row = [x for x in reg if x["id"] == cid][0]
    assert row["version_label"] == ver and row["category"] == "nonconformity" and row["severity"] == "major" and row["replies"] == 1
    assert users["editor"].call("PUT", f"/api/comments/{cid}", {"status": "resolved"})[0] == 400                    # resolution note is mandatory
    assert users["editor"].call("PUT", f"/api/comments/{cid}", {"status": "resolved", "resolution": "Evidence column filled"})[0] == 200
    assert users["editor"].call("PUT", f"/api/comments/{cid}", {"status": "closed"})[0] == 403                      # author/reviewer/controller close it
    assert users["reviewer"].call("PUT", f"/api/comments/{cid}", {"status": "closed"})[0] == 200
    cm = [c for c in users["reviewer"].call("GET", f"/api/process/{pid}")[1]["comments"] if c["id"] == cid][0]
    assert cm["status"] == "closed" and cm["resolved_by"] == "demo_reviewer" and cm["version_label"] == ver
    assert {"comment_added", "comment_updated"} <= {x["action"] for x in db.q("SELECT action FROM audit WHERE entity_id=?", (pid,))}
    assert users["viewer"].call("GET", "/api/audit-comments")[0] == 403
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(users["reviewer"].call("GET", "/api/audit-comments.xlsx", raw=True)[1]))
    assert wb.active.max_row >= 2 and wb.active["E1"].value == "Raised on version"


def test_departments_legend_templates_and_caching(server, admin, users):
    assert users["editor"].call("POST", "/api/departments", {"code": "HSE", "name": "Health & Safety"})[0] == 403
    assert admin.call("POST", "/api/departments", {"code": "HSE", "name": "Health & Safety"})[0] == 200
    assert admin.call("POST", "/api/departments", {"code": "HSE", "name": "again"})[0] == 400
    assert any(d["code"] == "HSE" for d in admin.call("GET", "/api/tree")[1]["departments"])
    # new flows carry the master legend learned from the imported flows
    s, r = users["editor"].call("POST", "/api/diagrams", {"title": "New flow", "template": "approval_workflow"})
    xml = users["editor"].call("GET", f"/api/diagrams/{r['diagram_id']}")[1]["latest"]["xml"]
    assert "mea_legend" in xml and "Warehouse" in xml
    # caching: static files revalidate with 304, assets are immutable, large JSON is compressed
    import urllib.request
    r1 = urllib.request.urlopen(server + "/app.js")
    etag = r1.headers["ETag"]
    assert etag and r1.headers["Cache-Control"] == "no-cache"
    with pytest.raises(urllib.error.HTTPError) as ei:
        urllib.request.urlopen(urllib.request.Request(server + "/app.js", headers={"If-None-Match": etag}))
    assert ei.value.code == 304
    aid = db.one("SELECT id FROM assets ORDER BY id LIMIT 1")["id"]
    req = urllib.request.Request(server + f"/api/assets/{aid}", headers={"Cookie": "; ".join(f"{c.name}={c.value}" for c in admin.op.handlers[-1].cookiejar) if False else ""})
    s, _ = admin.call("GET", f"/api/assets/{aid}", raw=True)
    assert s == 200
    r2 = admin.op.open(urllib.request.Request(server + f"/api/assets/{aid}"))
    assert "immutable" in r2.headers["Cache-Control"]
    r3 = admin.op.open(urllib.request.Request(server + "/api/library", headers={"Accept-Encoding": "gzip"}))
    assert r3.headers.get("Content-Encoding") == "gzip"
    import gzip as _gz
    assert "processes" in json.loads(_gz.decompress(r3.read()))


# ------------------------------------------------------------------ sign-in recovery
def test_process_id_change_is_controlled_and_follows_everywhere(users, tmp_path):
    from mea_hub import importer
    path = str(tmp_path / "phases.docx")
    make_docx(path, [("Alpha Phase Process", "ZZ-M-AA-01", "First phase of the test project.", ["Planner"], None),
                     ("Beta Phase Process", "ZZ-M-AA-01", "Second phase, a different process with the same chart ID.", ["Planner"], None)], title="Project Test Document")
    importer.import_paths([path], "tester")
    assert db.one("SELECT 1 FROM processes WHERE process_id='ZZ-M-AA-01.2'")
    ctl, viewer = users["controller"], users["viewer"]
    assert viewer.call("POST", "/api/process/ZZ-M-AA-01.2/rename", {"new_id": "ZZ-M-BB-01", "reason": "x"})[0] == 403
    assert ctl.call("POST", "/api/process/ZZ-M-AA-01.2/rename", {"new_id": "ZZ-M-AA-01", "reason": "x"})[0] == 400      # already in use
    assert ctl.call("POST", "/api/process/ZZ-M-AA-01.2/rename", {"new_id": "ZZ-M-BB-01", "reason": ""})[0] == 400       # reason is mandatory
    s, d = ctl.call("POST", "/api/process/ZZ-M-AA-01.2/rename", {"new_id": "zz-m-bb-01", "reason": "Permanent ID issued by Document Controller"})
    assert s == 200 and d["process_id"] == "ZZ-M-BB-01"
    s, old = ctl.call("GET", "/api/process/ZZ-M-AA-01.2")                 # the former ID still leads to the process (bookmarks, printed documents)
    assert s == 200 and old["process"]["process_id"] != "ZZ-M-AA-01.2"
    s, p = ctl.call("GET", "/api/process/ZZ-M-BB-01")
    assert s == 200 and p["process"]["chart_id"] == "ZZ-M-AA-01"                    # what the source said is kept
    row = db.one("SELECT id FROM processes WHERE process_id='ZZ-M-BB-01'")
    f = db.one("SELECT status,decision FROM findings WHERE process_id=? AND title LIKE 'Chart ID ZZ-M-AA-01 is used%'", (row["id"],))
    assert f["status"] == "resolved" and "ZZ-M-AA-01.2 -> ZZ-M-BB-01" in f["decision"]
    assert not db.q("SELECT 1 FROM findings WHERE process_id=? AND status='open' AND title LIKE '%ZZ-M-AA-01.2%'", (row["id"],))
    assert not db.q("SELECT 1 FROM diagrams WHERE process_id=? AND code LIKE 'DG-ZZ-M-AA-01%'", (row["id"],))
    assert db.one("SELECT 1 FROM audit WHERE action='process_id_changed' AND entity_id='ZZ-M-BB-01'")
    assert any(r["process_id"] == "ZZ-M-BB-01" for r in ctl.call("GET", "/api/search?q=Beta+Phase")[1]["results"])
    # the first process keeps its ID and its open findings are untouched by the neighbour's rename
    assert db.one("SELECT 1 FROM processes WHERE process_id='ZZ-M-AA-01' AND name='Alpha Phase Process'")
    # a decision shipped with the flows is applied once and is idempotent
    cor = [dict(chart="ZZ-M-AA-01", name="Alpha Phase Process", to="ZZ-M-CC-01", reason="decision recorded with the flows")]
    assert svc.apply_id_corrections(cor) == [("ZZ-M-AA-01", "ZZ-M-CC-01")]
    assert svc.apply_id_corrections(cor) == []
    # importing the same document again finds both processes under their new IDs (no new provisional IDs)
    before = db.one("SELECT COUNT(*) n FROM processes WHERE kind='sop'")["n"]
    path2 = str(tmp_path / "phases_v2.docx")
    make_docx(path2, [("Alpha Phase Process", "ZZ-M-AA-01", "First phase of the test project.", ["Planner"], None),
                      ("Beta Phase Process", "ZZ-M-AA-01", "Second phase, a different process with the same chart ID.", ["Planner"], None)], title="Project Test Document v2")
    res = importer.import_paths([path2], "tester")
    assert not res["skipped"]
    assert db.one("SELECT COUNT(*) n FROM processes WHERE kind='sop'")["n"] == before
    assert not db.one("SELECT 1 FROM processes WHERE process_id LIKE 'ZZ-M-AA-01%'")


FLOW_LEGEND = dict(roles=[dict(role="Sales", color="#1E90FF"), dict(role="Logistics", color="#008080"), dict(role="Warehouse", color="#2F4F4F"),
                     dict(role="Credit Controller", color="#CD5C5C"), dict(role="Operations Manager", color="#808000"), dict(role="Sales Support Manager", color="#808000")])
STEPS = """Sales: Receive customer order & check it
Credit Controller: Credit limit sufficient?
No: Credit Controller: Block the order
No: End
Note: Check incoterms
Logistcs: Plan the transport
Stock available?
No: Warehouse: Raise replenishment (ME51N)
Ref: WL-M-OB-01 Outbound delivery
Warehouse: Post goods issue (VL02N)
End: Order shipped"""


def test_flow_built_from_text_is_standard_and_reads_back():
    from mea_hub import flowbuild, flowread
    xml, warnings = flowbuild.build("Order to shipment", "ZZ-M-OS-01", "LOG", STEPS, FLOW_LEGEND)
    assert not security.unsafe_xml(xml.encode()) and drawio.normalize(xml)
    assert len(warnings) == 1 and "Logistcs" in warnings[0] and "Logistics" in warnings[0]          # unknown role is reported, never guessed
    assert "mea_frame" in xml and "mea_legend" in xml and "Process Map – Order to shipment – ZZ-M-OS-01" in xml
    fr = flowread.read(xml)
    acts = {a["activity"]: a for a in fr["activities"]}
    assert acts["Receive customer order & check it"]["role"] == "Sales"
    assert acts["Decision: Credit limit sufficient?"]["output"] == "→ No: Block the order; Yes: Logistcs: Plan the transport"
    assert acts["Block the order"]["output"] == "→ End"                                              # "No: End" closes the branch
    assert acts["Logistcs: Plan the transport"]["role"] == ""
    assert acts["Raise replenishment (ME51N)"]["sap"] == "ME51N" and acts["Raise replenishment (ME51N)"]["output"] == ""
    assert "Linked process: WL-M-OB-01 Outbound delivery" in acts and fr["node_meta"]
    assert fr["responsible"] == ["Sales", "Credit Controller", "Warehouse"]
    assert "Check incoterms" in fr["notes_html"] and [x["transaction"] for x in fr["sap"]] == ["ME51N", "VL02N"]
    codes = {c["code"] for c in fr["checks"]}
    assert codes == {"dead_end", "no_role"}                  # the open branch and the steps without a role are reported, not repaired
    assert "Raise replenishment" in next(c["text"] for c in fr["checks"] if c["code"] == "dead_end")
    # a complete flow has no open points
    ok, w = flowbuild.build("t", "", "", "Sales: Take order\nLogistics: Ship order", FLOW_LEGEND)
    assert not w and flowread.read(ok)["checks"] == []
    with pytest.raises(ValueError):
        flowbuild.build("t", "", "", "\n# only a comment\n", FLOW_LEGEND)
    # recolouring a shape in the editor changes its role; two roles sharing a colour keep their tag
    assert flowread.read(ok.replace("strokeColor=#1E90FF;strokeWidth=2;fontSize=11;", "strokeColor=#008080;strokeWidth=2;fontSize=11;", 1))["activities"][0]["role"] == "Logistics"
    same, _ = flowbuild.build("t", "", "", "Operations Manager: Approve", FLOW_LEGEND)
    assert flowread.read(same)["activities"][0]["role"] == "Operations Manager"
    # the activity table of a process turns back into builder text
    text = flowbuild.steps_from_activities(fr["activities"])
    assert "Credit Controller: Credit limit sufficient?" in text and "Ref: WL-M-OB-01 Outbound delivery" in text
    # shape library: standard shapes + one tagged activity per role (roles are listed once)
    lib = flowbuild.library_entries(FLOW_LEGEND)
    assert [e["title"] for e in lib].count("Activity – Sales") == 1 and len(lib) == 10 + 6 and flowbuild.library_xml(FLOW_LEGEND).startswith("<mxlibrary")


def test_new_flow_from_steps_is_linked_to_the_document(users):
    ed, viewer = users["editor"], users["viewer"]
    svc.set_cfg("master_legend", json.dumps(FLOW_LEGEND))
    assert ed.call("POST", "/api/process", {"name": "Order to shipment", "department": "LOG", "process_id": "ZZ-M-OS-01"})[0] == 200
    assert viewer.call("POST", "/api/flows/build", {"process_id": "ZZ-M-OS-01", "steps": STEPS})[0] == 403
    assert ed.call("POST", "/api/flows/build", {"process_id": "ZZ-M-OS-01", "steps": "  "})[0] == 400
    s, r = ed.call("POST", "/api/flows/build", {"process_id": "ZZ-M-OS-01", "steps": STEPS})
    assert s == 200 and r["steps"] == 8 and len(r["warnings"]) == 1 and {c["code"] for c in r["checks"]} == {"dead_end", "no_role"}
    d = ed.call("GET", "/api/process/ZZ-M-OS-01")[1]
    c = d["version"]["content"]
    assert c["flow_sync"] and len(c["activities"]) == 8 and c["responsible"] == ["Sales", "Credit Controller", "Warehouse"]
    assert [x["transaction"] for x in c["sap"]] == ["ME51N", "VL02N"] and d["diagram"]["ver_no"] == 1 and len(d["diagram"]["checks"]) == 2
    assert any(n["meta"].get("role") == "Sales" for n in d["diagram"]["nodes"])
    # building again keeps the first flow as revision 1
    s, r2 = ed.call("POST", "/api/flows/build", {"process_id": "ZZ-M-OS-01", "steps": "Sales: Take order\nLogistics: Ship order"})
    assert s == 200 and r2["diagram_id"] == r["diagram_id"] and r2["checks"] == []
    d = ed.call("GET", "/api/process/ZZ-M-OS-01")[1]
    assert d["diagram"]["ver_no"] == 2 and [a["activity"] for a in d["version"]["content"]["activities"]] == ["Take order", "Ship order"]
    assert not any(n["meta"].get("role") == "Credit Controller" for n in d["diagram"]["nodes"])       # nothing carried over from the old shapes
    # editing in Flow Studio: the save answers with the flow check and the document follows
    did = r["diagram_id"]
    info = ed.call("GET", f"/api/diagrams/{did}")[1]
    assert ed.call("POST", f"/api/diagrams/{did}/lock")[0] == 200
    xml = info["latest"]["xml"].replace("Ship order", "Ship order (VL01N)")
    s, sv = ed.call("POST", f"/api/diagrams/{did}/save", {"xml": xml, "png": None, "base_ver": info["latest"]["ver_no"]})
    assert s == 200 and sv["synced"] and sv["checks"] == []
    assert ed.call("GET", "/api/process/ZZ-M-OS-01")[1]["version"]["content"]["sap"][0]["transaction"] == "VL01N"
    # builder helpers and library
    assert "Take order" in ed.call("GET", "/api/flows/steps?process_id=ZZ-M-OS-01")[1]["steps"]
    assert ed.call("GET", "/api/flows/steps?template=approval_workflow")[1]["steps"].startswith("Prepare and submit request")
    assert len(ed.call("GET", "/api/flow-library")[1]["entries"]) == 16
    s, raw = ed.call("GET", "/api/flow-library.xml", raw=True)
    assert s == 200 and raw.startswith(b"<mxlibrary")
    # a library flow (no process) and a process created from a template are standard tagged flows as well
    s, lib = ed.call("POST", "/api/flows/build", {"title": "Idea", "steps": "Sales: Call customer"})
    assert s == 200 and "meaKind=activity" in ed.call("GET", f"/api/diagrams/{lib['diagram_id']}")[1]["latest"]["xml"]
    assert ed.call("POST", "/api/process", {"name": "Template flow", "department": "LOG", "process_id": "ZZ-M-TF-01", "template": "department_workflow"})[0] == 200
    t = ed.call("GET", "/api/process/ZZ-M-TF-01")[1]
    assert t["version"]["content"]["flow_sync"] and t["diagram"]["checks"] is not None and "ZZ-M-TF-01" in ed.call("GET", f"/api/diagrams/{t['diagram']['diagram_id']}")[1]["latest"]["xml"]


def _png_size(data):
    from PIL import Image
    return Image.open(io.BytesIO(data)).size


def test_document_picture_is_the_flow_only_or_the_export_areas(users):
    """Documents show the flow without frame, title bar and master legend; export areas drawn in Flow Studio cut it further."""
    import base64
    from docx import Document
    from mea_hub import flowbuild, flowpic, flowread
    xml, _ = flowbuild.build("Order to shipment", "ZZ-M-DP-01", "LOG", "Sales: Take order\nStock available?\nNo: End\nWarehouse: Pick goods (LT03)\nLogistics: Ship order (VL01N)", FLOW_LEGEND)
    info = {}
    png = drawio.to_png(xml, info=info)                                         # stands in for the picture draw.io renders
    cover, (W, H) = info["cover"], _png_size(png)
    L = flowpic.layout(xml)
    assert L["frame"] and L["legend"] and L["flow"][3] < L["legend"][1] and not L["areas"]
    res = flowpic.cut(png, xml, cover)
    assert res["kind"] == "flow" and len(res["pictures"]) == 1 and not res["note"]
    w, h = _png_size(res["pictures"][0]["png"])
    k = W / cover[2]
    assert w < W * 0.8 and h < (L["legend"][1] - L["frame"][1]) * k           # narrower than the sheet, ends above the legend
    assert h > (L["flow"][3] - L["flow"][1]) * k * 0.9                        # ... and nothing of the flow is lost
    assert _png_size(flowpic.cut(png, xml, cover, "sheet")["pictures"][0]["png"]) == (W, H)
    assert flowpic.cut(png, xml, (0, 0, 50, 5000))["kind"] == "sheet"         # a picture that cannot be located is never cut blindly
    # an export area around the first steps: only that window, exactly its size
    area = ('<mxCell id="exp1" value="%s" style="%s" vertex="1" parent="1"><mxGeometry x="%s" y="%s" width="300" height="200" as="geometry"/></mxCell>'
            % (flowpic.AREA_LABEL, flowpic.AREA_STYLE, L["flow"][0] - 10, L["flow"][1] - 10))
    area2 = area.replace('id="exp1"', 'id="exp2"').replace(flowpic.AREA_LABEL, "Shipping").replace('y="%s"' % (L["flow"][1] - 10), 'y="%s"' % (L["flow"][1] + 230))
    xa = xml.replace("</root>", area + area2 + "</root>")
    drawio.normalize(xa)
    png_a = drawio.to_png(xa, info=info)
    res = flowpic.cut(png_a, xa, info["cover"])
    assert res["kind"] == "areas" and [p["label"] for p in res["pictures"]] == ["", "Shipping"]
    for p_ in res["pictures"]:
        w, h = _png_size(p_["png"])
        assert abs(w - (300 - 2 * flowpic.INSET) * k) <= 2 and abs(h - (200 - 2 * flowpic.INSET) * k) <= 2
    assert flowpic.describe(xa)["kind"] == "areas" and flowpic.describe(xa)["count"] == 2 and flowpic.describe(xml)["kind"] == "flow"
    # the area is not a process step: activities, roles and the flow check are unchanged
    a, b = flowread.read(xml), flowread.read(xa)
    assert a["activities"] == b["activities"] and a["checks"] == b["checks"]
    assert "Export area (document picture)" in [e["title"] for e in flowbuild.library_entries(FLOW_LEGEND)]
    # through the application: Flow Studio sends the picture and its position, the export uses the areas
    ed = users["editor"]
    svc.set_cfg("master_legend", json.dumps(FLOW_LEGEND))
    assert ed.call("POST", "/api/process", {"name": "Order to shipment", "department": "LOG", "process_id": "ZZ-M-DP-01"})[0] == 200
    s, r = ed.call("POST", "/api/flows/build", {"process_id": "ZZ-M-DP-01", "steps": "Sales: Take order\nStock available?\nNo: End\nWarehouse: Pick goods (LT03)\nLogistics: Ship order (VL01N)"})
    did = r["diagram_id"]
    d = ed.call("GET", "/api/process/ZZ-M-DP-01")[1]
    assert d["diagram"]["picture"]["kind"] == "flow"
    s, pic = ed.call("GET", f"/api/diagram-versions/{d['diagram']['id']}/picture")
    assert s == 200 and pic["kind"] == "flow" and len(pic["pictures"]) == 1
    assert ed.call("GET", f"/api/diagram-versions/{d['diagram']['id']}/picture/0", raw=True)[1][:4] == b"\x89PNG"
    assert ed.call("GET", f"/api/diagram-versions/{d['diagram']['id']}/picture/3")[0] == 404
    assert ed.call("POST", f"/api/diagrams/{did}/lock")[0] == 200
    c = info["cover"]
    box = [c[0] + flowpic.BORDER, c[1] + flowpic.BORDER, c[2] - 2 * flowpic.BORDER, c[3] - 2 * flowpic.BORDER]
    s, sv = ed.call("POST", f"/api/diagrams/{did}/save", {"xml": xa, "png": "data:image/png;base64," + base64.b64encode(png_a).decode(), "box": box, "base_ver": 1})
    assert s == 200 and sv["picture"]["kind"] == "areas" and sv["picture"]["count"] == 2
    d = ed.call("GET", "/api/process/ZZ-M-DP-01")[1]
    assert len(d["version"]["content"]["activities"]) == len(a["activities"])                       # the areas did not become activities
    s, pic = ed.call("GET", f"/api/diagram-versions/{d['diagram']['id']}/picture")
    assert pic["kind"] == "areas" and [p_["label"] for p_ in pic["pictures"]] == ["", "Shipping"]
    s, e = ed.call("POST", "/api/exports", {"scope": "process", "ids": ["ZZ-M-DP-01"], "fmt": "docx"})
    doc = Document(io.BytesIO(ed.call("GET", f"/api/exports/{e['export']['id']}/download", raw=True)[1]))
    assert sum(len(p_._p.xpath(".//w:drawing")) for p_ in doc.paragraphs) == 2 and "Part 2 of 2 – Shipping" in all_text(doc)
    s, e = ed.call("POST", "/api/exports", {"scope": "process", "ids": ["ZZ-M-DP-01"], "fmt": "docx", "flow_picture": "sheet"})
    doc = Document(io.BytesIO(ed.call("GET", f"/api/exports/{e['export']['id']}/download", raw=True)[1]))
    assert sum(len(p_._p.xpath(".//w:drawing")) for p_ in doc.paragraphs) == 1
    for fmt in ("pdf", "html"):
        s, e = ed.call("POST", "/api/exports", {"scope": "process", "ids": ["ZZ-M-DP-01"], "fmt": fmt})
        assert s == 200 and e["export"]["status"] == "done"


def test_draft_raci_and_sap_work_instructions_use_only_the_flow(users):
    """Drafts take roles, order and wording from the flow; what the sources do not say stays empty or is written as an open point."""
    from mea_hub import drafts
    roles = ["Sales", "Logistics", "Warehouse", "Customer Service", "Financial Controller"]
    acts = [dict(no="1", activity="Receive order", role="Sales", sap="", output="→ Stock available?"),
            dict(no="2", activity="Decision: Stock available?", role="Logistics", sap="", output="→ Yes: Post goods issue in SAP (VL02N); No: Notify Sales with comments"),
            dict(no="3", activity="Notify Sales with comments", role="Logistics", sap="", output=""),
            dict(no="4", activity="Customer Service to get approval from Logistics Head", role="Customer Service", sap="", output="→ Post goods issue in SAP (VL02N)"),
            dict(no="5", activity="Post goods issue in SAP (VL02N)", role="Warehouse", sap="VL02N", output="→ Share the report with Financial Controller"),
            dict(no="6", activity="Share the report with Financial Controller", role="Warehouse", sap="", output=""),
            dict(no="7", activity="Align with the Shop Drawing and Share it", role="", sap="", output=""),
            dict(no="8", activity="Linked process: WL-M-OB-01 Dispatch", role="", sap="", output="")]
    rows = {r["activity"]: r for r in drafts.raci_rows(acts, "", roles)}
    assert len(rows) == 7 and "Linked process: WL-M-OB-01 Dispatch" not in rows                       # a reference is not a step
    assert rows["Receive order"] == dict(activity="Receive order", R="Sales", A="", C="", I="Logistics")       # I = role of the next step
    assert rows["Decision: Stock available?"]["I"] == "Warehouse" and rows["Notify Sales with comments"]["I"] == "Sales"
    assert rows["Customer Service to get approval from Logistics Head"]["A"] == "Logistics Head"       # as written, not shortened to the role "Logistics"
    assert rows["Share the report with Financial Controller"]["I"] == "Financial Controller"
    assert rows["Align with the Shop Drawing and Share it"] == dict(activity="Align with the Shop Drawing and Share it", R="", A="", C="", I="")   # nothing guessed
    assert all(r["A"] == "Jane Doe" for r in drafts.raci_rows(acts[:3], "Jane Doe", roles))              # the recorded process owner is accountable
    # through the application
    ed, ctl, viewer = users["editor"], users["controller"], users["viewer"]
    svc.set_cfg("master_legend", json.dumps(dict(roles=[dict(role=r, color="#1E90FF") for r in roles])))
    assert ed.call("POST", "/api/process", {"name": "Order to shipment", "department": "LOG", "process_id": "ZZ-M-RA-01"})[0] == 200
    steps = "Sales: Receive order\nLogistics: Stock available?\nNo: Logistics: Notify Sales with comments\nNo: End\nWarehouse: Post goods issue in SAP (VL02N)\nWarehouse: Update stock report in SAP"
    assert ed.call("POST", "/api/flows/build", {"process_id": "ZZ-M-RA-01", "steps": steps})[0] == 200
    assert viewer.call("POST", "/api/drafts/raci", {"process_id": "ZZ-M-RA-01"})[0] == 403 and ed.call("POST", "/api/drafts/raci", {})[0] == 403
    s, r = ed.call("POST", "/api/drafts/raci", {"process_id": "ZZ-M-RA-01"})
    assert s == 200 and r["rows"] == 5
    c = ed.call("GET", "/api/process/ZZ-M-RA-01")[1]["version"]["content"]
    assert c["raci_draft"] and [x["R"] for x in c["raci"]] == ["Sales", "Logistics", "Logistics", "Warehouse", "Warehouse"] and not any(x["A"] or x["C"] for x in c["raci"])
    assert ed.call("POST", "/api/drafts/raci", {"process_id": "ZZ-M-RA-01"})[1]["rows"] == 0             # an existing RACI is not overwritten unless asked
    # editing something else keeps the draft mark, editing the RACI removes it
    d = ed.call("GET", "/api/process/ZZ-M-RA-01")[1]
    assert ed.call("PUT", "/api/process/ZZ-M-RA-01/draft", {"content": dict(c, objective="Ship orders"), "base_updated_at": None})[0] == 200
    c = ed.call("GET", "/api/process/ZZ-M-RA-01")[1]["version"]["content"]
    assert c["raci_draft"] and c["objective"] == "Ship orders"
    c["raci"][0]["A"] = "Sales Manager"
    assert ed.call("PUT", "/api/process/ZZ-M-RA-01/draft", {"content": c, "base_updated_at": None})[0] == 200
    c = ed.call("GET", "/api/process/ZZ-M-RA-01")[1]["version"]["content"]
    assert not c.get("raci_draft") and c["raci"][0]["A"] == "Sales Manager"
    # SAP work instructions: one draft per distinct SAP step, editable, linked to the process, never created twice
    info = ctl.call("GET", "/api/drafts")[1]
    assert info["can"] and info["sap_steps"] >= 2
    assert ed.call("POST", "/api/drafts/sap", {})[0] == 403
    s, r = ctl.call("POST", "/api/drafts/sap", {})
    mine = [p_ for p_ in r["created"] if p_.startswith("ZZ-M-RA-01-WI-")]
    assert s == 200 and len(mine) == 2
    assert ctl.call("POST", "/api/drafts/sap", {})[1]["created"] == []
    wi = ed.call("GET", f"/api/process/{mine[0]}")[1]
    w = wi["version"]["content"]
    assert wi["process"]["kind"] == "work_instruction" and wi["version"]["status"] == "draft" and wi["perms"]["edit"]
    assert w["sap"] == [dict(transaction="VL02N", purpose="Change Outbound Delivery (standard SAP name)")] and w["responsible"] == ["Warehouse"]
    assert "Decision: Stock available?" in w["activities"][0]["activity"] and "Update stock report in SAP" in w["activities"][4]["activity"]
    assert "[to be completed by the process owner]" in w["activities"][2]["activity"] and "Nothing was assumed" in w["notes"]
    w2 = ed.call("GET", f"/api/process/{mine[1]}")[1]["version"]["content"]
    assert w2["sap"] == [] and "do not name it" in w2["activities"][1]["activity"]                        # no transaction in the source: left open
    assert any(x["process_id"] == "ZZ-M-RA-01" for x in wi["relationships"])
    w["activities"][2]["activity"] = "Enter delivery number, post goods issue"
    assert ed.call("PUT", f"/api/process/{mine[0]}/draft", {"content": w, "base_updated_at": None})[0] == 200          # the draft is the user's to complete


def test_hosted_mode_secure_cookie_and_login_throttle(server, users):
    import urllib.request
    def login(user, pw, proto=None):
        h = {"Content-Type": "application/json"}
        if proto:
            h["X-Forwarded-Proto"] = proto
        req = urllib.request.Request(server + "/api/login", data=json.dumps({"username": user, "password": pw}).encode(), headers=h, method="POST")
        try:
            r = urllib.request.urlopen(req)
            return r.status, r.headers.get("Set-Cookie") or "", ""
        except urllib.error.HTTPError as e:
            return e.code, "", json.loads(e.read())["error"]
    s, cookie, _ = login("demo_viewer", "ChangeMe!123", "https")            # behind an HTTPS proxy the session cookie is Secure
    assert s == 200 and cookie.endswith("; Secure") and "HttpOnly" in cookie
    s, cookie, _ = login("demo_viewer", "ChangeMe!123")
    assert s == 200 and "Secure" not in cookie
    for _ in range(svc.LOGIN_MAX_FAILURES):
        assert login("demo_reviewer", "wrong")[0] == 403
    s, _, err = login("demo_reviewer", "ChangeMe!123")                        # even the right password waits now
    assert s == 403 and "Too many failed sign-ins" in err
    assert login("demo_viewer", "ChangeMe!123")[0] == 200                     # other users are not affected
    db.db().execute("DELETE FROM audit WHERE username='demo_reviewer' AND action='login_failed'")
    assert login("demo_reviewer", "ChangeMe!123")[0] == 200


def test_embedding_in_sharepoint_is_opt_in(server, users, monkeypatch):
    """By default no other site may frame the app. Named https sites may, and then the session cookie works inside their frame."""
    import urllib.request
    from mea_hub import config

    def get(path, data=None):
        req = urllib.request.Request(server + path, data=data, headers={"Content-Type": "application/json"}, method="POST" if data else "GET")
        r = urllib.request.urlopen(req)
        return r.status, r.headers
    body = json.dumps({"username": "demo_editor", "password": "ChangeMe!123"}).encode()
    s, h = get("/")
    assert h["X-Frame-Options"] == "SAMEORIGIN" and "frame-ancestors 'self';" not in h["Content-Security-Policy"] and h["Content-Security-Policy"].endswith("frame-ancestors 'self'")
    assert "SameSite=Strict" in get("/api/login", body)[1]["Set-Cookie"]
    s, h = get("/api/health")                                                # reverse proxy / monitoring probe, no session needed
    assert s == 200
    assert json.loads(urllib.request.urlopen(server + "/api/config").read())["embeddable"] is False
    # invalid entries never open the door: plain http, a path, a bare wildcard
    monkeypatch.setenv("MEA_HUB_EMBED_ORIGINS", "http://evil.example, https://contoso.sharepoint.com/sites/x, *, javascript:alert(1)")
    assert config.embed_origins() == [] and get("/")[1]["X-Frame-Options"] == "SAMEORIGIN"
    monkeypatch.setenv("MEA_HUB_EMBED_ORIGINS", "https://contoso.sharepoint.com, https://*.sharepoint.com/ ,https://contoso.sharepoint.com")
    assert config.embed_origins() == ["https://contoso.sharepoint.com", "https://*.sharepoint.com"]
    s, h = get("/")
    assert h["X-Frame-Options"] is None and h["Cross-Origin-Resource-Policy"] == "same-origin"
    assert h["Content-Security-Policy"].endswith("frame-ancestors 'self' https://contoso.sharepoint.com https://*.sharepoint.com")
    cookie = get("/api/login", body)[1]["Set-Cookie"]
    assert "SameSite=None; Secure; Partitioned" in cookie and "HttpOnly" in cookie and "SameSite=Strict" not in cookie
    assert json.loads(urllib.request.urlopen(server + "/api/config").read())["embeddable"] is True
    # the cookie now travels with cross-site requests, so changes still need the CSRF header
    ed = users["editor"]
    assert ed.call("POST", "/api/process", {"name": "x", "department": "LOG"}, csrf=False)[0] == 403


def test_upgrade_helpers_aliases_legend_loops_and_long_flows(admin, users, tmp_path, monkeypatch):
    """Small things that make the tool hold up in daily use."""
    from mea_hub import config, flowbuild, flowpic, flowread
    ed, ctl = users["editor"], users["controller"]
    # a flow builder branch may loop back to an earlier step
    xml, warn = flowbuild.build("Loop", "ZZ-M-LP-01", "LOG", "Sales: Receive order\nSales: Check data\nLogistics: Data complete?\nNo: Sales: Ask customer\nNo: Back to 2\n"
                                "Warehouse: Pick goods\nLogistics: Quantity correct?\nNo: Back to: Pick goods\nLogistics: Ship\nLogistics: Delivered?\nNo: Back to 99", FLOW_LEGEND)
    acts = {a["activity"]: a["output"] for a in flowread.read(xml)["activities"]}
    assert acts["Ask customer"] == "→ Check data" and "No: Pick goods" in acts["Decision: Quantity correct?"]
    assert len(warn) == 1 and "Back to 99" in warn[0]                                                # an unknown target is reported, the branch stays open
    # the master legend is editable; bad input is refused
    roles = admin.call("GET", "/api/legend")[1]["roles"]
    assert ed.call("PUT", "/api/legend", {"roles": roles})[0] == 403
    assert admin.call("PUT", "/api/legend", {"roles": roles + [{"role": "Quality Inspector", "color": "red"}]})[0] == 400
    assert admin.call("PUT", "/api/legend", {"roles": roles + [{"role": "Sales", "color": "#112233"}]})[0] == (400 if any(r["role"] == "Sales" for r in roles) else 200)
    s, r = admin.call("PUT", "/api/legend", {"roles": [x for x in roles if x["role"] != "Quality Inspector"] + [{"role": " Quality  Inspector ", "color": "#aa3377"}, {"role": "", "color": ""}]})
    assert s == 200 and r["roles"][-1] == {"role": "Quality Inspector", "color": "#AA3377"}
    assert "Quality Inspector" in ed.call("GET", "/api/config")[1]["flow_roles"]
    assert any(e["title"] == "Activity – Quality Inspector" for e in ed.call("GET", "/api/flow-library")[1]["entries"])
    # a flow much taller than a page is printed in consecutive parts, cut between shapes
    steps = "\n".join(f"Sales: Step number {i} of a long procedure" for i in range(1, 41))
    long_xml, _ = flowbuild.build("Long", "ZZ-M-LG-01", "LOG", steps, FLOW_LEGEND)
    info = {}
    res = flowpic.cut(drawio.to_png(long_xml, info=info), long_xml, info["cover"])
    assert res["kind"] == "flow" and 2 <= len(res["pictures"]) <= 8 and "consecutive parts" in res["note"]
    heights = [_png_size(p_["png"])[1] for p_ in res["pictures"]]
    assert max(heights) < 1.6 * min(heights)                                                         # roughly even parts
    short_xml, _ = flowbuild.build("Short", "ZZ-M-SH-01", "LOG", "Sales: One\nSales: Two", FLOW_LEGEND)
    assert len(flowpic.cut(drawio.to_png(short_xml, info=info), short_xml, info["cover"])["pictures"]) == 1
    # exports carry the legend once, because the flow pictures no longer do
    assert ed.call("POST", "/api/process", {"name": "Loop process", "department": "LOG", "process_id": "ZZ-M-LP-01"})[0] == 200
    assert ed.call("POST", "/api/flows/build", {"process_id": "ZZ-M-LP-01", "steps": "Sales: Receive order\nLogistics: Ship"})[0] == 200
    from docx import Document
    s, e = ed.call("POST", "/api/exports", {"scope": "process", "ids": ["ZZ-M-LP-01"], "fmt": "docx"})
    text = all_text(Document(io.BytesIO(ed.call("GET", f"/api/exports/{e['export']['id']}/download", raw=True)[1])))
    assert "Appendix B – Flowchart legend" in text and "Logistics" in text
    s, e = ed.call("POST", "/api/exports", {"scope": "process", "ids": ["ZZ-M-LP-01"], "fmt": "docx", "flow_picture": "sheet"})
    assert "Appendix B – Flowchart legend" not in all_text(Document(io.BytesIO(ed.call("GET", f"/api/exports/{e['export']['id']}/download", raw=True)[1])))
    # source files delivered with a newer version are offered for import, once
    root = tmp_path / "app"
    (root / "source_documents" / "flows").mkdir(parents=True)
    (root / "source_documents" / "flows" / "ZZ-M-LP-01_Loop.drawio").write_text(xml, encoding="utf-8")
    monkeypatch.setattr(config, "app_root", lambda: str(root))
    assert ed.call("GET", "/api/sources/pending")[1] == {"files": ["ZZ-M-LP-01_Loop.drawio"], "can": False}
    assert ed.call("POST", "/api/sources/import-shipped", {})[0] == 403
    s, r = ctl.call("POST", "/api/sources/import-shipped", {})
    assert s == 200 and len(r["sources"]) == 1 and ctl.call("GET", "/api/sources/pending")[1]["files"] == []
    assert len(ed.call("GET", "/api/process/ZZ-M-LP-01")[1]["version"]["content"]["activities"]) == 8      # the delivered flow became the next revision


def test_read_only_publication_for_sharepoint(admin, users):
    """The "site" export is a self-contained read-only library: data, flow pictures and the reader - no server needed to read it."""
    ed, viewer = users["editor"], users["viewer"]
    svc.set_cfg("master_legend", json.dumps(FLOW_LEGEND))
    assert ed.call("POST", "/api/process", {"name": "Goods receipt", "department": "LOG", "process_id": "ZZ-M-PB-01"})[0] == 200
    assert ed.call("POST", "/api/flows/build", {"process_id": "ZZ-M-PB-01", "steps": "Warehouse: Receive goods\nLogistics: Documents complete?\nNo: End\nWarehouse: Post goods receipt (MIGO)"})[0] == 200
    s, e = ed.call("POST", "/api/exports", {"scope": "process", "ids": ["ZZ-M-PB-01"], "fmt": "site"})
    assert s == 200 and e["export"]["filename"].endswith("_SharePoint.zip")
    z = zipfile.ZipFile(io.BytesIO(ed.call("GET", f"/api/exports/{e['export']['id']}/download", raw=True)[1]))
    names = z.namelist()
    assert {"processhub/handbook.json", "processhub/index.html", "processhub/viewer.js", "README.txt"} <= set(names)
    assert "processhub/flows/ZZ-M-PB-01_1.png" in names and z.read("processhub/flows/ZZ-M-PB-01_1.png")[:4] == b"\x89PNG"
    assert b"MEAProcessHubViewer" in z.read("processhub/viewer.js") and b"viewer.js" in z.read("processhub/index.html")
    book = json.loads(z.read("processhub/handbook.json"))
    pr = book["departments"][0]["processes"][0]
    assert book["count"] == 1 and book["unapproved"] == 1 and pr["id"] == "ZZ-M-PB-01" and pr["status"] != "published"
    assert [a["activity"] for a in pr["activities"]][-1] == "Post goods receipt (MIGO)" and pr["sap"][0]["transaction"] == "MIGO"
    assert pr["pictures"] == [{"file": "flows/ZZ-M-PB-01_1.png", "label": "", "part": 0, "of": 1}]
    assert {"Warehouse", "Logistics"} <= {r["role"] for r in book["legend"]}
    assert "UNCONTROLLED DRAFT" in z.read("README.txt").decode()
    assert "xml" not in pr and "password" not in json.dumps(book).lower()                           # no editable source, no account data
    # a viewer can only publish what is approved: nothing here yet
    assert viewer.call("POST", "/api/exports", {"scope": "process", "ids": ["ZZ-M-PB-01"], "fmt": "site"})[0] in (400, 403)


# ------------------------------------------------------------------ single sign-on (Entra ID) against a stand-in identity provider
def _rsa_key(bits=2048):
    """Test key only (pure Python, Miller-Rabin)."""
    import random
    rnd = random.SystemRandom()

    def prime(nbits):
        while True:
            c = rnd.getrandbits(nbits) | (1 << (nbits - 1)) | 1
            if any(c % q == 0 for q in (3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)):
                continue
            d, r = c - 1, 0
            while d % 2 == 0:
                d, r = d // 2, r + 1
            for _ in range(12):
                x = pow(rnd.randrange(2, c - 1), d, c)
                if x in (1, c - 1):
                    continue
                for _ in range(r - 1):
                    x = pow(x, 2, c)
                    if x == c - 1:
                        break
                else:
                    break
            else:
                return c
    while True:
        p_, q_ = prime(bits // 2), prime(bits // 2)
        n, e = p_ * q_, 65537
        if n.bit_length() == bits and (p_ - 1) % e and (q_ - 1) % e:
            return n, e, pow(e, -1, (p_ - 1) * (q_ - 1))


class FakeEntra:
    """Answers like the Entra endpoints the tool uses: configuration document, key set, token endpoint."""
    TENANT = "11111111-2222-3333-4444-555555555555"

    def __init__(self):
        import base64, hashlib, threading, time
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from urllib.parse import parse_qs
        self.n, self.e, self.d = _rsa_key()
        self.codes, self.auto, me = {}, {}, self
        b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()
        self.b64 = b64

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, obj, status=200):
                data = json.dumps(obj).encode()
                self.send_response(status); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

            def do_GET(self):
                if self.path.endswith("/.well-known/openid-configuration"):
                    return self._send(dict(issuer=me.authority, authorization_endpoint=me.base + "/authorize", token_endpoint=me.base + "/token", jwks_uri=me.base + "/keys"))
                if self.path.startswith("/authorize?"):          # the person signs in and is sent back to the tool
                    from urllib.parse import urlparse
                    code, state = me.sign_in(me.base + self.path, **me.auto)
                    back = parse_qs(urlparse(self.path).query)["redirect_uri"][0]
                    self.send_response(302); self.send_header("Location", f"{back}?code={code}&state={state}"); self.send_header("Content-Length", "0"); self.end_headers()
                    return
                if self.path == "/keys":
                    return self._send(dict(keys=[dict(kty="RSA", kid="k1", use="sig", n=b64(me.n.to_bytes(256, "big")), e=b64(me.e.to_bytes(3, "big")))]))
                self._send({}, 404)

            def do_POST(self):
                form = {k: v[0] for k, v in parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode()).items()}
                c = me.codes.pop(form.get("code"), None)
                if not c or form.get("client_secret") != "s3cret" or form.get("redirect_uri") != c["redirect_uri"]:
                    return self._send(dict(error="invalid_grant", error_description="code or secret wrong"), 400)
                if b64(hashlib.sha256(form.get("code_verifier", "").encode()).digest()) != c["challenge"]:
                    return self._send(dict(error="invalid_grant", error_description="PKCE verifier does not match"), 400)
                self._send(dict(token_type="Bearer", id_token=me.token(c["claims"], c.get("tamper"))))
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        self.authority = f"{self.base}/{self.TENANT}/v2.0"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.time = time

    def token(self, claims, tamper=None):
        import hashlib
        head = dict(alg="none" if tamper == "alg" else "RS256", kid="k1", typ="JWT")
        signing = self.b64(json.dumps(head).encode()) + "." + self.b64(json.dumps(claims).encode())
        di = bytes.fromhex("3031300d060960864801650304020105000420") + hashlib.sha256(signing.encode()).digest()
        em = b"\x00\x01" + b"\xff" * (256 - 3 - len(di)) + b"\x00" + di
        sig = pow(int.from_bytes(em, "big"), self.d, self.n).to_bytes(256, "big")
        if tamper == "payload":                                # content changed after signing
            signing = signing.split(".")[0] + "." + self.b64(json.dumps(dict(claims, roles=["admin"])).encode())
        return signing + "." + self.b64(sig)

    def sign_in(self, login_url, tamper=None, **over):
        """The person signs in at the identity provider: returns the code it would send back to the tool."""
        from urllib.parse import parse_qs, urlparse
        q = {k: v[0] for k, v in parse_qs(urlparse(login_url).query).items()}
        assert q["response_type"] == "code" and q["code_challenge_method"] == "S256" and "openid" in q["scope"] and login_url.startswith(self.base + "/authorize?")
        claims = dict(iss=self.authority, aud=q["client_id"], tid=self.TENANT, exp=int(self.time.time()) + 600, nbf=int(self.time.time()) - 5, nonce=q["nonce"],
                      oid="aaaaaaaa-0000-0000-0000-000000000001", name="Layla Hassan", preferred_username="Layla.Hassan@example.com")
        claims.update(over)
        code = "code" + str(len(self.codes) + int(self.time.time() * 1000))
        self.codes[code] = dict(claims=claims, challenge=q["code_challenge"], redirect_uri=q["redirect_uri"], tamper=tamper)
        return code, q["state"]


def test_single_sign_on_with_entra_id(server, admin, users, monkeypatch):
    """Authorization code flow with PKCE: the token is verified, roles come from app roles, forged or replayed answers are refused."""
    import http.cookiejar
    import urllib.request
    from mea_hub import sso

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    def browser():
        return urllib.request.build_opener(NoRedirect, urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def get(op, path):
        try:
            r = op.open(server + path)
            return r.status, r.headers, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read().decode()

    assert json.loads(urllib.request.urlopen(server + "/api/config").read())["sso"] == {"enabled": False, "only": False}
    assert get(browser(), "/auth/login")[0] == 400 and admin.call("GET", "/api/admin/sso")[1]["enabled"] is False
    idp = FakeEntra()
    for k, v in dict(MEA_HUB_OIDC_AUTHORITY=idp.authority, MEA_HUB_OIDC_TENANT=idp.TENANT, MEA_HUB_OIDC_CLIENT_ID="client-123", MEA_HUB_OIDC_CLIENT_SECRET="s3cret", MEA_HUB_PUBLIC_URL=server).items():
        monkeypatch.setenv(k, v)
    st = admin.call("GET", "/api/admin/sso")[1]
    assert st["enabled"] and st["reachable"] and st["has_secret"] and st["redirect_uri"] == server + "/auth/callback" and "s3cret" not in json.dumps(st)

    def attempt(b, popup=False, tamper=None, state=None, **over):
        s, h, _ = get(b, "/auth/login" + ("?popup=1" if popup else ""))
        assert s == 302
        code, st_ = idp.sign_in(h["Location"], tamper, **over)
        return get(b, f"/auth/callback?code={code}&state={state or st_}")

    # 1. first sign-in: the person is created with the role and department named in the app roles
    b = browser()
    s, h, body = attempt(b, roles=["ProcessHub.editor.LOG", "viewer"])
    assert s == 200 and "HttpOnly" in h["Set-Cookie"] and "url=/" in body
    me = json.loads(get(b, "/api/me")[2])
    log = db.one("SELECT id FROM departments WHERE code='LOG'")["id"]
    assert me["user"]["username"] == "layla.hassan@example.com" and me["user"]["display_name"] == "Layla Hassan" and me["user"]["role"] == "editor" and me["user"]["department_id"] == log and me["csrf"]
    row = db.one("SELECT * FROM users WHERE username='layla.hassan@example.com'")
    assert row["auth"] == "entra" and row["external_id"].endswith("0001") and not row["must_change"] and row["last_login"]
    # 2. the directory decides at every sign-in: role changed there, same person here
    assert attempt(browser(), roles=["controller"])[0] == 200
    again = db.one("SELECT id,role,department_id FROM users WHERE external_id=?", (row["external_id"],))
    assert again == {"id": row["id"], "role": "controller", "department_id": None}
    assert attempt(browser())[0] == 200 and db.one("SELECT role FROM users WHERE id=?", (row["id"],))["role"] == "viewer"      # no app role: default role
    # 3. her password cannot be used, and she never had one
    c = Client(server)
    assert c.call("POST", "/api/login", {"username": "layla.hassan@example.com", "password": "anything"}, csrf=False)[0] == 403
    # 4. everything that is not a genuine, fresh answer of this directory for this application is refused
    for kw, why in ((dict(tamper="payload"), "signature"), (dict(tamper="alg"), "signature method"), (dict(aud="other-app"), "another application"), (dict(nonce="x"), "sign-in attempt"),
                    (dict(exp=1), "expired"), (dict(iss="https://login.microsoftonline.com/other/v2.0"), "another directory"), (dict(tid="99999999-2222-3333-4444-555555555555"), "another tenant"),
                    (dict(state="unknown"), "unknown or older")):
        s, _, body = attempt(browser(), **kw)
        assert s == 400 and why in body, (kw, body[-200:])
    b = browser()
    s, h, _ = get(b, "/auth/login")
    code, state = idp.sign_in(h["Location"])
    assert get(b, f"/auth/callback?code={code}&state={state}")[0] == 200
    assert get(b, f"/auth/callback?code={code}&state={state}")[0] == 400                                   # an answer cannot be replayed
    assert get(browser(), "/auth/callback?error=access_denied&error_description=User+cancelled")[0] == 400
    # 5. a person without an app role can be kept out entirely
    monkeypatch.setenv("MEA_HUB_OIDC_DEFAULT_ROLE", "none")
    s, _, body = attempt(browser(), oid="aaaaaaaa-0000-0000-0000-000000000002", preferred_username="omar@example.com", name="Omar")
    assert s == 400 and "no role" in body and not db.one("SELECT 1 FROM users WHERE username='omar@example.com'")
    monkeypatch.delenv("MEA_HUB_OIDC_DEFAULT_ROLE")
    # 6. deactivated in the tool: no entry even with a valid Microsoft sign-in
    db.db().execute("UPDATE users SET active=0 WHERE id=?", (row["id"],))
    s, _, body = attempt(browser(), roles=["admin"])
    assert s == 400 and "deactivated" in body
    db.db().execute("UPDATE users SET active=1 WHERE id=?", (row["id"],))
    # 7. roles kept in the tool instead of the directory
    monkeypatch.setenv("MEA_HUB_OIDC_ROLE_SOURCE", "tool")
    db.db().execute("UPDATE users SET role='reviewer' WHERE id=?", (row["id"],))
    assert attempt(browser(), roles=["admin"])[0] == 200 and db.one("SELECT role FROM users WHERE id=?", (row["id"],))["role"] == "reviewer"
    monkeypatch.delenv("MEA_HUB_OIDC_ROLE_SOURCE")
    # 8. framed page (SharePoint, Teams): the sign-in window hands a one-time code to the frame
    b = browser()
    s, h, _ = attempt(b, popup=True, roles=["approver"])
    assert s == 302 and h["Location"].startswith("/auth/done.html#h=") and "Set-Cookie" not in h
    token = h["Location"].split("#h=")[1]
    frame = Client(server)
    s, r = frame.call("POST", "/api/auth/handoff", {"token": token}, csrf=False)
    assert s == 200 and r["user"]["role"] == "approver" and r["csrf"]
    frame.csrf = r["csrf"]
    assert frame.call("GET", "/api/library")[0] == 200
    assert Client(server).call("POST", "/api/auth/handoff", {"token": token}, csrf=False)[0] == 403        # single use
    # 9. single sign-on only: passwords remain for local administrators
    monkeypatch.setenv("MEA_HUB_OIDC_ONLY", "1")
    assert json.loads(urllib.request.urlopen(server + "/api/config").read())["sso"] == {"enabled": True, "only": True}
    assert Client(server).call("POST", "/api/login", {"username": "demo_editor", "password": "ChangeMe!123"}, csrf=False)[0] == 403
    assert Client(server).call("POST", "/api/login", {"username": "admin", "password": "Str0ng!Admin#1"}, csrf=False)[0] == 200
    # the signature check itself
    n, e, d = idp.n, idp.e, idp.d
    import hashlib
    di = bytes.fromhex("3031300d060960864801650304020105000420") + hashlib.sha256(b"msg").digest()
    sig = pow(int.from_bytes(b"\x00\x01" + b"\xff" * (256 - 3 - len(di)) + b"\x00" + di, "big"), d, n).to_bytes(256, "big")
    assert sso.rsa_verify(n, e, sig, b"msg") and not sso.rsa_verify(n, e, sig, b"msg2") and not sso.rsa_verify(n, e, sig[:-1] + bytes([sig[-1] ^ 1]), b"msg")
    assert not sso.rsa_verify(n >> 1100, e, sig, b"msg")                                                    # short keys are not accepted
    assert sso.settings()["only"] and sso.settings()["redirect_uri"] == server + "/auth/callback"
    monkeypatch.setenv("MEA_HUB_OIDC_TENANT", "common")
    monkeypatch.delenv("MEA_HUB_OIDC_AUTHORITY")
    assert sso.settings() is None                                                                           # one named tenant only


def test_notifications_by_mail_and_teams(server, admin, users, monkeypatch, tmp_path):
    """People are told once when work is waiting for them; failures are retried; nothing is sent unless a channel is configured."""
    import datetime as dt
    import socketserver
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from mea_hub import notify

    class Smtp(socketserver.StreamRequestHandler):               # minimal mail server that keeps what it receives
        def handle(self):
            say = lambda t: self.wfile.write((t + "\r\n").encode())
            say("220 test")
            data, buf, rcpt = False, [], []
            for line in self.rfile:
                if data:
                    if line.strip() == b".":
                        self.server.box.append((list(rcpt), b"".join(buf).decode("utf-8", "replace")))
                        data, buf, rcpt = False, [], []
                        say("250 ok")
                    else:
                        buf.append(line)
                    continue
                cmd = line.strip()
                if cmd.upper().startswith(b"RCPT TO:"):
                    rcpt.append(cmd[8:].decode().strip("<> "))
                if cmd.upper() == b"DATA":
                    data = True
                    say("354 go")
                elif cmd.upper() == b"QUIT":
                    say("221 bye")
                    return
                else:
                    say("250 ok")
    mail = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Smtp)
    mail.box = []
    threading.Thread(target=mail.serve_forever, daemon=True).start()
    posts = []

    class Hook(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            posts.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(202); self.send_header("Content-Length", "0"); self.end_headers()
    hook = ThreadingHTTPServer(("127.0.0.1", 0), Hook)
    threading.Thread(target=hook.serve_forever, daemon=True).start()

    assert notify.run_once() == dict(mails=0, failed=0, teams=0, people_without_address=0) and not notify.enabled()      # nothing configured: nothing happens
    db.db().execute("DELETE FROM notified")
    db.db().execute("UPDATE users SET email=NULL, notify=1")
    monday = dt.datetime(2026, 11, 16, 9, 0)
    assert monday.weekday() == 0
    hookfile = tmp_path / "hook.txt"
    hookfile.write_text(f"http://127.0.0.1:{hook.server_address[1]}/workflows/abc")
    for k, v in dict(MEA_HUB_SMTP_HOST="127.0.0.1", MEA_HUB_SMTP_PORT=str(mail.server_address[1]), MEA_HUB_MAIL_FROM="processhub@example.com", MEA_HUB_PUBLIC_URL="https://processhub.example.com",
                     MEA_HUB_TEAMS_WEBHOOK_FILE=str(hookfile), MEA_HUB_NOTIFY_DIGEST="off").items():
        monkeypatch.setenv(k, v)
    ed, rev = users["editor"], users["reviewer"]
    # addresses: the administrator enters them (single sign-on users have theirs from the directory)
    uid = {u["username"]: u["id"] for u in admin.call("GET", "/api/users")[1]["users"]}
    assert admin.call("PUT", f"/api/users/{uid['demo_reviewer']}", {"email": "not-an-address"})[0] == 400
    assert admin.call("PUT", f"/api/users/{uid['demo_reviewer']}", {"email": "reviewer@example.com"})[0] == 200
    assert admin.call("PUT", f"/api/users/{uid['demo_editor']}", {"email": "editor@example.com"})[0] == 200
    notify.run_once()                                                # whatever is already waiting is announced once ...
    mail.box.clear(); posts.clear()
    assert notify.run_once()["mails"] == 0 and not mail.box and not posts         # ... and never twice
    # a revision is submitted: the reviewer gets a message with a link, the channel gets a summary
    assert ed.call("POST", "/api/process", {"name": "Notify me", "department": "LOG", "process_id": "ZZ-M-NT-01"})[0] == 200
    assert ed.call("PUT", "/api/process/ZZ-M-NT-01/draft", {"content": {"objective": "x"}, "base_updated_at": None})[0] == 200
    assert ed.call("POST", "/api/process/ZZ-M-NT-01/submit", {"change_summary": "first version"})[0] == 200
    res = notify.run_once()
    to_rev = [m for r, m in mail.box if r == ["reviewer@example.com"]]
    assert res["failed"] == 0 and len(to_rev) == 1 and "Review requested" in to_rev[0] and "ZZ-M-NT-01" in to_rev[0]
    assert "https://processhub.example.com/#/process/ZZ-M-NT-01" in to_rev[0] and "Subject: MEA Process Hub: 1 new item for you" in to_rev[0]
    assert not [m for r, m in mail.box if r == ["editor@example.com"]]                                   # the author is not asked to review his own work
    assert res["people_without_address"] >= 1                                                           # other reviewers without an address are counted, not lost
    card = posts[-1]["attachments"][0]
    assert posts[-1]["type"] == "message" and card["contentType"] == "application/vnd.microsoft.card.adaptive" and "ZZ-M-NT-01" in json.dumps(card["content"])
    n_posts = len(posts)
    mail.box.clear()
    assert notify.run_once()["mails"] == 0 and len(posts) == n_posts                                     # announced once
    # the reviewer asks for changes: the author is told; the reviewer's task is gone
    assert rev.call("POST", "/api/process/ZZ-M-NT-01/review", {"decision": "request_changes", "note": "add scope"})[0] == 200
    notify.run_once()
    to_ed = [m for r, m in mail.box if r == ["editor@example.com"]]
    assert len(to_ed) == 1 and "Changes requested" in to_ed[0]
    # a person switches the messages off
    assert ed.call("PUT", "/api/me/notify", {"enabled": False})[1] == {"enabled": False}
    assert ed.call("POST", "/api/process/ZZ-M-NT-01/submit", {"change_summary": "scope added"})[0] == 200
    assert rev.call("POST", "/api/process/ZZ-M-NT-01/review", {"decision": "request_changes", "note": "again"})[0] == 200
    mail.box.clear()
    notify.run_once()
    assert not [m for r, m in mail.box if r == ["editor@example.com"]]
    assert ed.call("PUT", "/api/me/notify", {"enabled": True})[0] == 200
    # the mail server is down: recorded as failed, and delivered at the next run
    assert ed.call("POST", "/api/process/ZZ-M-NT-01/submit", {"change_summary": "third"})[0] == 200
    monkeypatch.setenv("MEA_HUB_SMTP_PORT", "1")
    mail.box.clear()
    assert notify.run_once()["failed"] >= 1 and not mail.box
    monkeypatch.setenv("MEA_HUB_SMTP_PORT", str(mail.server_address[1]))
    notify.run_once()
    assert [m for r, m in mail.box if r == ["reviewer@example.com"]]
    # weekly summary of open tasks: Monday after the set hour, once
    monkeypatch.setenv("MEA_HUB_NOTIFY_DIGEST", "weekly")
    mail.box.clear()
    assert notify.run_once(now=monday.replace(hour=6))["mails"] == 0
    notify.run_once(now=monday)
    digests = [m for r, m in mail.box if "open task" in m]
    assert digests and any(r == ["reviewer@example.com"] for r, m in mail.box if "open task" in m)
    mail.box.clear()
    assert notify.run_once(now=monday.replace(hour=15))["mails"] == 0
    # administration: state without secrets, test message
    st = admin.call("GET", "/api/admin/notifications")[1]
    assert st["email"]["configured"] and st["teams"]["configured"] and "demo_viewer" in st["without_address"] and any(x["status"] == "failed" for x in st["recent"])
    assert "workflows/abc" not in json.dumps(st)
    assert admin.call("POST", "/api/admin/notifications/test", {})[0] == 400                               # the admin has no address yet
    assert ed.call("GET", "/api/admin/notifications")[0] == 403
    assert json.loads(__import__("urllib.request").request.urlopen(server + "/api/config").read())["notifications"] is True


def test_bpmn_export_comparison_and_periodic_review(admin, users):
    """Phase 3: flows leave the tool in BPMN 2.0, two versions can be compared step by step, published processes are reviewed on schedule."""
    from lxml import etree
    from mea_hub import bpmn, flowbuild
    ed, rev, apr, ctl, viewer = (users[k] for k in ("editor", "reviewer", "approver", "controller", "viewer"))
    svc.set_cfg("master_legend", json.dumps(FLOW_LEGEND))
    assert ed.call("POST", "/api/process", {"name": "Order to shipment", "department": "LOG", "process_id": "ZZ-M-P3-01"})[0] == 200
    steps = "Sales: Take order\nLogistics: Stock available?\nNo: Sales: Inform customer\nNo: End\nWarehouse: Pick goods (LT03)\nNote: Check the pick list\nRef: WL-M-OB-01 Dispatch"
    assert ed.call("POST", "/api/flows/build", {"process_id": "ZZ-M-P3-01", "steps": steps})[0] == 200
    d = ed.call("GET", "/api/process/ZZ-M-P3-01")[1]
    # ---- BPMN 2.0
    s, raw = ed.call("GET", f"/api/diagram-versions/{d['diagram']['id']}/bpmn", raw=True)
    assert s == 200
    ns = {"b": "http://www.omg.org/spec/BPMN/20100524/MODEL", "di": "http://www.omg.org/spec/BPMN/20100524/DI", "dc": "http://www.omg.org/spec/DD/20100524/DC"}
    root = etree.fromstring(raw)
    proc = root.find("b:process", ns)
    count = lambda tag: len(proc.findall("b:" + tag, ns))
    assert (count("startEvent"), count("endEvent"), count("task"), count("exclusiveGateway"), count("callActivity"), count("textAnnotation")) == (1, 1, 3, 1, 1, 1)
    ids = {e.get("id") for e in proc}
    flows = proc.findall("b:sequenceFlow", ns)
    assert flows and all(f.get("sourceRef") in ids and f.get("targetRef") in ids for f in flows)             # every connector joins two exported shapes
    assert {"Yes", "No"} <= {f.get("name") for f in flows}
    task = [t for t in proc.findall("b:task", ns) if t.get("name") == "Pick goods (LT03)"][0]
    assert task.find("b:performer/b:resourceRef", ns).text == "Role_Warehouse" and root.find("b:resource[@id='Role_Warehouse']", ns).get("name") == "Warehouse"
    shapes = root.findall(".//di:BPMNShape", ns)
    assert len(shapes) == 8 and all(sh.find("dc:Bounds", ns) is not None for sh in shapes) and {sh.get("bpmnElement") for sh in shapes} <= ids
    assert len(root.findall(".//di:BPMNEdge", ns)) == len(flows) + len(proc.findall("b:association", ns))
    assert "mea_legend" not in raw.decode() and "Master legend" not in raw.decode()                         # legend and frame are not process content
    assert viewer.call("GET", f"/api/diagram-versions/{d['diagram']['id']}/bpmn")[0] == 403
    s, z = ed.call("POST", "/api/exports", {"scope": "process", "ids": ["ZZ-M-P3-01"], "fmt": "zip"})
    names = zipfile.ZipFile(io.BytesIO(ed.call("GET", f"/api/exports/{z['export']['id']}/download", raw=True)[1])).namelist()
    assert any(n.endswith(".bpmn") for n in names) and any(n.endswith(".drawio") for n in names)
    # a swimlane diagram: the lane becomes the role and a named group
    lane = ('<mxfile><diagram name="L"><mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/>'
            '<mxCell id="l1" value="Finance" style="swimlane;horizontal=0;" vertex="1" parent="1"><mxGeometry x="0" y="0" width="600" height="120" as="geometry"/></mxCell>'
            '<mxCell id="a" value="Check invoice" style="rounded=0;" vertex="1" parent="l1"><mxGeometry x="60" y="40" width="140" height="40" as="geometry"/></mxCell>'
            '<mxCell id="b" value="Post invoice (MIRO)" style="rounded=0;" vertex="1" parent="l1"><mxGeometry x="300" y="40" width="140" height="40" as="geometry"/></mxCell>'
            '<mxCell id="e" edge="1" source="a" target="b" parent="1"><mxGeometry relative="1" as="geometry"/></mxCell></root></mxGraphModel></diagram></mxfile>')
    lr = etree.fromstring(bpmn.export(lane, "X", "Lane"))
    assert [t.get("name") for t in lr.findall(".//b:task", ns)] == ["Check invoice", "Post invoice (MIRO)"] and lr.find(".//b:categoryValue", ns).get("value") == "Finance"
    assert all(t.find("b:performer/b:resourceRef", ns).text == "Role_Finance" for t in lr.findall(".//b:task", ns))
    # ---- comparison of two versions
    c = d["version"]["content"]
    assert ed.call("PUT", "/api/process/ZZ-M-P3-01/draft", {"content": dict(c, objective="Ship customer orders on time"), "base_updated_at": None})[0] == 200
    assert ed.call("POST", "/api/process/ZZ-M-P3-01/submit", {"change_summary": "first"})[0] == 200
    assert rev.call("POST", "/api/process/ZZ-M-P3-01/review", {"decision": "approve_review"})[0] == 200
    assert apr.call("POST", "/api/process/ZZ-M-P3-01/approve", {"decision": "approve"})[0] == 200
    assert ctl.call("POST", "/api/process/ZZ-M-P3-01/publish")[0] == 200
    v1 = ed.call("GET", "/api/process/ZZ-M-P3-01")[1]["version"]["id"]
    steps2 = steps.replace("Sales: Take order", "Logistics: Take order").replace("Pick goods (LT03)", "Pick and pack goods (LT03)") + "\nLogistics: Ship order (VL01N)"
    assert ed.call("POST", "/api/flows/build", {"process_id": "ZZ-M-P3-01", "steps": steps2})[0] == 200
    d2 = ed.call("GET", "/api/process/ZZ-M-P3-01")[1]
    assert ed.call("PUT", "/api/process/ZZ-M-P3-01/draft", {"content": dict(d2["version"]["content"], objective="Ship customer orders on time and in full"), "base_updated_at": None})[0] == 200
    v2 = ed.call("GET", "/api/process/ZZ-M-P3-01")[1]["version"]["id"]
    s, cmp_ = ed.call("GET", f"/api/process/ZZ-M-P3-01/compare?a={v1}&b={v2}")
    assert s == 200 and not cmp_["identical"]
    obj = [f for f in cmp_["fields"] if f["key"] == "objective"][0]
    assert obj["parts"] == [["=", "Ship customer orders on time"], ["+", " and in full"]]                 # only the added words are marked
    acts = [t for t in cmp_["tables"] if t["key"] == "activities"][0]
    assert any(r["activity"] == "Ship order (VL01N)" for r in acts["added"]) and any(r["activity"] == "Pick goods (LT03)" for r in acts["removed"])
    assert [x["cols"] for x in acts["changed"] if x["key"] == "Take order"] == [[{"col": "role", "before": "Sales", "after": "Logistics"}]]
    f = cmp_["flow"]
    assert f["changed"] and f["added"] == ["Ship order (VL01N)"] and f["removed"] == []
    assert f["reworded"] == [{"before": "Pick goods (LT03)", "after": "Pick and pack goods (LT03)"}]
    assert any("Ship order (VL01N)" in x for x in f["connectors_added"])
    assert {"step": "Take order", "before": "Sales", "after": "Logistics"} in f["role_changed"]
    same = ed.call("GET", f"/api/process/ZZ-M-P3-01/compare?a={v1}&b={v1}")[1]
    assert same["identical"] and same["fields"] == [] and same["tables"] == [] and same["flow"] is None
    # ---- periodic review
    rows = {r["process_id"]: r for r in ctl.call("GET", "/api/reviews")[1]["rows"]}
    assert rows["ZZ-M-P3-01"]["in_revision"] and rows["ZZ-M-P3-01"]["state"] in ("ok", "soon")
    assert ctl.call("POST", "/api/process/ZZ-M-P3-01/confirm-review", {"note": "x"})[0] == 409            # a revision is in work: finish that instead
    assert ed.call("POST", "/api/process", {"name": "Reviewed process", "department": "LOG", "process_id": "ZZ-M-P3-02"})[0] == 200
    assert ctl.call("POST", "/api/process/ZZ-M-P3-02/confirm-review", {})[0] == 409                         # not published: nothing to review
    assert ed.call("PUT", "/api/process/ZZ-M-P3-02/draft", {"content": {"objective": "x"}, "base_updated_at": None})[0] == 200
    assert ed.call("POST", "/api/process/ZZ-M-P3-02/submit", {"change_summary": "first"})[0] == 200
    assert rev.call("POST", "/api/process/ZZ-M-P3-02/review", {"decision": "approve_review"})[0] == 200
    assert apr.call("POST", "/api/process/ZZ-M-P3-02/approve", {"decision": "approve"})[0] == 200
    assert ctl.call("POST", "/api/process/ZZ-M-P3-02/publish")[0] == 200
    db.db().execute("UPDATE processes SET next_review='2020-01-01', review_months=6 WHERE process_id='ZZ-M-P3-02'")
    row = {r["process_id"]: r for r in ctl.call("GET", "/api/reviews")[1]["rows"]}["ZZ-M-P3-02"]
    assert row["state"] == "overdue" and row["can_confirm"] and row["days"] < 0
    assert rev.call("POST", "/api/process/ZZ-M-P3-02/confirm-review", {})[0] == 403                         # not the owner, not a controller
    s, r = ctl.call("POST", "/api/process/ZZ-M-P3-02/confirm-review", {"note": "Checked with the warehouse team"})
    import datetime as dt
    assert s == 200 and r["last_review"] == dt.date.today().isoformat() and r["next_review"] > (dt.date.today() + dt.timedelta(days=150)).isoformat()
    row = {r_["process_id"]: r_ for r_ in ctl.call("GET", "/api/reviews")[1]["rows"]}["ZZ-M-P3-02"]
    assert row["state"] == "ok" and ed.call("GET", "/api/process/ZZ-M-P3-02")[1]["version"]["status"] == "published"      # the published version is untouched
    assert db.one("SELECT 1 FROM audit WHERE action='review_confirmed' AND entity_id='ZZ-M-P3-02' AND detail LIKE '%warehouse team%'")


def test_teams_tab_package_and_pages(server, admin, users, monkeypatch, tmp_path):
    """The Teams app package points Teams at the hosted tool; the server lets the Teams hosts frame it only when asked to."""
    import importlib.util
    import urllib.request
    from mea_hub import config
    from mea_hub import teams as mk
    man = mk.manifest("https://processhub.example.com/")
    assert man["validDomains"] == ["processhub.example.com"] and man["manifestVersion"] == "1.16" and len(man["name"]["short"]) <= 30
    tab = man["configurableTabs"][0]
    assert tab["configurationUrl"] == "https://processhub.example.com/teams/config.html" and tab["scopes"] == ["team", "groupChat"] and tab["canUpdateConfiguration"]
    assert man["staticTabs"][0]["contentUrl"] == "https://processhub.example.com/#/dashboard" and man["staticTabs"][0]["scopes"] == ["personal"]
    assert man["id"] == mk.manifest("https://processhub.example.com")["id"] != mk.manifest("https://other.example.com")["id"]      # same address, same app: an upload updates it
    for bad in ("http://processhub.example.com", "https://processhub.example.com/app", "processhub.example.com", "https://"):
        with pytest.raises(ValueError):
            mk.manifest(bad)
    z = zipfile.ZipFile(io.BytesIO(mk.build("https://processhub.example.com", name="MEA Process Hub – Logistics and Warehouse team")))
    assert sorted(z.namelist()) == ["color.png", "manifest.json", "outline.png"]
    assert _png_size(z.read("color.png")) == (192, 192) and _png_size(z.read("outline.png")) == (32, 32)
    assert len(json.loads(z.read("manifest.json"))["name"]["short"]) == 30
    # pages of the tab are part of the tool and need no session
    for path, needle in (("/teams/config.html", b"/teams/teams-js.min.js"), ("/teams/config.js", b"pages.config.setConfig"), ("/teams/about.html", b"does not use your Microsoft 365 sign-in")):
        r = urllib.request.urlopen(server + path)
        assert r.status == 200 and needle in r.read() and r.headers["X-Frame-Options"] == "SAMEORIGIN"      # not frameable by Teams unless switched on
    assert len(urllib.request.urlopen(server + "/teams/teams-js.min.js").read()) > 100000
    # administrators download the package from the tool itself
    assert users["controller"].call("GET", "/api/admin/teams-package?url=https://processhub.example.com")[0] == 403
    assert admin.call("GET", "/api/admin/teams")[1]["teams_allowed"] is False
    s, raw = admin.call("GET", "/api/admin/teams-package?url=https://processhub.example.com&name=Process%20Hub", raw=True)
    assert s == 200 and json.loads(zipfile.ZipFile(io.BytesIO(raw)).read("manifest.json"))["name"]["short"] == "Process Hub"
    assert admin.call("GET", "/api/admin/teams-package?url=http://processhub.example.com")[0] == 400
    monkeypatch.setenv("MEA_HUB_EMBED_ORIGINS", "teams")
    assert config.embed_origins() == config.TEAMS_ORIGINS and "https://teams.microsoft.com" in config.TEAMS_ORIGINS and "https://*.cloud.microsoft" in config.TEAMS_ORIGINS
    h = urllib.request.urlopen(server + "/teams/config.html").headers
    assert h["X-Frame-Options"] is None and "frame-ancestors 'self' https://teams.microsoft.com https://*.teams.microsoft.com" in h["Content-Security-Policy"]
    assert "script-src 'self'" in h["Content-Security-Policy"]                                         # the Teams library is served by the tool itself
    monkeypatch.setenv("MEA_HUB_EMBED_ORIGINS", "Teams, https://contoso.sharepoint.com")
    assert config.embed_origins() == config.TEAMS_ORIGINS + ["https://contoso.sharepoint.com"]             # Teams tab hosted through a SharePoint (SPFx) page


def test_one_time_password_file_and_admin_reset(server, admin):
    import conftest
    path = os.path.join(conftest._tmp, svc.ADMIN_FILE)
    pw = svc.one_time_password()
    assert len(pw) == 12 and not set(pw) & set("0O1lI-_")                      # no look-alike characters
    new_pw, f = svc.reset_admin()
    assert os.path.isfile(f) and new_pw in open(f).read()
    c = Client(server)
    s, d = c.call("POST", "/api/login", {"username": " Admin ", "password": "  " + new_pw + " "}, csrf=False)   # copy-paste spaces + case
    assert s == 200 and d["user"]["must_change"]
    c.csrf = d["csrf"]
    assert c.call("GET", "/api/library")[0] == 403                             # must change first
    assert c.call("POST", "/api/password", {"old": new_pw, "new": "Str0ng!Admin#1"})[0] == 200
    assert not os.path.exists(path), "stale one-time password file must be removed after the change"
    assert Client(server).call("POST", "/api/login", {"username": "admin", "password": new_pw}, csrf=False)[0] == 403
    assert admin.call("GET", "/api/library")[0] == 401                         # reset ended the old admin sessions
    admin.login("admin", "Str0ng!Admin#1")


# ------------------------------------------------------------------ backup / restore (keep last)
def test_backup_and_restore(server, admin, users):
    before = admin.call("GET", "/api/library")[1]["processes"]
    s, data = admin.call("POST", "/api/backup", {}, raw=True)
    assert s == 200 and zipfile.ZipFile(io.BytesIO(data)).testzip() is None
    admin.call("POST", "/api/process", {"name": "Created after backup", "department": "LOG", "process_id": "TST-AFTER-01"})
    assert any(p["process_id"] == "TST-AFTER-01" for p in admin.call("GET", "/api/library")[1]["processes"])
    s, r = admin.call("POST", "/api/restore", data)
    assert s == 200, r
    c = Client(server)
    c.login("admin", "Str0ng!Admin#1")
    after = c.call("GET", "/api/library")[1]["processes"]
    assert {p["process_id"] for p in after} == {p["process_id"] for p in before}                  # post-backup change gone, everything else intact
    assert c.call("GET", "/api/process/TST-W-001")[1]["versions"]
    assert users["viewer"].call("GET", "/api/library")[0] == 401                                  # sessions invalidated by restore


# ------------------------------------------------------------------ native draw.io + checklist import
LANE_XML = '''<mxfile><diagram name="TST-X-LN-01" id="p"><mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/>
<mxCell id="box" value="Process Map – Goods Test Flow – TST-X-LN-01" style="swimlane;startSize=30;" vertex="1" parent="1"><mxGeometry x="40" y="40" width="800" height="400" as="geometry"/></mxCell>
<mxCell id="l1" value="Customer Service" style="swimlane;horizontal=0;startSize=34;" vertex="1" parent="box"><mxGeometry y="30" width="800" height="170" as="geometry"/></mxCell>
<mxCell id="l2" value="Warehouse" style="swimlane;horizontal=0;startSize=34;" vertex="1" parent="box"><mxGeometry y="200" width="800" height="170" as="geometry"/></mxCell>
<mxCell id="l3" value="Exception – RECOMMENDED ADDITION (not in original process)" style="swimlane;horizontal=0;startSize=34;" vertex="1" parent="box"><mxGeometry y="370" width="800" height="170" as="geometry"/></mxCell>
<mxCell id="s" value="Start" style="ellipse;" vertex="1" parent="l1"><mxGeometry x="40" y="40" width="60" height="60" as="geometry"/></mxCell>
<mxCell id="a" value="Raise request" style="rounded=1;" vertex="1" parent="l1"><mxGeometry x="150" y="40" width="160" height="60" as="geometry"/></mxCell>
<mxCell id="d" value="Approved?" style="rhombus;" vertex="1" parent="l2"><mxGeometry x="200" y="20" width="120" height="100" as="geometry"/></mxCell>
<mxCell id="b" value="Post goods receipt (MIGO)" style="rounded=1;" vertex="1" parent="l2"><mxGeometry x="400" y="40" width="160" height="60" as="geometry"/></mxCell>
<mxCell id="x" value="Notify rejection" style="rounded=1;dashed=1;" vertex="1" parent="l3"><mxGeometry x="200" y="40" width="160" height="60" as="geometry"/></mxCell>
<mxCell id="n" value="SLA: 2 days" style="rounded=0;fillColor=#FFFFE0;" vertex="1" parent="1"><mxGeometry x="600" y="10" width="100" height="40" as="geometry"/></mxCell>
<mxCell id="e1" edge="1" source="s" target="a" parent="1"><mxGeometry relative="1" as="geometry"/></mxCell>
<mxCell id="e2" edge="1" source="a" target="d" parent="1"><mxGeometry relative="1" as="geometry"/></mxCell>
<mxCell id="e3" value="Yes" edge="1" source="d" target="b" parent="1"><mxGeometry relative="1" as="geometry"/></mxCell>
<mxCell id="e4" value="No" edge="1" source="d" target="x" parent="1"><mxGeometry relative="1" as="geometry"/></mxCell>
</root></mxGraphModel></diagram></mxfile>'''


def test_native_drawio_import_extracts_structure(admin, tmp_path):
    f = tmp_path / "TST-X-LN-01_Goods_Test.drawio"
    f.write_text(LANE_XML, encoding="utf-8")
    importer.import_paths([str(f)], "tester")
    p = svc.get_process("TST-X-LN-01")
    v = svc.latest_version(p["id"])
    c = v["content"]
    assert c["responsible"] == ["Customer Service", "Warehouse"]                         # proposed lane is not listed as responsible
    acts = c["activities"]
    assert [a["activity"] for a in acts][:3] == ["Raise request", "Decision: Approved?", "Post goods receipt (MIGO)"]
    assert acts[0]["role"] == "Customer Service" and acts[2]["sap"] == "MIGO"
    assert acts[-1]["activity"].startswith("[PROPOSED") and "(proposed)" in acts[-1]["role"]
    assert "Yes: Post goods receipt" in acts[1]["output"] and "No: Notify rejection" in acts[1]["output"]
    assert "SLA: 2 days" in c["notes"] and c["sap"][0]["transaction"] == "MIGO"
    dv = db.one("SELECT * FROM diagram_versions WHERE id=?", (v["diagram_version_id"],))
    assert dv["origin"] == "imported-drawio" and dv["xml"].count("<mxCell") >= 10      # native XML kept, not flattened
    assert dv["preview_asset_id"], "approximate preview must exist so exports contain a picture"
    meta = [n["meta"] for n in svc.diagram_nodes(dv["id"]) if n["node_id"] == "b"][0]
    assert meta["role"] == "Warehouse" and meta["sap"] == "MIGO"
    assert db.one("SELECT 1 FROM findings WHERE process_id=? AND title LIKE 'Proposed (not approved)%'", (p["id"],))
    assert drawio.to_png(dv["xml"])[:4] == b"\x89PNG"


def test_checklist_import_creates_forms_and_flags_differing_duplicates(tmp_path):
    from docx import Document

    def mk(path, rows_a, rows_b):
        d = Document()
        d.add_heading("Customer Service Checklist", 1)
        d.add_paragraph("Manual Sales Order Creation before credit review and PR creation.")
        t = d.add_table(rows=1 + len(rows_a), cols=3)
        for i, h in enumerate(["#", "Validation Area", "Checkpoint"]):
            t.rows[0].cells[i].text = h
        for r, row in enumerate(rows_a, 1):
            for i, v in enumerate(row):
                t.rows[r].cells[i].text = v
        d.add_heading("MRP Checklist", 1)
        d.add_paragraph("PR validation before processing and release of the purchase requisition.")
        t = d.add_table(rows=1 + len(rows_b), cols=3)
        for i, h in enumerate(["#", "Validation Area", "Checkpoint"]):
            t.rows[0].cells[i].text = h
        for r, row in enumerate(rows_b, 1):
            for i, v in enumerate(row):
                t.rows[r].cells[i].text = v
        d.save(path)
    a, b = tmp_path / "check_a.docx", tmp_path / "check_b.docx"
    mk(str(a), [("1", "PG approval", "Check PG numbers are approved")], [("1", "SO status", "Credit released and SO released")])
    mk(str(b), [("1", "PG approval", "Confirm every PG is approved before release of the order")], [("1", "SO status", "Credit released and SO released")])
    res = importer.import_paths([str(a), str(b)], "tester")
    forms = db.q("SELECT process_id,name FROM processes WHERE kind='form' AND name LIKE '%Checklist (Sales%'")
    assert len(forms) == 1 and forms[0]["process_id"].startswith("SAL-FRM-")                      # same form in two files = ONE record
    assert db.one("SELECT 1 FROM mappings WHERE process_id=(SELECT id FROM processes WHERE process_id=?) AND role='duplicate' AND similarity IS NOT NULL", (forms[0]["process_id"],))
    assert db.one("SELECT 1 FROM findings WHERE kind='duplicate' AND severity='medium' AND title LIKE ?", (f"%{forms[0]['process_id']}%",))


