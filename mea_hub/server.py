"""Local HTTP server (stdlib only): static UI, optional self-hosted draw.io, and the JSON API."""
import gzip
import hashlib
import json
import mimetypes
import os
import re
import tempfile
import traceback
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from . import config, db, drawio, drafts, exporter, flowpic, importer, queries, service as svc

COOKIE = "mea_session"
ROUTES = []


def route(method, pattern, auth=True, csrf=None):
    def deco(fn):
        ROUTES.append((method, re.compile("^" + pattern + "$"), fn, auth, (method != "GET") if csrf is None else csrf))
        return fn
    return deco


class Ctx:
    def __init__(self, h, user, qs, body_raw):
        self.h, self.user, self.qs, self.raw = h, user, qs, body_raw

    def json(self):
        try:
            d = json.loads(self.raw.decode("utf-8") or "{}")
        except ValueError:
            raise svc.Invalid("Request body is not valid JSON.")
        if not isinstance(d, dict):
            raise svc.Invalid("JSON object expected.")
        return d

    def arg(self, k, default=None):
        v = self.qs.get(k)
        return v[0] if v else default


def frame_ancestors():
    """Who may show the app in a frame: the app itself, plus the sites named in MEA_HUB_EMBED_ORIGINS."""
    return "frame-ancestors 'self'" + "".join(" " + o for o in config.embed_origins())


def csp_header(drawio_origin):
    return ("default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
            f"frame-src 'self' {drawio_origin}; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; " + frame_ancestors())


def session_cookie(cookie, https):
    """Cookie attributes for the way the app is reached. Embedded in another site (SharePoint) the browser treats the
    cookie as third-party: it must be SameSite=None + Secure, and Partitioned so that browsers which block third-party
    cookies keep it for that one embedding site. State-changing requests stay protected by the X-CSRF-Token header."""
    if config.embed_origins():
        return cookie.replace("SameSite=Strict", "SameSite=None; Secure; Partitioned")
    return cookie + ("; Secure" if https or os.environ.get("MEA_HUB_SECURE_COOKIE") == "1" else "")


def local_drawio():
    return os.path.isfile(os.path.join(config.DRAWIO_DIR, "index.html"))


COMPRESSIBLE = {"application/json", "application/javascript", "text/javascript", "text/css", "text/html", "text/plain", "image/svg+xml",
                "application/xml", "text/xml", "application/vnd.jgraph.mxfile"}
_GZ_CACHE = {}


class Handler(BaseHTTPRequestHandler):
    server_version = "MEAProcessHub/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        if os.environ.get("MEA_HUB_DEBUG"):
            super().log_message(fmt, *args)

    # ---------------------------------------------------------------- plumbing
    def send_bytes(self, status, data, ctype, extra=None, csp=True, cache="no-store", etag=None, gz_key=None):
        """cache: Cache-Control value. etag: enables 304 revalidation. gz_key: cache key for the gzipped body."""
        if etag and self.headers.get("If-None-Match") == etag and status == 200:
            self.send_response(304)
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", cache)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        enc = None
        if len(data) > 1400 and "gzip" in (self.headers.get("Accept-Encoding") or "") and ctype.split(";")[0] in COMPRESSIBLE:
            if gz_key and gz_key in _GZ_CACHE:
                data = _GZ_CACHE[gz_key]
            else:
                data = gzip.compress(data, 5)
                if gz_key:
                    if len(_GZ_CACHE) > 400:
                        _GZ_CACHE.clear()
                    _GZ_CACHE[gz_key] = data
            enc = "gzip"
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        if enc:
            self.send_header("Content-Encoding", enc)
            self.send_header("Vary", "Accept-Encoding")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        embed = config.embed_origins()
        if embed:                                            # framing is governed by frame-ancestors (X-Frame-Options cannot name other sites)
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        else:
            self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Cache-Control", cache)
        if etag:
            self.send_header("ETag", etag)
        if csp:
            origin = "" if local_drawio() else config.DRAWIO_REMOTE
            self.send_header("Content-Security-Policy", csp_header(origin))
        elif embed and not (extra or {}).get("Content-Security-Policy"):
            self.send_header("Content-Security-Policy", frame_ancestors())      # e.g. the draw.io editor nested inside the embedded app
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def send_json(self, obj, status=200, extra=None):
        self.send_bytes(status, json.dumps(obj, default=str).encode(), "application/json; charset=utf-8", extra)

    def host_ok(self):
        host = (self.headers.get("Host") or "").split(":")[0].lower()
        allowed = {"127.0.0.1", "localhost", "[::1]"} | {h.strip().lower() for h in os.environ.get("MEA_HUB_ALLOW_HOSTS", "").split(",") if h.strip()}
        return host in allowed or getattr(self.server, "allow_any_host", False)

    def current_user(self):
        c = SimpleCookie(self.headers.get("Cookie", ""))
        return (svc.session_user(c[COOKIE].value), c[COOKIE].value) if COOKIE in c else (None, None)

    def handle_any(self):
        try:
            if not self.host_ok():
                return self.send_json({"error": "Host not allowed"}, 403)
            u = urlparse(self.path)
            path = unquote(u.path)
            if path.startswith("/api/"):
                return self.api(path, parse_qs(u.query))
            if path.startswith("/drawio/") or path == "/drawio":
                return self.serve_drawio(path)
            return self.serve_static(path)
        except BrokenPipeError:
            pass
        finally:
            db.close_all_for_thread()

    do_GET = do_POST = do_PUT = do_DELETE = do_HEAD = handle_any

    # ---------------------------------------------------------------- static
    def serve_file(self, root, rel, csp=True, cache="no-cache"):
        rel = rel.lstrip("/") or "index.html"
        full = os.path.realpath(os.path.join(root, rel))
        if not full.startswith(os.path.realpath(root) + os.sep) or not os.path.isfile(full):
            return self.send_bytes(404, b"Not found", "text/plain")
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if full.endswith(".js"):
            ctype = "application/javascript"
        st = os.stat(full)
        etag = f'"{int(st.st_mtime)}-{st.st_size}"'
        if self.headers.get("If-None-Match") == etag:                      # unchanged: no file read at all
            return self.send_bytes(200, b"", ctype, csp=csp, cache=cache, etag=etag)
        with open(full, "rb") as f:
            self.send_bytes(200, f.read(), ctype + ("; charset=utf-8" if ctype.startswith("text/") else ""), csp=csp, cache=cache, etag=etag, gz_key=full + etag)

    def serve_static(self, path):
        if path in ("/", ""):
            path = "/index.html"
        self.serve_file(config.STATIC_DIR, path)

    def serve_drawio(self, path):
        if not local_drawio():
            return self.send_bytes(404, b"Local draw.io copy not installed. Run fetch_drawio.py (see docs/ADMIN_GUIDE.md).", "text/plain")
        rel = path[len("/drawio/"):] if path.startswith("/drawio/") else "index.html"
        self.serve_file(config.DRAWIO_DIR, rel, csp=False, cache="private, max-age=86400")      # the editor is static: let the browser keep it

    # ---------------------------------------------------------------- API
    def api(self, path, qs):
        method = self.command if self.command != "HEAD" else "GET"
        length = int(self.headers.get("Content-Length") or 0)
        limit = config.MAX_UPLOAD_BYTES if path in ("/api/import", "/api/restore", "/api/register-import") else config.MAX_JSON_BYTES
        if length > limit:
            return self.send_json({"error": "Request too large."}, 413)
        raw = self.rfile.read(length) if length else b""
        user, tok = self.current_user()
        for m, rx, fn, auth, csrf in ROUTES:
            mt = rx.match(path)
            if m == method and mt:
                try:
                    if auth and not user:
                        return self.send_json({"error": "Login required."}, 401)
                    if csrf and auth and self.headers.get("X-CSRF-Token") != user["csrf"]:
                        return self.send_json({"error": "Missing or invalid CSRF token."}, 403)
                    if user and user["must_change"] and path not in ("/api/password", "/api/me", "/api/logout"):
                        return self.send_json({"error": "You must change your password first.", "must_change": True}, 403)
                    ctx = Ctx(self, user, qs, raw)
                    ctx.token = tok
                    res = fn(ctx, *mt.groups())
                    if res is None:
                        res = {"ok": True}
                    if isinstance(res, tuple):          # (bytes, ctype, extra headers[, cache-control, etag])
                        return self.send_bytes(200, res[0], res[1], res[2] if len(res) > 2 else None, cache=res[3] if len(res) > 3 else "no-store",
                                               etag=res[4] if len(res) > 4 else None)
                    if isinstance(res, dict) and "_set_cookie" in res:
                        cookie = res.pop("_set_cookie")
                        https = (self.headers.get("X-Forwarded-Proto") or "").split(",")[0].strip().lower() == "https"      # behind an HTTPS proxy
                        extra = {"Set-Cookie": session_cookie(cookie, https)}
                        return self.send_json(res, 200, extra)
                    return self.send_json(res)
                except svc.Forbidden as e:
                    return self.send_json({"error": str(e)}, 403)
                except svc.NotFound as e:
                    return self.send_json({"error": str(e)}, 404)
                except svc.Conflict as e:
                    return self.send_json({"error": str(e), "conflict": True}, 409)
                except (svc.Invalid, drawio.DiagramError, importer.ImportError_) as e:
                    return self.send_json({"error": str(e)}, 400)
                except Exception as e:  # noqa
                    if os.environ.get("MEA_HUB_DEBUG"):
                        traceback.print_exc()
                    svc_log_error(e)
                    return self.send_json({"error": "Internal error. See data/error.log."}, 500)
        self.send_json({"error": "Unknown API endpoint."}, 404)


def svc_log_error(e):
    try:
        with open(os.path.join(config.DATA_DIR, "error.log"), "a") as f:
            f.write(svc.now() + " " + traceback.format_exc() + "\n")
    except Exception:
        pass


def file_resp(data, ctype, name):
    return data, ctype, {"Content-Disposition": f'attachment; filename="{name}"'}


# ====================================================================== routes
@route("POST", "/api/login", auth=False, csrf=False)
def r_login(c):
    d = c.json()
    res = svc.login(d.get("username"), d.get("password"))
    if not res:
        raise svc.Forbidden("Invalid username or password.")
    tok, csrf, user = res
    cookie = f"{COOKIE}={tok}; Path=/; HttpOnly; SameSite=Strict; Max-Age={config.SESSION_HOURS * 3600}"
    return dict(user=user, csrf=csrf, _set_cookie=cookie)


@route("POST", "/api/logout")
def r_logout(c):
    svc.logout(c.token)
    return dict(ok=True, _set_cookie=f"{COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict")


@route("GET", "/api/me", auth=False)
def r_me(c):
    if not c.user:
        return dict(user=None)
    u = dict(c.user)
    csrf = u.pop("csrf")
    return dict(user=u, csrf=csrf)


@route("POST", "/api/password")
def r_password(c):
    d = c.json()
    svc.change_password(c.user, d.get("old"), d.get("new"))


@route("GET", "/api/health", auth=False)
def r_health(c):
    """For a reverse proxy / monitoring: answers without a session and touches the database."""
    return dict(ok=bool(db.one("SELECT 1 ok")), version="1.0.0")


@route("GET", "/api/config", auth=False)
def r_config(c):
    return dict(embeddable=bool(config.embed_origins()), drawio_url=("/drawio/index.html" if local_drawio() else config.DRAWIO_REMOTE + "/"), drawio_local=local_drawio(),
                org=svc.cfg("org_name"), classification=svc.cfg("classification", "Internal"), region=svc.cfg("region_label", "Region MEA"), statuses=svc.STATUS_LABEL, kinds=svc.KINDS, rel_types=svc.REL_TYPES, roles=svc.ROLES,
                templates={k: v[0] for k, v in drawio.TEMPLATES.items()}, comment_categories=svc.COMMENT_CATEGORIES, comment_severities=svc.COMMENT_SEVERITIES,
                comment_statuses=svc.COMMENT_STATUSES, comment_sections=svc.COMMENT_SECTIONS, node_meta_keys=svc.NODE_META_KEYS, version="1.0.0",
                flow_roles=[r["role"] for r in svc.master_legend().get("roles", [])])


@route("GET", "/api/departments")
def r_depts(c):
    return q_all("SELECT * FROM departments ORDER BY sort")


def q_all(sql, args=()):
    return db.q(sql, args)


@route("GET", "/api/tree")
def r_tree(c):
    return dict(departments=queries.tree(c.user))


@route("GET", "/api/library")
def r_library(c):
    return dict(processes=queries.library(c.user, c.arg("dept"), c.arg("status"), c.arg("kind"), c.arg("q")))


@route("GET", "/api/process/([^/]+)")
def r_process(c, pid):
    return queries.process_detail(c.user, pid, c.arg("version"))


@route("POST", "/api/process")
def r_new_process(c):
    p = svc.new_process(c.user, c.json())
    return dict(process_id=p["process_id"])


@route("PUT", "/api/process/([^/]+)/draft")
def r_draft(c, pid):
    v = svc.save_draft(pid, c.user, c.json())
    return dict(updated_at=v["updated_at"], version=v["version"], status=v["status"])


@route("POST", "/api/process/([^/]+)/submit")
def r_submit(c, pid):
    d = c.json()
    v = svc.submit_for_review(pid, c.user, d.get("change_summary", ""), d.get("bump", "minor"))
    return dict(status=v["status"], version=v["version"])


@route("POST", "/api/process/([^/]+)/withdraw")
def r_withdraw(c, pid):
    return dict(status=svc.withdraw(pid, c.user)["status"])


@route("POST", "/api/process/([^/]+)/review")
def r_review(c, pid):
    d = c.json()
    return dict(status=svc.review_decision(pid, c.user, d.get("decision"), d.get("note", ""))["status"])


@route("POST", "/api/process/([^/]+)/approve")
def r_approve(c, pid):
    d = c.json()
    return dict(status=svc.approval_decision(pid, c.user, d.get("decision"), d.get("note", ""))["status"])


@route("POST", "/api/process/([^/]+)/publish")
def r_publish(c, pid):
    v = svc.publish(pid, c.user)
    return dict(status=v["status"], version=v["version"])


@route("POST", "/api/process/([^/]+)/accept-import")
def r_accept(c, pid):
    return dict(status=svc.accept_import(pid, c.user, c.json().get("note", ""))["status"])


@route("POST", "/api/process/([^/]+)/restore")
def r_restore(c, pid):
    d = c.json()
    v = svc.restore_version(pid, c.user, int(d.get("version_id", 0)), d.get("summary", ""))
    return dict(version=v["version"], status=v["status"])


@route("GET", "/api/process/([^/]+)/compare")
def r_compare(c, pid):
    p = svc.get_process(pid)
    svc.need(c.user, "view_all")
    a, b = int(c.arg("a")), int(c.arg("b"))
    for vid in (a, b):
        if svc.get_version(vid)["process_id"] != p["id"]:
            raise svc.Invalid("Version belongs to another process.")
    return svc.compare_versions(a, b)


@route("POST", "/api/process/([^/]+)/comments")
def r_comment(c, pid):
    d = c.json()
    return dict(id=svc.add_comment(pid, c.user, d.get("body"), d.get("category", "comment"), d.get("severity", "info"), d.get("section", ""), d.get("parent_id"), d.get("version_id")))


@route("PUT", "/api/comments/(\\d+)")
def r_comment_upd(c, cid):
    d = c.json()
    svc.update_comment(c.user, int(cid), d.get("status"), d.get("resolution"))


@route("GET", "/api/audit-comments")
def r_audit_comments(c):
    return dict(rows=svc.comments_register(c.user, c.arg("status"), c.arg("category"), c.arg("process"), c.arg("dept")))


@route("GET", "/api/audit-comments.xlsx")
def r_audit_comments_xlsx(c):
    return file_resp(queries.comments_xlsx(c.user), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "MEA_Audit_Comments_Register.xlsx")


@route("POST", "/api/departments")
def r_dept_add(c):
    d = c.json()
    svc.add_department(c.user, d.get("code"), d.get("name"))


@route("POST", "/api/process/([^/]+)/rename")
def r_rename(c, pid):
    d = c.json()
    p = svc.rename_process(c.user, pid, d.get("new_id"), d.get("reason", ""))
    return dict(process_id=p["process_id"])


@route("PUT", "/api/process/([^/]+)/department")
def r_dept(c, pid):
    svc.reassign_department(pid, c.user, int(c.json().get("department_id", 0)))


@route("POST", "/api/process/([^/]+)/finding")
def r_log_finding(c, pid):
    d = c.json()
    svc.log_finding(pid, c.user, d.get("kind", "conflict"), d.get("title", ""), d.get("detail", ""))


@route("GET", "/api/process/([^/]+)/trace")
def r_trace(c, pid):
    svc.need(c.user, "view_all")
    return dict(items=queries.trace(c.user, pid, c.arg("dir", "down")))


@route("POST", "/api/relationships")
def r_rel_add(c):
    d = c.json()
    svc.add_relationship(c.user, d.get("from"), d.get("to"), d.get("type"), d.get("note", ""))


@route("DELETE", "/api/relationships/(\\d+)")
def r_rel_del(c, rid):
    svc.remove_relationship(c.user, int(rid))


# ---- diagrams
@route("GET", "/api/diagrams")
def r_diagrams(c):
    svc.need(c.user, "view_all")
    return dict(diagrams=db.q("""SELECT d.id,d.code,d.title,d.kind,p.process_id,dv.ver_no,dv.validation,dv.origin,dv.created_at,dv.preview_asset_id
        FROM diagrams d LEFT JOIN processes p ON p.id=d.process_id JOIN diagram_versions dv ON dv.diagram_id=d.id AND dv.ver_no=(SELECT MAX(ver_no) FROM diagram_versions WHERE diagram_id=d.id) ORDER BY d.id"""))


@route("POST", "/api/diagrams")
def r_diagram_new(c):
    d = c.json()
    title = (d.get("title") or "Untitled diagram").strip()[:120]
    pid = d.get("process_id")
    if d.get("xml"):
        xml = drawio.normalize(d["xml"])
    else:
        xml = None
    proc = svc.get_process(pid) if pid else None
    if xml is None:                                          # templates are standard tagged flows (frame, master legend, readable by the document link)
        from . import flowbuild
        dept = db.one("SELECT code FROM departments WHERE id=?", (proc["department_id"],)) if proc and proc.get("department_id") else None
        xml = drawio.normalize(flowbuild.build(proc["name"] if proc else title, proc["process_id"] if proc else "", dept["code"] if dept else "",
                                               flowbuild.template_steps(d.get("template", "blank")), svc.master_legend())[0])
    svc.need(c.user, "edit", proc)
    with db.tx():
        if proc:
            existing = svc.latest_version(proc["id"]).get("diagram_version_id")
            if existing:
                did = db.one("SELECT diagram_id FROM diagram_versions WHERE id=?", (existing,))["diagram_id"]
                svc.ensure_draft(proc, c.user)
                return dict(diagram_id=_replace_diagram(did, proc, xml, c.user))
            svc.ensure_draft(proc, c.user)
            did, dv = svc.create_diagram(proc["id"], proc["process_id"], title, xml, "template" if not d.get("xml") else "imported-drawio", None, "Created", c.user)
            svc.reindex(proc["id"])
        else:
            did, dv = svc.create_diagram(None, None, title, xml, "template" if not d.get("xml") else "imported-drawio", None, "Created", c.user, kind="library")
    return dict(diagram_id=did)


@route("POST", "/api/flows/build")
def r_flow_build(c):
    d = c.json()
    return svc.build_flow(c.user, d.get("steps") or "", title=d.get("title") or "", pid_text=d.get("process_id") or None, link=d.get("link", True) is not False)


@route("GET", "/api/flows/steps")
def r_flow_steps(c):
    """Starting text for the builder: the activity table of a process, or the steps of a template."""
    from . import flowbuild
    pid, tpl = c.arg("process_id", ""), c.arg("template", "")
    if tpl:
        return dict(steps=flowbuild.template_steps(tpl))
    proc = svc.get_process(pid)
    svc.need(c.user, "edit", proc)
    v = svc.latest_version(proc["id"])
    content = v["content"] if isinstance(v["content"], dict) else db.jloads(v["content"], {})
    return dict(steps=flowbuild.steps_from_activities(content.get("activities")))


@route("GET", "/api/flow-library")
def r_flow_library(c):
    from . import flowbuild
    return dict(entries=flowbuild.library_entries(svc.master_legend()))


@route("GET", "/api/flow-library.xml")
def r_flow_library_file(c):
    from . import flowbuild
    return (flowbuild.library_xml(svc.master_legend()).encode("utf-8"), "application/xml; charset=utf-8",
            {"Content-Disposition": 'attachment; filename="dormakaba_MEA_shapes.xml"'})


def _replace_diagram(did, proc, xml, user):
    dv = svc._add_dv(did, xml, "imported-drawio", None, "Replaced diagram", user["username"])
    v = svc.open_version(proc["id"])
    db.db().execute("UPDATE process_versions SET diagram_version_id=? WHERE id=?", (dv, v["id"]))
    svc.reindex(proc["id"])
    return did


@route("GET", "/api/diagrams/(\\d+)")
def r_diagram(c, did):
    svc.need(c.user, "view_all")
    d = svc.diagram_info(int(did))
    latest = db.one("SELECT * FROM diagram_versions WHERE diagram_id=? ORDER BY ver_no DESC LIMIT 1", (d["id"],))
    p = db.one("SELECT process_id,name FROM processes WHERE id=?", (d["process_id"],)) if d["process_id"] else None
    approx = bool(latest["preview_asset_id"] is None or (db.one("SELECT role FROM assets WHERE id=?", (latest["preview_asset_id"],)) or {}).get("role") == "preview-approx")
    return dict(diagram=d, latest=dict(id=latest["id"], ver_no=latest["ver_no"], xml=latest["xml"], validation=latest["validation"], preview_asset_id=latest["preview_asset_id"], preview_approx=approx,
                            checks=svc.flow_checks(latest["id"]), picture=flowpic.describe(latest["xml"])),
                process=p, versions=svc.diagram_versions(d["id"]), nodes=svc.diagram_nodes(latest["id"]))


@route("GET", "/api/diagram-versions/(\\d+)/xml")
def r_dv_xml(c, dvid):
    svc.need(c.user, "view_all")
    dv = db.one("SELECT dv.*,d.code FROM diagram_versions dv JOIN diagrams d ON d.id=dv.diagram_id WHERE dv.id=?", (int(dvid),))
    if not dv:
        raise svc.NotFound("Not found")
    return file_resp(dv["xml"].encode(), "application/vnd.jgraph.mxfile", f"{dv['code']}_rev{dv['ver_no']}.drawio")


@route("GET", "/api/diagram-versions/(\\d+)/json")
def r_dv_json(c, dvid):
    svc.need(c.user, "view_all")
    dv = db.one("SELECT * FROM diagram_versions WHERE id=?", (int(dvid),))
    if not dv:
        raise svc.NotFound("Not found")
    return dict(xml=dv["xml"], ver_no=dv["ver_no"], diagram_id=dv["diagram_id"])


@route("GET", "/api/diagram-versions/(\\d+)/svg")
def r_dv_svg(c, dvid):
    svc.need(c.user, "view_all")
    return file_resp(svc.diagram_svg(int(dvid)).encode(), "image/svg+xml", f"diagram_{dvid}.svg")


@route("POST", "/api/diagram-versions/(\\d+)/preview")
def r_preview(c, dvid):
    """Replace an *approximate* server-rendered preview with the authoritative PNG exported by draw.io."""
    dv = db.one("SELECT dv.*,d.process_id FROM diagram_versions dv JOIN diagrams d ON d.id=dv.diagram_id WHERE dv.id=?", (int(dvid),))
    if not dv:
        raise svc.NotFound("Not found")
    proc = db.one("SELECT * FROM processes WHERE id=?", (dv["process_id"],)) if dv["process_id"] else None
    svc.need(c.user, "edit", proc)
    old = db.one("SELECT role FROM assets WHERE id=?", (dv["preview_asset_id"],)) if dv["preview_asset_id"] else None
    if old and old["role"] != "preview-approx":
        return dict(replaced=False)
    import base64
    raw = base64.b64decode((c.json().get("png") or "").split(",", 1)[-1])
    if raw[:8] != b"\x89PNG\r\n\x1a\n" or len(raw) > 12 * 1024 * 1024:
        raise svc.Invalid("Preview must be a PNG under 12 MB.")
    with db.tx():
        aid = svc.store_asset(raw, "image/png", f"diagram_{dvid}.png", None, "preview")
        db.db().execute("UPDATE diagram_versions SET preview_asset_id=? WHERE id=?", (aid, dv["id"]))
        svc.set_preview_box(dv["id"], c.json().get("box"))
    return dict(replaced=True)


@route("GET", "/api/diagram-versions/(\\d+)/picture")
def r_dv_picture(c, dvid):
    """What documents show of this flow (export areas, or the flow without frame and legend)."""
    svc.need(c.user, "view_all")
    res = svc.diagram_pictures(int(dvid))
    return dict(kind=res["kind"], note=res["note"], pictures=[dict(n=i, label=p["label"]) for i, p in enumerate(res["pictures"])])


@route("GET", "/api/diagram-versions/(\\d+)/picture/(\\d+)")
def r_dv_picture_png(c, dvid, n):
    svc.need(c.user, "view_all")
    pics = svc.diagram_pictures(int(dvid))["pictures"]
    if int(n) >= len(pics):
        raise svc.NotFound("Not found")
    return pics[int(n)]["png"], "image/png", {"Content-Security-Policy": "sandbox"}, "private, no-cache"


@route("POST", "/api/diagrams/(\\d+)/lock")
def r_lock(c, did):
    return svc.acquire_lock(int(did), c.user)


@route("POST", "/api/diagrams/(\\d+)/unlock")
def r_unlock(c, did):
    svc.release_lock(int(did), c.user)


@route("POST", "/api/diagrams/(\\d+)/save")
def r_dsave(c, did):
    d = c.json()
    return svc.save_diagram(int(did), c.user, d.get("xml", ""), d.get("png"), d.get("base_ver"), d.get("note", ""), d.get("box"))


@route("PUT", "/api/diagram-versions/(\\d+)/nodes/([^/]+)")
def r_node_meta(c, dvid, nid):
    return dict(meta=svc.set_node_meta(int(dvid), unquote(nid), c.user, c.json()))


@route("GET", "/api/assets/(\\d+)")
def r_asset(c, aid):
    mime, data = svc.asset_bytes(int(aid))
    a = db.one("SELECT role,source_id FROM assets WHERE id=?", (int(aid),))
    if not svc.can(c.user, "view_all"):
        # viewers may only fetch assets that belong to published content
        if not db.one("SELECT 1 FROM diagram_versions dv JOIN process_versions pv ON pv.diagram_version_id=dv.id WHERE dv.preview_asset_id=? AND pv.status IN ('published','superseded')", (int(aid),)) \
           and not db.one("SELECT 1 FROM process_versions WHERE status IN ('published','superseded') AND content LIKE ?", (f'%/api/assets/{int(aid)}"%',)):
            raise svc.Forbidden("Asset not available.")
    return data, mime, {"Content-Security-Policy": "sandbox"}, "private, max-age=31536000, immutable", f'"a{int(aid)}"'      # an asset id never changes content


# ---- insight / reports
@route("GET", "/api/dashboard")
def r_dashboard(c):
    return queries.dashboard(c.user)


@route("GET", "/api/search")
def r_search(c):
    return dict(results=queries.search(c.user, c.arg("q", ""), c.arg("dept"), c.arg("status")))


@route("GET", "/api/map")
def r_map(c):
    return queries.process_map(c.user)


@route("GET", "/api/raci")
def r_raci(c):
    return dict(rows=queries.raci_report(c.user))


@route("GET", "/api/kpis")
def r_kpis(c):
    return dict(rows=queries.kpi_report(c.user))


@route("GET", "/api/escalation")
def r_esc(c):
    return dict(rows=queries.escalation_report(c.user))


@route("GET", "/api/approvals")
def r_approvals(c):
    svc.need(c.user, "view_all")
    return dict(rows=queries.approvals_queue(c.user))


@route("GET", "/api/changelog")
def r_changelog(c):
    svc.need(c.user, "view_all")
    return dict(rows=queries.change_log(c.user, c.arg("process")))


@route("GET", "/api/findings")
def r_findings(c):
    svc.need(c.user, "view_all")
    return dict(rows=queries.findings(c.arg("status"), c.arg("kind")))


@route("PUT", "/api/findings/(\\d+)")
def r_finding_upd(c, fid):
    d = c.json()
    queries.update_finding(c.user, int(fid), d.get("status"), d.get("decision", ""))


@route("GET", "/api/sources")
def r_sources(c):
    svc.need(c.user, "view_all")
    return dict(sources=queries.sources_register())


@route("GET", "/api/sources/(\\d+)/download")
def r_source_dl(c, sid):
    svc.need(c.user, "view_all")
    s = db.one("SELECT * FROM sources WHERE id=?", (int(sid),))
    if not s:
        raise svc.NotFound("Source not found")
    with open(s["stored_path"], "rb") as f:
        return file_resp(f.read(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document", s["filename"])


@route("POST", "/api/import")
def r_import(c):
    svc.need(c.user, "import")
    name = os.path.basename(unquote(c.h.headers.get("X-Filename", "upload.docx")))
    if not name.lower().endswith((".docx", ".drawio")):
        raise svc.Invalid("Only .docx and .drawio files can be imported.")
    if not c.raw:
        raise svc.Invalid("Empty upload.")
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, re.sub(r"[^A-Za-z0-9._ -]", "_", name))
        with open(p, "wb") as f:
            f.write(c.raw)
        return importer.import_paths([p], c.user["username"])


@route("GET", "/api/inbox")
def r_inbox(c):
    return dict(rows=svc.inbox(c.user))


@route("POST", "/api/ownership")
def r_ownership(c):
    d = c.json()
    items = d.get("items")
    if not items and d.get("dept"):
        items = [dict(process_id=r["process_id"], owner=d.get("owner"), reviewer=d.get("reviewer"), review_months=d.get("review_months"))
                 for r in db.q("SELECT p.process_id FROM processes p JOIN departments x ON x.id=p.department_id WHERE x.code=? AND p.kind<>'reference'", (d["dept"],))]
    if not isinstance(items, list) or not items:
        raise svc.Invalid("Nothing to assign.")
    return svc.assign_ownership(c.user, items[:2000], bool(d.get("only_empty")))


@route("POST", "/api/register-import")
def r_register_import(c):
    svc.need(c.user, "assign_owner")
    return queries.import_register(c.user, c.raw)


@route("POST", "/api/map/suggest-links")
def r_suggest(c):
    return svc.suggest_value_stream_links(c.user)


@route("POST", "/api/findings/bulk")
def r_findings_bulk(c):
    d = c.json()
    return queries.bulk_update_findings(c.user, d.get("ids") or [], d.get("status"), d.get("decision", ""))


@route("GET", "/api/register.xlsx")
def r_register(c):
    svc.need(c.user, "view_all")
    return file_resp(queries.register_xlsx(c.user), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "MEA_Master_Process_Register.xlsx")


# ---- Microsoft Teams / SharePoint
@route("GET", "/api/admin/teams")
def r_teams_info(c):
    svc.need(c.user, "admin")
    origins = config.embed_origins()
    return dict(embed_origins=origins, teams_allowed=all(o in origins for o in config.TEAMS_ORIGINS), teams_origins=config.TEAMS_ORIGINS)


@route("GET", "/api/admin/teams-package")
def r_teams_package(c):
    """The Teams app package for the address under which the tool is hosted (admin only)."""
    svc.need(c.user, "admin")
    from . import teams
    try:
        data = teams.build(c.arg("url", ""), name=c.arg("name", "MEA Process Hub")[:100] or "MEA Process Hub", developer=c.arg("developer", "")[:32] or svc.cfg("org_name", "dormakaba MEA"))
    except ValueError as e:
        raise svc.Invalid(str(e))
    svc.audit(c.user, "teams_package", "system", "teams", c.arg("url", "")[:200])
    return file_resp(data, "application/zip", "MEA_Process_Hub_Teams.zip")


# ---- drafts derived from the flows (RACI per process, work instruction per SAP task)
@route("GET", "/api/drafts")
def r_drafts_info(c):
    svc.need(c.user, "view_all")
    todo, no_steps = drafts.raci_candidates()
    return dict(raci_missing=len(todo), raci_no_steps=no_steps, sap_steps=len(drafts.sap_steps()), sap_steps_extended=len(drafts.sap_steps(True)),
                sap_drafts=db.one("SELECT count(*) n FROM processes WHERE gen_key LIKE 'SAPWI:%'")["n"], can=svc.can(c.user, "generate_drafts"))


@route("POST", "/api/drafts/raci")
def r_drafts_raci(c):
    d = c.json()
    if d.get("process_id"):
        return dict(rows=drafts.generate_raci(c.user, d["process_id"], bool(d.get("force"))))
    return drafts.generate_all_raci(c.user)


@route("POST", "/api/drafts/sap")
def r_drafts_sap(c):
    return drafts.generate_sap_instructions(c.user, bool(c.json().get("extended")))


# ---- exports
@route("POST", "/api/exports")
def r_export(c):
    d = c.json()
    e = exporter.run_export(c.user, d.get("scope", "handbook"), d.get("fmt", "docx"), d.get("ids"), d.get("dept"), bool(d.get("include_unapproved", True)), d.get("version_id"),
                            "sheet" if d.get("flow_picture") == "sheet" else "flow")
    return dict(export=e)


@route("GET", "/api/exports")
def r_exports(c):
    rows = db.q("SELECT id,ts,username,scope,fmt,status,filename,sha256,size,snapshot_hash,error FROM exports ORDER BY id DESC LIMIT 100")
    if c.user["role"] not in ("admin", "controller"):
        rows = [r for r in rows if r["username"] == c.user["username"]]
    return dict(rows=rows)


@route("GET", "/api/exports/(\\d+)/download")
def r_export_dl(c, eid):
    e, data = exporter.export_file(c.user, int(eid))
    return file_resp(data, exporter.FORMATS[e["fmt"]][1], e["filename"])


# ---- administration
@route("GET", "/api/users")
def r_users(c):
    svc.need(c.user, "admin")
    return dict(users=queries.users_list())


@route("POST", "/api/users")
def r_user_new(c):
    svc.need(c.user, "admin")
    d = c.json()
    with db.tx():
        uid = svc.create_user(d.get("username"), d.get("display_name"), d.get("password"), d.get("role"), d.get("department_id") or None, must_change=True)
        svc.audit(c.user, "user_created", "user", uid, d.get("username"))
    return dict(id=uid)


@route("PUT", "/api/users/(\\d+)")
def r_user_upd(c, uid):
    svc.need(c.user, "admin")
    d = c.json()
    with db.tx():
        if "role" in d:
            if d["role"] not in svc.ROLES:
                raise svc.Invalid("Unknown role")
            db.db().execute("UPDATE users SET role=? WHERE id=?", (d["role"], int(uid)))
        if "active" in d:
            if int(uid) == c.user["id"] and not d["active"]:
                raise svc.Invalid("You cannot deactivate yourself.")
            db.db().execute("UPDATE users SET active=? WHERE id=?", (1 if d["active"] else 0, int(uid)))
            if not d["active"]:
                db.db().execute("DELETE FROM sessions WHERE user_id=?", (int(uid),))
        if "department_id" in d:
            db.db().execute("UPDATE users SET department_id=? WHERE id=?", (d["department_id"] or None, int(uid)))
        if d.get("password"):
            if len(d["password"]) < 8:
                raise svc.Invalid("Password must be at least 8 characters.")
            from .security import hash_password
            db.db().execute("UPDATE users SET pw_hash=?, must_change=1 WHERE id=?", (hash_password(d["password"]), int(uid)))
        svc.audit(c.user, "user_updated", "user", uid, json.dumps({k: v for k, v in d.items() if k != "password"}))


@route("PUT", "/api/settings")
def r_settings(c):
    svc.need(c.user, "admin")
    d = c.json()
    with db.tx():
        for k in ("org_name", "allow_self_approval", "default_review_months", "export_footer", "classification", "region_label"):
            if k in d:
                svc.set_cfg(k, str(d[k])[:300])
        svc.audit(c.user, "settings_changed", "config", None, json.dumps(d)[:500])


@route("GET", "/api/settings")
def r_settings_get(c):
    svc.need(c.user, "admin")
    return {k: svc.cfg(k) for k in ("org_name", "allow_self_approval", "default_review_months", "export_footer", "classification", "region_label")}


@route("GET", "/api/audit")
def r_audit(c):
    svc.need(c.user, "admin")
    return dict(rows=db.q("SELECT * FROM audit ORDER BY id DESC LIMIT 500"))


@route("POST", "/api/backup")
def r_backup(c):
    svc.need(c.user, "admin")
    path = queries.make_backup()
    svc.audit(c.user, "backup", "system", None, path)
    with open(path, "rb") as f:
        return file_resp(f.read(), "application/zip", os.path.basename(path))


@route("POST", "/api/restore")
def r_restore_all(c):
    svc.need(c.user, "admin")
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "restore.zip")
        with open(p, "wb") as f:
            f.write(c.raw)
        queries.restore_backup(p)
    db.init()
    db.db().execute("DELETE FROM sessions")          # a restore must never resurrect old logins
    return dict(ok=True, message="Restore complete. Please log in again.")


# ====================================================================== run
def make_server(host="127.0.0.1", port=8765):
    db.init()
    srv = ThreadingHTTPServer((host, port), Handler)
    srv.daemon_threads = True
    srv.allow_any_host = host not in ("127.0.0.1", "localhost", "::1")
    return srv
