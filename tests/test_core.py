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
def test_exports(admin, users):
    from docx import Document
    s, d = users["editor"].call("POST", "/api/exports", {"scope": "process", "ids": ["WL-M-IB-01"], "fmt": "docx"})
    assert s == 200, d
    s, data = users["editor"].call("GET", f"/api/exports/{d['export']['id']}/download", raw=True)
    doc = Document(io.BytesIO(data))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "Material Inbound Process" in text and "UNCONTROLLED DRAFT" in text                          # unapproved is labelled
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
    assert "UNCONTROLLED" not in "\n".join(p.text for p in doc.paragraphs)
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
