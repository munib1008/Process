"""Read-only publication of the library ("site" export): a folder that needs no server.

    processhub/handbook.json     departments, processes (text, tables, pictures, relations), legend, snapshot data
    processhub/flows/*.png       the document pictures of the flows (flow only, long flows in parts)
    processhub/assets/*          pictures used inside the text sections
    processhub/index.html        opens the library in a browser on any static web host
    processhub/viewer.js         the reader (the same code that the SharePoint web part contains)

Upload the folder to a SharePoint document library and point the MEA Process Hub web part at it (docs/SHAREPOINT_PUBLISHING.md):
readers then use their Microsoft 365 sign-in and the library's permissions; the tool itself stays the authoring workplace.
Nothing can be edited in the publication; a new export replaces it."""
import io
import json
import os
import re
import zipfile

from . import __version__, config, service as svc

FOLDER = "processhub"
TEXT_FIELDS = ("objective", "scope", "trigger", "inputs", "outputs", "risks", "evidence", "forms", "notes")
TABLES = ("activities", "raci", "sap", "kpis", "escalation")
INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MEA Process Hub – published library</title>
<style>html,body{margin:0;height:100%}</style>
</head>
<body>
<div id="mea-process-hub" style="min-height:100vh"></div>
<script src="viewer.js"></script>
<script>MEAProcessHubViewer.mount(document.getElementById("mea-process-hub"), ".");</script>
</body>
</html>
"""
README = """MEA Process Hub - published library (read-only)

Generated: {when}   Snapshot: {snap}   Processes: {n}{draft}

SharePoint: upload the folder "processhub" to a document library and enter its address in the
MEA Process Hub web part (see docs/SHAREPOINT_PUBLISHING.md of the tool).
Any web server: serve the folder and open index.html.
Opening index.html directly from a disk does not work in most browsers (they block reading handbook.json from file://).
A new export replaces this folder; nothing in it is meant to be edited by hand.
"""


def _safe(name):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:80]


def viewer_js() -> bytes:
    with open(os.path.join(config.STATIC_DIR, "viewer", "viewer.js"), "rb") as f:
        return f.read()


def build_site(snap) -> bytes:
    """FORMATS entry of the exporter: the publication as one ZIP."""
    files, depts = {}, []

    def asset(m):
        try:
            mime, data = svc.asset_bytes(int(m.group(1)))
        except svc.NotFound:
            return 'src=""'
        ext = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif"}.get(mime)
        if not ext:
            return 'src=""'
        files[f"assets/{m.group(1)}.{ext}"] = data
        return f'src="assets/{m.group(1)}.{ext}"'
    for g in snap["departments"]:
        procs = []
        for p in g["processes"]:
            c = p["content"]
            pics = []
            if p["diagram"]:
                res = svc.picture_set(p["diagram"]["xml"], p["diagram"]["png"], p["diagram"].get("cover"), snap.get("flow_picture", "flow"))
                for i, pic in enumerate(res["pictures"]):
                    name = f"flows/{_safe(p['process_id'])}_{i + 1}.png"
                    files[name] = pic["png"]
                    pics.append(dict(file=name, label=pic["label"], part=(i + 1) if len(res["pictures"]) > 1 else 0, of=len(res["pictures"])))
            rec = dict(id=p["process_id"], name=p["name"], kind=p["kind"], status=p["status"], status_label=p["status_label"], version=p["version"],
                       owner=p["owner"] or "", reviewer=p["reviewer"] or "", approved_by=p["approved_by"] or "", published_at=p["published_at"] or "",
                       category=p["category"] or "", countries=p["countries"] or "", responsible=c.get("responsible", []),
                       raci_draft=bool(c.get("raci_draft")), pictures=pics,
                       flow_revision=p["diagram"]["ver_no"] if p["diagram"] else None,
                       sections=[dict(title=s["title"], html=re.sub(r'src="/api/assets/(\d+)"', asset, s["html"])) for s in c.get("sections", [])],
                       relations=[dict(type=r["rel_type"], id=r["process_id"], name=r["name"]) for r in p.get("relations", [])])
            for k in TEXT_FIELDS:
                rec[k] = c.get(k, "")
            for k in TABLES:
                rec[k] = c.get(k, [])
            procs.append(rec)
        depts.append(dict(code=g["code"], name=g["name"], processes=procs))
    book = dict(format=1, tool_version=__version__, title=snap["title"], org=snap["org"], classification=snap["classification"], region=snap["region"],
                generated_at=snap["generated_at"], generated_by=snap["user_display"], snapshot=snap["hash"], count=snap["count"], unapproved=snap["unapproved"],
                legend=[dict(role=r, color=c) for r, c in snap.get("legend", [])], departments=depts)
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{FOLDER}/handbook.json", json.dumps(book, ensure_ascii=False))
        for name, data in files.items():
            z.writestr(f"{FOLDER}/{name}", data)
        z.writestr(f"{FOLDER}/index.html", INDEX_HTML)
        z.writestr(f"{FOLDER}/viewer.js", viewer_js())
        z.writestr("README.txt", README.format(when=snap["generated_at"], snap=snap["hash"], n=snap["count"],
                                               draft=f"   UNCONTROLLED DRAFT: {snap['unapproved']} not approved" if snap["unapproved"] else ""))
    return bio.getvalue()
