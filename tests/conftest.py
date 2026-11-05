import io
import json
import os
import sys
import tempfile
import threading
import urllib.error
import urllib.request
import http.cookiejar

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
_tmp = tempfile.mkdtemp(prefix="mea_hub_test_")
os.environ["MEA_HUB_DATA"] = _tmp
os.environ["MEA_HUB_DRAWIO_DIR"] = os.path.join(_tmp, "no_drawio")

from mea_hub import db, service as svc          # noqa: E402
from mea_hub.server import make_server          # noqa: E402


@pytest.fixture(scope="session")
def server():
    svc.bootstrap(demo_users=True)
    srv = make_server("127.0.0.1", 0)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}"
    srv.shutdown()


class Client:
    def __init__(self, base):
        self.base, self.csrf = base, None
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self, method, path, body=None, raw=False, headers=None, csrf=True):
        h = {"Content-Type": "application/json"}
        if self.csrf and csrf:
            h["X-CSRF-Token"] = self.csrf
        h.update(headers or {})
        data = body if isinstance(body, bytes) else (json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=h)
        try:
            r = self.op.open(req)
            payload = r.read()
        except urllib.error.HTTPError as e:
            payload, r = e.read(), e
        ct = r.headers.get("Content-Type", "")
        out = payload if raw or not ct.startswith("application/json") else json.loads(payload or b"{}")
        return r.status if hasattr(r, "status") else r.code, out

    def login(self, user, pw="ChangeMe!123"):
        s, d = self.call("POST", "/api/login", {"username": user, "password": pw}, csrf=False)
        assert s == 200, d
        self.csrf = d["csrf"]
        return d["user"]


@pytest.fixture(scope="session")
def admin(server):
    c = Client(server)
    pw = open(os.path.join(_tmp, "FIRST_RUN_ADMIN_PASSWORD.txt")).read().split("password: ")[1].split()[0]
    c.login("admin", pw)
    assert c.call("POST", "/api/password", {"old": pw, "new": "Str0ng!Admin#1"})[0] == 200
    return c


@pytest.fixture(scope="session")
def users(server, admin):
    out = {}
    for r in ("controller", "dept_owner", "editor", "reviewer", "approver", "viewer"):
        c = Client(server)
        c.login("demo_" + r)
        out[r] = c
    return out


def make_docx(path, sections, title="Logistics Test Document"):
    """sections: list of (heading, chart_id, body, responsible, png_bytes|None)"""
    from docx import Document
    d = Document()
    d.add_paragraph(title)
    for head, cid, body, resp, png in sections:
        d.add_heading(head, level=1)
        d.add_paragraph(body)
        if cid:
            d.add_paragraph(f"Process flow chart ID: {cid}")
        if resp:
            d.add_paragraph("Responsible:\n" + "\n".join("■ " + r for r in resp))
        if png:
            d.add_picture(io.BytesIO(png))
    d.add_heading("Escalation Matrix and KPIs", level=1)
    t = d.add_table(rows=2, cols=4)
    for i, v in enumerate(["Stage", "Task / Reminder to", "Time Period", "Escalation"]):
        t.rows[0].cells[i].text = v
    for i, v in enumerate(["Level 1", "Supervisor", "+1 day", "Reminder"]):
        t.rows[1].cells[i].text = v
    d.save(path)


def big_png(w=500, h=300):
    from PIL import Image, ImageDraw
    import random
    im = Image.new("RGB", (w, h), "white")
    dr = ImageDraw.Draw(im)
    rnd = random.Random(w)
    for _ in range(4000):
        dr.point((rnd.randrange(w), rnd.randrange(h)), fill=(rnd.randrange(255), rnd.randrange(255), rnd.randrange(255)))
    dr.rectangle([50, 50, 200, 120], outline="black")
    b = io.BytesIO()
    im.save(b, "PNG")
    return b.getvalue()
