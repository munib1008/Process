"""Business logic: users/permissions, processes, versions & approval workflow, diagrams, search, reports."""
import base64
import datetime as dt
import difflib
import hashlib
import json
import os
import re
import secrets
import sqlite3
import zipfile

from . import config, db, drawio
from .db import jloads, one, q, tx
from .security import hash_password, new_token, sanitize_html, strip_tags, verify_password

DEPARTMENTS = [
    ("E2E", "Supply Chain E2E (Enterprise)"), ("PMM", "Product Marketing & Management"), ("SAL", "Sales & Sales Support"),
    ("MPL", "Material Planning & OPEX"), ("PRC", "Procurement"), ("PRD", "Production & Engineering"),
    ("LOG", "Logistics & Warehouse"), ("PRJ", "Project Management"), ("FIN", "Finance & Accounts"),
    ("SVC", "Service & Installation"), ("MDM", "Master Data Management"), ("GOV", "Approval & Governance")]
ROLES = ["admin", "controller", "dept_owner", "editor", "reviewer", "approver", "viewer"]
STATUS_LABEL = {"imported": "Imported / Unverified", "draft": "Draft", "under_review": "Under Review",
                "changes_requested": "Changes Requested", "pending_approval": "Pending Approval", "approved": "Approved",
                "published": "Published", "superseded": "Superseded", "archived": "Archived"}
OPEN_STATES = ("imported", "draft", "under_review", "changes_requested", "pending_approval", "approved")
EDITABLE = ("imported", "draft", "changes_requested")
KINDS = ["e2e", "department", "sop", "approval", "work_instruction", "form", "reference", "future_state"]


class Forbidden(Exception):
    pass


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


class Invalid(ValueError):
    pass


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def audit(user, action, entity=None, entity_id=None, detail=""):
    db.db().execute("INSERT INTO audit(ts,username,action,entity,entity_id,detail) VALUES(?,?,?,?,?,?)",
                    (now(), user if isinstance(user, str) else (user or {}).get("username"), action, entity,
                     str(entity_id) if entity_id is not None else None, detail[:2000]))


def cfg(key, default=None):
    r = one("SELECT value FROM config WHERE key=?", (key,))
    return r["value"] if r else default


def set_cfg(key, value):
    db.db().execute("INSERT INTO config(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))


# ------------------------------------------------------------------ bootstrap
def seed_departments():
    c = db.db()
    for i, (code, name) in enumerate(DEPARTMENTS):
        c.execute("INSERT OR IGNORE INTO departments(code,name,sort) VALUES(?,?,?)", (code, name, i))
    for k, v in (("org_name", "dormakaba MEA"), ("doc_ref_format", "MEA-PH-{n}"), ("allow_self_approval", "0"),
                 ("default_review_months", "12"), ("export_footer", "Controlled document – printed copies are uncontrolled")):
        c.execute("INSERT OR IGNORE INTO config(key,value) VALUES(?,?)", (k, v))


def bootstrap(demo_users=False):
    """First-run setup: departments + admin with a random one-time password (written to data/)."""
    db.init()
    seed_departments()
    msg = None
    if not one("SELECT 1 FROM users LIMIT 1"):
        pw = secrets.token_urlsafe(9)
        create_user("admin", "Administrator", pw, "admin", None, must_change=True)
        path = os.path.join(config.DATA_DIR, "FIRST_RUN_ADMIN_PASSWORD.txt")
        with open(path, "w") as f:
            f.write(f"username: admin\npassword: {pw}\n(You are asked to change it after first login. Delete this file afterwards.)\n")
        msg = (pw, path)
    if demo_users:
        for r in ROLES:
            if r != "admin" and not one("SELECT 1 FROM users WHERE username=?", (f"demo_{r}",)):
                create_user(f"demo_{r}", f"Demo {r.replace('_', ' ').title()}", "ChangeMe!123", r, None)
    return msg


# ------------------------------------------------------------------ users & sessions
def create_user(username, display_name, password, role, department_id=None, must_change=False):
    username = (username or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9_.@-]{3,64}", username):
        raise Invalid("Username must be 3-64 characters (letters, digits, . _ @ -).")
    if role not in ROLES:
        raise Invalid("Unknown role.")
    if len(password or "") < 8:
        raise Invalid("Password must be at least 8 characters.")
    if one("SELECT 1 FROM users WHERE username=?", (username,)):
        raise Invalid("Username already exists.")
    cur = db.db().execute("INSERT INTO users(username,display_name,pw_hash,role,department_id,must_change,created_at) VALUES(?,?,?,?,?,?,?)",
                          (username, display_name or username, hash_password(password), role, department_id, int(must_change), now()))
    return cur.lastrowid


def login(username, password):
    u = one("SELECT * FROM users WHERE username=? AND active=1", ((username or "").strip().lower(),))
    if not u or not verify_password(password or "", u["pw_hash"]):
        audit(username, "login_failed")
        return None
    tok, csrf = new_token(), new_token()
    exp = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=config.SESSION_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    db.db().execute("INSERT INTO sessions(token,csrf,user_id,created_at,expires_at) VALUES(?,?,?,?,?)", (tok, csrf, u["id"], now(), exp))
    audit(u["username"], "login")
    return tok, csrf, public_user(u)


def public_user(u):
    return dict(id=u["id"], username=u["username"], display_name=u["display_name"], role=u["role"],
                department_id=u["department_id"], must_change=bool(u["must_change"]))


def session_user(token):
    if not token:
        return None
    s = one("SELECT s.*,u.username,u.display_name,u.role,u.department_id,u.must_change,u.active FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=?", (token,))
    if not s or not s["active"] or s["expires_at"] < now():
        return None
    return dict(id=s["user_id"], username=s["username"], display_name=s["display_name"], role=s["role"],
                department_id=s["department_id"], must_change=bool(s["must_change"]), csrf=s["csrf"])


def logout(token):
    db.db().execute("DELETE FROM sessions WHERE token=?", (token,))


def change_password(user, old, new):
    u = one("SELECT * FROM users WHERE id=?", (user["id"],))
    if not verify_password(old or "", u["pw_hash"]):
        raise Invalid("Current password is incorrect.")
    if len(new or "") < 8:
        raise Invalid("New password must be at least 8 characters.")
    db.db().execute("UPDATE users SET pw_hash=?, must_change=0 WHERE id=?", (hash_password(new), u["id"]))
    audit(user, "password_changed", "user", u["id"])


# ------------------------------------------------------------------ permissions
def can(user, action, proc=None) -> bool:
    if not user:
        return False
    r = user["role"]
    if r == "admin":
        return True
    in_scope = proc is None or user.get("department_id") in (None, proc.get("department_id"))
    table = {
        "view_all": {"controller", "dept_owner", "editor", "reviewer", "approver"},
        "edit": {"controller", "dept_owner", "editor"},
        "review": {"controller", "reviewer", "dept_owner"},
        "approve": {"approver"},
        "publish": {"controller"},
        "accept_import": {"controller"},
        "manage_findings": {"controller", "dept_owner"},
        "manage_relationships": {"controller", "dept_owner", "editor"},
        "assign_owner": {"controller", "dept_owner"},
        "comment": {"controller", "dept_owner", "editor", "reviewer", "approver"},
        "import": {"controller"},
        "export_draft": {"controller", "dept_owner", "editor", "reviewer", "approver"},
        "admin": set(),
    }
    if r not in table.get(action, set()):
        return False
    if action in ("edit", "review", "manage_findings", "assign_owner") and r in ("dept_owner", "editor"):
        return in_scope
    return True


def need(user, action, proc=None):
    if not user:
        raise Forbidden("Login required.")
    if not can(user, action, proc):
        raise Forbidden(f"Your role ({user['role']}) is not allowed to perform: {action.replace('_', ' ')}.")


# ------------------------------------------------------------------ assets
def store_asset(data: bytes, mime: str, filename: str, source_id=None, role="diagram", w=None, h=None) -> int:
    sha = hashlib.sha256(data).hexdigest()
    ext = {"image/png": ".png", "image/jpeg": ".jpg", "image/svg+xml": ".svg", "image/gif": ".gif"}.get(mime, ".bin")
    path = os.path.join(config.ASSET_DIR, sha + ext)
    if not os.path.exists(path):
        with open(path, "wb") as f:
            f.write(data)
    cur = db.db().execute("INSERT INTO assets(sha256,mime,filename,size,path,source_id,role,width,height) VALUES(?,?,?,?,?,?,?,?,?)",
                          (sha, mime, filename, len(data), path, source_id, role, w, h))
    return cur.lastrowid


def asset_bytes(aid: int):
    a = one("SELECT * FROM assets WHERE id=?", (aid,))
    if not a:
        raise NotFound("Asset not found")
    with open(a["path"], "rb") as f:
        return a["mime"], f.read()


# ------------------------------------------------------------------ content helpers
EMPTY = dict(objective="", scope="", trigger="", inputs="", outputs="", responsible=[], activities=[], raci=[], sap=[], kpis=[],
             escalation=[], risks="", evidence="", forms="", sections=[], notes="")
STR_FIELDS = ["objective", "scope", "trigger", "inputs", "outputs", "risks", "evidence", "forms", "notes"]
TABLE_FIELDS = {"activities": ["no", "activity", "role", "sap", "output"], "raci": ["activity", "R", "A", "C", "I"],
                "sap": ["transaction", "purpose"], "kpis": ["name", "definition", "target"], "escalation": ["stage", "to", "time", "action", "sla"]}


def clean_content(c: dict) -> dict:
    """Validate/normalise a content dict from the client. Rich-text is sanitised server-side."""
    out = json.loads(json.dumps(EMPTY))
    for k in STR_FIELDS:
        v = c.get(k, "")
        if not isinstance(v, str) or len(v) > 200000:
            raise Invalid(f"Field {k} is invalid or too long.")
        out[k] = v.strip()
    resp = c.get("responsible", [])
    if not isinstance(resp, list):
        raise Invalid("responsible must be a list.")
    out["responsible"] = [str(x).strip()[:120] for x in resp if str(x).strip()][:50]
    for k, cols in TABLE_FIELDS.items():
        rows = c.get(k, [])
        if not isinstance(rows, list) or len(rows) > 500:
            raise Invalid(f"Table {k} is invalid.")
        for r in rows:
            if not isinstance(r, dict):
                raise Invalid(f"Table {k} row is invalid.")
            row = {col: str(r.get(col, ""))[:2000] for col in cols}
            if any(v.strip() for v in row.values()):
                out[k].append(row)
    secs = c.get("sections", [])
    if not isinstance(secs, list) or len(secs) > 200:
        raise Invalid("sections invalid.")
    for s in secs:
        out["sections"].append(dict(title=str(s.get("title", ""))[:200], html=sanitize_html(str(s.get("html", "")))))
    return out


def content_text(content) -> str:
    c = jloads(content, {}) if isinstance(content, str) else (content or {})
    parts = []
    for k in STR_FIELDS:
        parts.append(c.get(k, ""))
    parts += c.get("responsible", [])
    for k in TABLE_FIELDS:
        for r in c.get(k, []):
            parts.append(" ".join(r.values()))
    for s in c.get("sections", []):
        parts.append(s.get("title", ""))
        parts.append(strip_tags(s.get("html", "")))
    return " ".join(p for p in parts if p)


def parse_ver(v: str):
    m = re.fullmatch(r"(\d+)\.(\d+)", v or "")
    return (int(m.group(1)), int(m.group(2))) if m else (0, 1)


def latest_version(pid: int):
    v = one("SELECT * FROM process_versions WHERE process_id=? ORDER BY major DESC, minor DESC, id DESC LIMIT 1", (pid,))
    if v:
        v["content"] = jloads(v["content"], {})
    return v


def published_version(pid: int):
    v = one("SELECT * FROM process_versions WHERE process_id=? AND status='published' ORDER BY major DESC, minor DESC LIMIT 1", (pid,))
    if v:
        v["content"] = jloads(v["content"], {})
    return v


def open_version(pid: int):
    v = one("SELECT * FROM process_versions WHERE process_id=? AND status IN ('imported','draft','under_review','changes_requested','pending_approval','approved') "
            "ORDER BY id DESC LIMIT 1", (pid,))
    if v:
        v["content"] = jloads(v["content"], {})
    return v


def get_version(vid: int):
    v = one("SELECT * FROM process_versions WHERE id=?", (vid,))
    if not v:
        raise NotFound("Version not found")
    v["content"] = jloads(v["content"], {})
    return v


def get_process(pid_text: str):
    p = one("SELECT p.*,d.name AS department,d.code AS dept_code FROM processes p LEFT JOIN departments d ON d.id=p.department_id WHERE p.process_id=?", (pid_text,))
    if not p:
        raise NotFound(f"Process {pid_text} not found")
    return p


# ------------------------------------------------------------------ process creation
def create_process_record(process_id, chart_id, name, dept_code, kind, content, status, origin, user, countries="", category="", owner=""):
    c = db.db()
    dept = one("SELECT id FROM departments WHERE code=?", (dept_code,))
    uname = user if isinstance(user, str) else user["username"]
    cur = c.execute("INSERT INTO processes(process_id,chart_id,name,department_id,kind,category,countries,owner,origin,created_at,created_by,validation) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (process_id, chart_id, name, dept["id"] if dept else None, kind, category, countries, owner, origin, now(), uname,
                     "unverified" if status == "imported" else "authored"))
    pid = cur.lastrowid
    c.execute("INSERT INTO process_versions(process_id,version,major,minor,status,content,author,created_at,updated_at,change_summary) VALUES(?,?,?,?,?,?,?,?,?,?)",
              (pid, "0.1", 0, 1, status, json.dumps(content), uname, now(), now(),
               "Initial import from source document" if origin == "imported" else "Initial draft"))
    c.execute("UPDATE processes SET sort_order=? WHERE id=?", (pid, pid))
    audit(uname, "process_created", "process", process_id, f"{name} ({origin})")
    return dict(id=pid, process_id=process_id)


def add_finding(kind, severity, source_id, process_id, title, detail):
    db.db().execute("INSERT INTO findings(kind,severity,source_id,process_id,title,detail,created_at) VALUES(?,?,?,?,?,?,?)",
                    (kind, severity, source_id, process_id, title, detail, now()))


def new_process(user, data: dict) -> dict:
    name = (data.get("name") or "").strip()
    if not name:
        raise Invalid("Process name is required.")
    dept = one("SELECT * FROM departments WHERE id=? OR code=?", (data.get("department_id"), data.get("department")))
    if not dept:
        raise Invalid("Department is required.")
    kind = data.get("kind", "sop")
    if kind not in KINDS:
        raise Invalid("Unknown process type.")
    proc_stub = dict(department_id=dept["id"])
    need(user, "edit", proc_stub)
    pid_text = (data.get("process_id") or "").strip().upper()
    if pid_text:
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9._-]{2,40}", pid_text):
            raise Invalid("Process ID may contain A-Z, 0-9, '.', '_', '-' (3-41 characters).")
        if one("SELECT 1 FROM processes WHERE process_id=?", (pid_text,)):
            raise Invalid(f"Process ID {pid_text} already exists.")
    else:
        n = 1
        while one("SELECT 1 FROM processes WHERE process_id=?", (f"{dept['code']}-N-{n:03d}",)):
            n += 1
        pid_text = f"{dept['code']}-N-{n:03d}"
    content = json.loads(json.dumps(EMPTY))
    copy_from = data.get("copy_from")
    if copy_from:
        src = get_process(copy_from)
        v = latest_version(src["id"])
        content = v["content"]
        content["notes"] = (content.get("notes", "") + f"\nCopied from {copy_from}.").strip()
    else:
        for k in ("objective", "scope", "trigger", "inputs", "outputs"):
            content[k] = str(data.get(k, ""))[:20000]
    pr = create_process_record(pid_text, None, name, dept["code"], kind, content, "draft", "authored", user,
                               countries=data.get("countries", ""), category=data.get("category", ""), owner=data.get("owner", ""))
    if copy_from:
        sv = latest_version(get_process(copy_from)["id"])
        if sv and sv.get("diagram_version_id"):
            dv = one("SELECT dv.*,d.title FROM diagram_versions dv JOIN diagrams d ON d.id=dv.diagram_id WHERE dv.id=?", (sv["diagram_version_id"],))
            create_diagram(pr["id"], pid_text, name, dv["xml"], "copied", dv["preview_asset_id"], f"Copied from {copy_from}", user)
    elif data.get("template"):
        create_diagram(pr["id"], pid_text, name, drawio.template_xml(data["template"], name), "template", None, f"Template {data['template']}", user)
    reindex(pr["id"])
    return get_process(pid_text)


# ------------------------------------------------------------------ versions & workflow
def ensure_draft(proc: dict, user) -> dict:
    """Return the editable open version, creating a new draft from the current baseline when necessary."""
    need(user, "edit", proc)
    ov = open_version(proc["id"])
    if ov:
        if ov["status"] in EDITABLE:
            if ov["status"] == "imported":
                db.db().execute("UPDATE process_versions SET status='draft', updated_at=? WHERE id=?", (now(), ov["id"]))
                ov["status"] = "draft"
                audit(user, "import_edited_to_draft", "process", proc["process_id"])
            return ov
        raise Conflict(f"Version {ov['version']} is {STATUS_LABEL[ov['status']]}. Withdraw it (or ask the reviewer to return it) before editing.")
    base = latest_version(proc["id"])
    ma, mi = base["major"], base["minor"] + 1
    cur = db.db().execute("INSERT INTO process_versions(process_id,version,major,minor,status,content,diagram_version_id,author,basis_version_id,created_at,updated_at) "
                          "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                          (proc["id"], f"{ma}.{mi}", ma, mi, "draft", json.dumps(base["content"]), base["diagram_version_id"], user["username"], base["id"], now(), now()))
    audit(user, "draft_created", "process", proc["process_id"], f"v{ma}.{mi} from v{base['version']}")
    return get_version(cur.lastrowid)


def save_draft(pid_text, user, data: dict):
    proc = get_process(pid_text)
    with tx():
        v = ensure_draft(proc, user)
        base_updated = data.get("base_updated_at")
        if base_updated and v["updated_at"] != base_updated and data.get("autosave_check", True):
            raise Conflict("This draft was changed by someone else since you opened it. Reload to see the latest.")
        content = clean_content(data.get("content", v["content"]))
        meta = data.get("meta", {})
        sets, args = [], []
        for k in ("name", "owner", "reviewer", "countries", "category"):
            if k in meta:
                val = str(meta[k]).strip()[:300]
                if k == "name" and not val:
                    raise Invalid("Name cannot be empty.")
                sets.append(f"{k}=?")
                args.append(val)
        if "department_id" in meta:
            if not one("SELECT 1 FROM departments WHERE id=?", (meta["department_id"],)):
                raise Invalid("Unknown department.")
            sets.append("department_id=?")
            args.append(meta["department_id"])
        if "kind" in meta:
            if meta["kind"] not in KINDS:
                raise Invalid("Unknown type.")
            sets.append("kind=?")
            args.append(meta["kind"])
        if "review_months" in meta:
            rm = meta["review_months"]
            sets.append("review_months=?")
            args.append(int(rm) if str(rm).strip().isdigit() else None)
        if sets:
            db.db().execute(f"UPDATE processes SET {','.join(sets)} WHERE id=?", (*args, proc["id"]))
        ts = now()
        db.db().execute("UPDATE process_versions SET content=?, updated_at=?, change_summary=COALESCE(NULLIF(?, ''), change_summary) WHERE id=?",
                        (json.dumps(content), ts, str(data.get("change_summary", ""))[:1000], v["id"]))
        reindex(proc["id"])
        audit(user, "draft_saved", "process", pid_text, f"v{v['version']}")
    return get_version(v["id"])


def _log(user, pid_text, action, detail=""):
    audit(user, action, "process", pid_text, detail)


def submit_for_review(pid_text, user, change_summary="", bump="minor"):
    proc = get_process(pid_text)
    need(user, "edit", proc)
    with tx():
        v = open_version(proc["id"])
        if not v or v["status"] not in EDITABLE:
            raise Conflict("There is no editable draft to submit.")
        summary = (change_summary or v["change_summary"] or "").strip()
        if not summary:
            raise Invalid("Please provide a change summary.")
        ma, mi = v["major"], v["minor"]
        if bump == "major" and mi != 0:
            pv = published_version(proc["id"])
            ma, mi = ((pv["major"] if pv else v["major"]) + 1, 0)
        db.db().execute("UPDATE process_versions SET status='under_review', submitted_at=?, change_summary=?, major=?, minor=?, version=?, updated_at=?, review_note='' WHERE id=?",
                        (now(), summary, ma, mi, f"{ma}.{mi}", now(), v["id"]))
        _log(user, pid_text, "submitted_for_review", f"v{ma}.{mi}: {summary}")
    return get_version(v["id"])


def withdraw(pid_text, user):
    proc = get_process(pid_text)
    v = open_version(proc["id"])
    if not v or v["status"] not in ("under_review", "pending_approval", "approved"):
        raise Conflict("Nothing to withdraw.")
    if not (v["author"] == user["username"] or can(user, "review", proc) or user["role"] == "admin"):
        raise Forbidden("Only the author or a reviewer can withdraw.")
    with tx():
        db.db().execute("UPDATE process_versions SET status='draft', updated_at=? WHERE id=?", (now(), v["id"]))
        _log(user, pid_text, "withdrawn", f"v{v['version']}")
    return get_version(v["id"])


def _sod(user, v, what):
    if v["author"] == user["username"] and cfg("allow_self_approval", "0") != "1":
        raise Forbidden(f"Separation of duties: the author cannot {what} their own revision "
                        "(an administrator can enable self-approval in Administration for single-user deployments).")


def review_decision(pid_text, user, decision, note=""):
    proc = get_process(pid_text)
    need(user, "review", proc)
    with tx():
        v = open_version(proc["id"])
        if not v or v["status"] != "under_review":
            raise Conflict("No revision is waiting for review.")
        _sod(user, v, "review")
        if decision == "approve_review":
            new = "pending_approval"
        elif decision == "request_changes":
            if not note.strip():
                raise Invalid("A comment is required when requesting changes.")
            new = "changes_requested"
        else:
            raise Invalid("Unknown decision.")
        db.db().execute("UPDATE process_versions SET status=?, reviewed_by=?, reviewed_at=?, review_note=?, updated_at=? WHERE id=?",
                        (new, user["username"], now(), note[:2000], now(), v["id"]))
        if note.strip():
            db.db().execute("INSERT INTO comments(process_id,version_id,author,body,kind,created_at) VALUES(?,?,?,?,?,?)",
                            (proc["id"], v["id"], user["username"], note[:4000], "review", now()))
        _log(user, pid_text, "review_" + decision, f"v{v['version']} {note[:200]}")
    return get_version(v["id"])


def approval_decision(pid_text, user, decision, note=""):
    proc = get_process(pid_text)
    need(user, "approve", proc)
    with tx():
        v = open_version(proc["id"])
        if not v or v["status"] != "pending_approval":
            raise Conflict("No revision is waiting for approval.")
        _sod(user, v, "approve")
        if v["reviewed_by"] == user["username"] and cfg("allow_self_approval", "0") != "1":
            raise Forbidden("Separation of duties: the reviewer cannot also be the approver.")
        if decision == "approve":
            db.db().execute("UPDATE process_versions SET status='approved', approved_by=?, approved_at=?, updated_at=? WHERE id=?",
                            (user["username"], now(), now(), v["id"]))
        elif decision == "reject":
            if not note.strip():
                raise Invalid("A comment is required when rejecting.")
            db.db().execute("UPDATE process_versions SET status='changes_requested', review_note=?, updated_at=? WHERE id=?", (note[:2000], now(), v["id"]))
            db.db().execute("INSERT INTO comments(process_id,version_id,author,body,kind,created_at) VALUES(?,?,?,?,?,?)",
                            (proc["id"], v["id"], user["username"], note[:4000], "approval", now()))
        else:
            raise Invalid("Unknown decision.")
        _log(user, pid_text, "approval_" + decision, f"v{v['version']} {note[:200]}")
        if decision == "approve" and user["role"] == "admin":
            publish_locked(proc, v, user)
    return get_version(v["id"])


def publish_locked(proc, v, user):
    ts = now()
    c = db.db()
    c.execute("UPDATE process_versions SET status='superseded', updated_at=? WHERE process_id=? AND status='published'", (ts, proc["id"]))
    major, minor = v["major"], v["minor"]
    if major == 0:
        major, minor = 1, 0
    c.execute("UPDATE process_versions SET status='published', published_at=?, version=?, major=?, minor=?, updated_at=? WHERE id=?",
              (ts, f"{major}.{minor}", major, minor, ts, v["id"]))
    months = proc.get("review_months") or int(cfg("default_review_months", "12"))
    nxt = (dt.date.today() + dt.timedelta(days=30 * months)).isoformat()
    c.execute("UPDATE processes SET last_review=?, next_review=?, review_months=?, validation=? WHERE id=?",
              (dt.date.today().isoformat(), nxt, months, "approved", proc["id"]))
    reindex(proc["id"])
    _log(user, proc["process_id"], "published", f"v{major}.{minor}")


def publish(pid_text, user):
    proc = get_process(pid_text)
    need(user, "publish", proc)
    with tx():
        v = open_version(proc["id"])
        if not v or v["status"] != "approved":
            raise Conflict("Only an approved revision can be published.")
        publish_locked(proc, v, user)
    return published_version(proc["id"])


def accept_import(pid_text, user, note=""):
    proc = get_process(pid_text)
    need(user, "accept_import", proc)
    with tx():
        v = open_version(proc["id"])
        if not v or v["status"] != "imported":
            raise Conflict("Process is not in Imported / Unverified state.")
        db.db().execute("UPDATE process_versions SET status='draft', updated_at=?, change_summary=? WHERE id=?", (now(), "Import accepted by controller. " + note, v["id"]))
        db.db().execute("UPDATE processes SET validation='accepted' WHERE id=?", (proc["id"],))
        _log(user, pid_text, "import_accepted", note)
    return get_version(v["id"])


def restore_version(pid_text, user, version_id, summary=""):
    """Rollback = a NEW controlled draft carrying old content; history is never rewritten."""
    proc = get_process(pid_text)
    need(user, "edit", proc)
    old = get_version(version_id)
    if old["process_id"] != proc["id"]:
        raise Invalid("Version belongs to a different process.")
    with tx():
        if open_version(proc["id"]):
            raise Conflict("Finish or withdraw the open revision first.")
        base = latest_version(proc["id"])
        ma, mi = base["major"], base["minor"] + 1
        cur = db.db().execute("INSERT INTO process_versions(process_id,version,major,minor,status,content,diagram_version_id,author,basis_version_id,created_at,updated_at,change_summary) "
                              "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                              (proc["id"], f"{ma}.{mi}", ma, mi, "draft", json.dumps(old["content"]), old["diagram_version_id"], user["username"], old["id"], now(), now(),
                               summary or f"Restore content of v{old['version']} (controlled rollback)"))
        _log(user, pid_text, "rollback_draft", f"v{ma}.{mi} restores v{old['version']}")
        reindex(proc["id"])
    return get_version(cur.lastrowid)


# ------------------------------------------------------------------ diff
def _flat(content):
    lines = []
    for k in STR_FIELDS:
        if content.get(k):
            lines += [f"{k}: {l}" for l in content[k].splitlines() if l.strip()]
    if content.get("responsible"):
        lines.append("responsible: " + ", ".join(content["responsible"]))
    for k in TABLE_FIELDS:
        for r in content.get(k, []):
            lines.append(f"{k}: " + " | ".join(r.values()))
    for s in content.get("sections", []):
        lines.append(f"[section] {s['title']}")
        lines += [l for l in strip_tags(s["html"]).splitlines() if l.strip()]
    return lines


def compare_versions(a_id, b_id):
    a, b = get_version(a_id), get_version(b_id)
    fa, fb = _flat(a["content"]), _flat(b["content"])
    rows = []
    for l in difflib.unified_diff(fa, fb, lineterm="", n=0):
        if l.startswith(("---", "+++", "@@")):
            continue
        rows.append(dict(op="add" if l[0] == "+" else "del", text=l[1:]))
    dva, dvb = a.get("diagram_version_id"), b.get("diagram_version_id")
    diagram = None
    if dva != dvb:
        diagram = dict(before=dva, after=dvb)
    return dict(a=dict(id=a["id"], version=a["version"], status=a["status"]), b=dict(id=b["id"], version=b["version"], status=b["status"]),
                changes=rows, diagram=diagram, identical=not rows and not diagram)


# ------------------------------------------------------------------ diagrams
def create_diagram(process_row_id, process_text, title, xml, origin, preview_asset_id, note, user, validation="ok", kind="process"):
    uname = user if isinstance(user, str) else user["username"]
    xml = drawio.normalize(xml)
    c = db.db()
    base = f"DG-{process_text}" if process_row_id else f"DG-LIB-{secrets.token_hex(3).upper()}"
    code, n = base, 1
    while one("SELECT 1 FROM diagrams WHERE code=?", (code,)):
        n += 1
        code = f"{base}-{n}"
    cur = c.execute("INSERT INTO diagrams(code,process_id,title,kind,created_at) VALUES(?,?,?,?,?)", (code, process_row_id, title, kind, now()))
    did = cur.lastrowid
    dv = _add_dv(did, xml, origin, preview_asset_id, note, uname, validation)
    if process_row_id:
        v = open_version(process_row_id)           # never touch a published/superseded version
        if v:
            c.execute("UPDATE process_versions SET diagram_version_id=? WHERE id=?", (dv, v["id"]))
    return did, dv


def _add_dv(did, xml, origin, preview_asset_id, note, uname, validation="ok"):
    c = db.db()
    last = one("SELECT COALESCE(MAX(ver_no),0) m FROM diagram_versions WHERE diagram_id=?", (did,))["m"]
    sha = hashlib.sha256(xml.encode()).hexdigest()
    cur = c.execute("INSERT INTO diagram_versions(diagram_id,ver_no,xml,sha256,preview_asset_id,origin,validation,note,author,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (did, last + 1, xml, sha, preview_asset_id, origin, validation, note, uname, now()))
    dvid = cur.lastrowid
    prev = one("SELECT id FROM diagram_versions WHERE diagram_id=? AND ver_no=?", (did, last)) if last else None
    old_meta = {r["node_id"]: r["meta"] for r in q("SELECT node_id,meta FROM diagram_nodes WHERE diagram_version_id=?", (prev["id"],))} if prev else {}
    for nid, label in drawio.nodes(xml):
        c.execute("INSERT OR IGNORE INTO diagram_nodes(diagram_version_id,node_id,label,meta) VALUES(?,?,?,?)", (dvid, nid, label, old_meta.get(nid, "{}")))
    return dvid


def diagram_info(did):
    d = one("SELECT * FROM diagrams WHERE id=?", (did,))
    if not d:
        raise NotFound("Diagram not found")
    return d


def acquire_lock(did, user):
    d = diagram_info(did)
    proc = one("SELECT * FROM processes WHERE id=?", (d["process_id"],)) if d["process_id"] else None
    need(user, "edit", proc)
    with tx():
        d = diagram_info(did)
        exp = d["lock_expires"]
        if d["lock_user"] and d["lock_user"] != user["username"] and exp and exp > now():
            raise Conflict(f"Diagram is being edited by {d['lock_user']} (lease expires {exp}).")
        new_exp = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=config.LOCK_MINUTES)).strftime("%Y-%m-%dT%H:%M:%SZ")
        db.db().execute("UPDATE diagrams SET lock_user=?, lock_expires=? WHERE id=?", (user["username"], new_exp, did))
    latest = one("SELECT ver_no FROM diagram_versions WHERE diagram_id=? ORDER BY ver_no DESC LIMIT 1", (did,))
    return dict(lock_expires=new_exp, latest_ver=latest["ver_no"])


def release_lock(did, user):
    db.db().execute("UPDATE diagrams SET lock_user=NULL, lock_expires=NULL WHERE id=? AND lock_user=?", (did, user["username"]))


def save_diagram(did, user, xml, png_b64, base_ver, note=""):
    d = diagram_info(did)
    proc = one("SELECT * FROM processes WHERE id=?", (d["process_id"],)) if d["process_id"] else None
    need(user, "edit", proc)
    xml = drawio.normalize(xml)
    sha = hashlib.sha256(xml.encode()).hexdigest()
    with tx():
        d = diagram_info(did)
        if d["lock_user"] and d["lock_user"] != user["username"] and d["lock_expires"] and d["lock_expires"] > now():
            raise Conflict(f"Diagram lease is held by {d['lock_user']}.")
        latest = one("SELECT * FROM diagram_versions WHERE diagram_id=? ORDER BY ver_no DESC LIMIT 1", (did,))
        if base_ver is not None and latest and int(base_ver) != latest["ver_no"]:
            raise Conflict(f"Diagram changed (now revision {latest['ver_no']}, you edited revision {base_ver}). Reload before saving; nothing was overwritten.")
        if latest and latest["sha256"] == sha and not png_b64:
            return dict(ver_no=latest["ver_no"], changed=False)
        asset = None
        if png_b64:
            raw = base64.b64decode(png_b64.split(",", 1)[-1], validate=False)
            if raw[:8] != b"\x89PNG\r\n\x1a\n" or len(raw) > 12 * 1024 * 1024:
                raise Invalid("Preview must be a PNG under 12 MB.")
            asset = store_asset(raw, "image/png", f"{d['code']}.png", None, "preview")
        elif latest:
            asset = None  # preview missing for this revision; exports fall back to the server renderer
        if proc:
            ensure_draft(proc, user)
        dv = _add_dv(did, xml, "editor", asset, note or "Edited in Flow Studio", user["username"])
        if proc:
            v = open_version(proc["id"])
            db.db().execute("UPDATE process_versions SET diagram_version_id=?, updated_at=? WHERE id=?", (dv, now(), v["id"]))
            reindex(proc["id"])
        new_exp = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=config.LOCK_MINUTES)).strftime("%Y-%m-%dT%H:%M:%SZ")
        db.db().execute("UPDATE diagrams SET lock_user=?, lock_expires=? WHERE id=?", (user["username"], new_exp, did))
        audit(user, "diagram_saved", "diagram", d["code"], f"revision {latest['ver_no'] + 1 if latest else 1}")
    return dict(ver_no=(latest["ver_no"] + 1 if latest else 1), changed=True)


def diagram_versions(did):
    return q("SELECT id,ver_no,origin,validation,note,author,created_at,preview_asset_id,sha256 FROM diagram_versions WHERE diagram_id=? ORDER BY ver_no DESC", (did,))


def diagram_nodes(dvid):
    return [dict(node_id=r["node_id"], label=r["label"], meta=jloads(r["meta"], {})) for r in q("SELECT * FROM diagram_nodes WHERE diagram_version_id=? ORDER BY id", (dvid,))]


NODE_META_KEYS = ["process_ref", "activity_id", "department", "role", "sap", "approval", "input", "output", "related", "evidence"]


def set_node_meta(dvid, node_id, user, meta):
    dv = one("SELECT dv.*,d.process_id FROM diagram_versions dv JOIN diagrams d ON d.id=dv.diagram_id WHERE dv.id=?", (dvid,))
    if not dv:
        raise NotFound("Diagram version not found")
    proc = one("SELECT * FROM processes WHERE id=?", (dv["process_id"],)) if dv["process_id"] else None
    need(user, "edit", proc)
    latest = one("SELECT id FROM diagram_versions WHERE diagram_id=? ORDER BY ver_no DESC LIMIT 1", (dv["diagram_id"],))
    if latest["id"] != dvid:
        raise Conflict("Only the latest diagram revision can be annotated.")
    clean = {k: str(meta.get(k, ""))[:300] for k in NODE_META_KEYS if str(meta.get(k, "")).strip()}
    if clean.get("process_ref") and not one("SELECT 1 FROM processes WHERE process_id=?", (clean["process_ref"],)):
        raise Invalid(f"Unknown process reference {clean['process_ref']}")
    with tx():
        db.db().execute("UPDATE diagram_nodes SET meta=? WHERE diagram_version_id=? AND node_id=?", (json.dumps(clean), dvid, node_id))
        if proc:
            reindex(proc["id"])
    return clean


def diagram_svg(dvid):
    dv = one("SELECT * FROM diagram_versions WHERE id=?", (dvid,))
    if not dv:
        raise NotFound("Diagram version not found")
    links = {n["node_id"]: f"#/process/{n['meta']['process_ref']}" for n in diagram_nodes(dvid) if n["meta"].get("process_ref")}
    return drawio.to_svg(dv["xml"], links)


# ------------------------------------------------------------------ search index & relationships
def reindex(pid: int):
    p = one("SELECT p.*,d.name dname FROM processes p LEFT JOIN departments d ON d.id=p.department_id WHERE p.id=?", (pid,))
    head = " ".join([p["process_id"], p["chart_id"] or "", p["name"], p["dname"] or "", p["owner"], p["countries"], p["category"], p["kind"]])

    def body(v):
        if not v:
            return ""
        t = head + " " + content_text(v["content"])
        if v.get("diagram_version_id"):
            dv = one("SELECT xml FROM diagram_versions WHERE id=?", (v["diagram_version_id"],))
            if dv:
                t += " " + drawio.labels_text(dv["xml"])
                t += " " + " ".join(json.dumps(n["meta"]) for n in diagram_nodes(v["diagram_version_id"]) if n["meta"])
        return t.lower()
    lv, pv = latest_version(pid), published_version(pid)
    db.db().execute("INSERT INTO search_index(process_id,body,body_pub) VALUES(?,?,?) ON CONFLICT(process_id) DO UPDATE SET body=excluded.body, body_pub=excluded.body_pub",
                    (pid, body(lv), body(pv) if pv else ""))
    refresh_inferred(pid)


ID_RE = re.compile(r"\b([A-Z]{2,3}-[A-Z]-[A-Z0-9]{2,3}-\d{2}(?:\.\d+)?|[A-Z]{3}-N-\d{3})\b")


def refresh_inferred(pid: int):
    p = one("SELECT * FROM processes WHERE id=?", (pid,))
    lv = latest_version(pid)
    if not lv:
        return
    text = content_text(lv["content"])
    c = db.db()
    c.execute("DELETE FROM relationships WHERE from_id=? AND inferred=1", (pid,))
    for m in set(ID_RE.findall(text)):
        if m == p["process_id"]:
            continue
        t = one("SELECT id FROM processes WHERE process_id=?", (m,))
        if t:
            c.execute("INSERT OR IGNORE INTO relationships(from_id,to_id,rel_type,note,inferred) VALUES(?,?,?,?,1)", (pid, t["id"], "related", "ID mentioned in text (inferred)"))


def infer_all_relationships():
    for r in q("SELECT id FROM processes"):
        refresh_inferred(r["id"])


REL_TYPES = ["parent", "next", "supports", "approval", "triggers", "exception", "related"]


def add_relationship(user, from_pid, to_pid, rel_type, note=""):
    a, b = get_process(from_pid), get_process(to_pid)
    need(user, "manage_relationships", a)
    if rel_type not in REL_TYPES:
        raise Invalid("Unknown relationship type.")
    if a["id"] == b["id"]:
        raise Invalid("A process cannot relate to itself.")
    with tx():
        db.db().execute("INSERT OR REPLACE INTO relationships(from_id,to_id,rel_type,note,inferred) VALUES(?,?,?,?,0)", (a["id"], b["id"], rel_type, note[:300]))
        if rel_type == "parent":
            db.db().execute("UPDATE processes SET parent_id=? WHERE id=?", (b["id"], a["id"]))
        audit(user, "relationship_added", "process", from_pid, f"{rel_type} -> {to_pid}")


def remove_relationship(user, rid):
    r = one("SELECT * FROM relationships WHERE id=?", (rid,))
    if not r:
        raise NotFound("Relationship not found")
    a = one("SELECT * FROM processes WHERE id=?", (r["from_id"],))
    need(user, "manage_relationships", a)
    with tx():
        db.db().execute("DELETE FROM relationships WHERE id=?", (rid,))
        audit(user, "relationship_removed", "process", a["process_id"], str(rid))


# ------------------------------------------------------------------ misc governance actions
def reassign_department(pid_text, user, dept_id):
    proc = get_process(pid_text)
    if not (can(user, "accept_import", proc) or can(user, "edit", proc)):
        raise Forbidden("Your role may not reassign departments.")
    d = one("SELECT * FROM departments WHERE id=?", (dept_id,))
    if not d:
        raise Invalid("Unknown department.")
    with tx():
        db.db().execute("UPDATE processes SET department_id=? WHERE id=?", (d["id"], proc["id"]))
        reindex(proc["id"])
        audit(user, "department_reassigned", "process", pid_text, f"{proc['department']} -> {d['name']}")


def log_finding(pid_text, user, kind, title, detail):
    proc = get_process(pid_text)
    need(user, "comment", proc)
    if kind not in ("conflict", "gap", "duplicate", "uncertain"):
        raise Invalid("Unknown finding kind.")
    with tx():
        add_finding(kind, "medium", None, proc["id"], title[:200], detail[:4000])
        audit(user, "finding_logged", "process", pid_text, title[:200])


# ------------------------------------------------------------------ ownership workbench
def assign_ownership(user, items, only_empty=False):
    """items: list of dicts {process_id, owner?, reviewer?, review_months?}. Process-level metadata (not versioned content)."""
    done, skipped = 0, []
    with tx():
        for it in items:
            p = get_process(it["process_id"])
            need(user, "assign_owner", p)
            sets, args = [], []
            for k in ("owner", "reviewer"):
                if k in it and it[k] is not None and str(it[k]).strip():
                    if only_empty and p[k]:
                        continue
                    sets.append(f"{k}=?")
                    args.append(str(it[k]).strip()[:120])
            rm = it.get("review_months")
            if rm not in (None, "") and str(rm).strip().isdigit() and 1 <= int(rm) <= 60 and not (only_empty and p["review_months"]):
                sets.append("review_months=?")
                args.append(int(rm))
            if not sets:
                skipped.append(p["process_id"])
                continue
            db.db().execute(f"UPDATE processes SET {','.join(sets)} WHERE id=?", (*args, p["id"]))
            reindex(p["id"])
            audit(user, "ownership_assigned", "process", p["process_id"], ", ".join(f"{a.split('=')[0]}={v}" for a, v in zip(sets, args)))
            done += 1
    return dict(updated=done, skipped=skipped)


def inbox(user):
    """Work waiting for this user (reviews, approvals, publishing, returned drafts, overdue reviews of own processes)."""
    out = []
    rows = q("SELECT p.process_id,p.name,p.owner,p.reviewer,p.next_review,p.department_id,v.status,v.version,v.author FROM processes p "
             "JOIN process_versions v ON v.process_id=p.id AND v.id=(SELECT id FROM process_versions WHERE process_id=p.id ORDER BY major DESC,minor DESC,id DESC LIMIT 1)")
    today = dt.date.today().isoformat()
    me = {user["username"].lower(), user["display_name"].lower()}
    for r in rows:
        proc = dict(department_id=r["department_id"])
        st = r["status"]
        if st == "under_review" and can(user, "review", proc) and r["author"] != user["username"]:
            out.append(dict(kind="Review requested", process_id=r["process_id"], name=r["name"], detail=f"v{r['version']} by {r['author']}"))
        elif st == "pending_approval" and can(user, "approve", proc) and r["author"] != user["username"]:
            out.append(dict(kind="Approval requested", process_id=r["process_id"], name=r["name"], detail=f"v{r['version']}"))
        elif st == "approved" and can(user, "publish", proc):
            out.append(dict(kind="Ready to publish", process_id=r["process_id"], name=r["name"], detail=f"v{r['version']}"))
        elif st == "changes_requested" and r["author"] == user["username"]:
            out.append(dict(kind="Changes requested", process_id=r["process_id"], name=r["name"], detail=f"v{r['version']}"))
        if r["next_review"] and r["next_review"] < today and ((r["owner"] or "").lower() in me or user["role"] in ("admin", "controller")):
            out.append(dict(kind="Review overdue", process_id=r["process_id"], name=r["name"], detail=f"due {r['next_review']}"))
    return out


# ------------------------------------------------------------------ value-stream link suggestions
_STOP = {"process", "material", "and", "the", "of", "to", "for", "in", "with", "a", "uae", "exp", "ksa", "ob", "virtual", "request"}
_ALIAS = {"cs": ["customer", "service"], "gr": ["goods", "receipt"], "pr": ["pr"], "po": ["po"]}


def _tokens(text):
    toks = []
    for w in re.findall(r"[a-z0-9]+", (text or "").lower()):
        toks += _ALIAS.get(w, [w])
    return {t for t in toks if t not in _STOP and len(t) > 1}


def suggest_value_stream_links(user, vs_process="SC-M-VS-01"):
    """Match Level-1 value-stream stages to process records by name and add *inferred* handover links.
    Suggestions only (inferred=2): they are labelled as such and can be removed."""
    need(user, "manage_relationships")
    vs = one("SELECT id FROM processes WHERE process_id=?", (vs_process,))
    if not vs:
        raise NotFound(f"{vs_process} (Level 1 value stream) is not loaded.")
    v = latest_version(vs["id"])
    dv = one("SELECT id,xml FROM diagram_versions WHERE id=?", (v["diagram_version_id"],))
    sc = drawio.scene(dv["xml"])
    procs = q("SELECT id,process_id,name,kind FROM processes WHERE kind IN ('sop','approval','department','form','work_instruction') AND process_id<>?", (vs_process,))
    ptok = {p["id"]: _tokens(p["name"]) for p in procs}
    stages = {b["id"]: b for b in sc["boxes"].values() if b["label"] and not (b["style"]["_first"] == "swimlane" or b["style"].get("swimlane"))}
    match = {}
    for sid_, b in stages.items():
        t = _tokens(b["label"])
        if not t:
            continue
        scored = []
        for p in procs:
            pt = ptok[p["id"]]
            if not pt:
                continue
            common = t & pt
            if not common:
                continue
            score = len(common) / min(len(t), len(pt))
            if score >= 0.5 and (len(common) >= 2 or min(len(t), len(pt)) == 1) and (p["kind"] != "form" or "checklist" in t):
                scored.append((score, p))
        if scored:
            top = max(s for s, _ in scored)
            match[sid_] = [p for s, p in scored if s >= top - 0.01][:4]
    added, linked_nodes = 0, 0
    with tx():
        for sid_, ps in match.items():
            if len(ps) == 1:
                row = one("SELECT meta FROM diagram_nodes WHERE diagram_version_id=? AND node_id=?", (dv["id"], sid_))
                if row:
                    meta = jloads(row["meta"], {})
                    if not meta.get("process_ref"):
                        meta["process_ref"] = ps[0]["process_id"]
                        db.db().execute("UPDATE diagram_nodes SET meta=? WHERE diagram_version_id=? AND node_id=?", (json.dumps(meta), dv["id"], sid_))
                        linked_nodes += 1
        for e in sc["edges"]:
            for a in match.get(e["source"], []):
                for b in match.get(e["target"], []):
                    if a["id"] != b["id"] and not one("SELECT 1 FROM relationships WHERE from_id=? AND to_id=? AND rel_type='next'", (a["id"], b["id"])):
                        db.db().execute("INSERT INTO relationships(from_id,to_id,rel_type,note,inferred) VALUES(?,?,?,?,2)",
                                        (a["id"], b["id"], "next", f"Suggested from {vs_process} value-stream handover (name match) - confirm or remove"))
                        added += 1
        audit(user, "value_stream_links_suggested", "process", vs_process, f"{added} links, {linked_nodes} nodes linked")
    return dict(stages_matched=len(match), links_added=added, nodes_linked=linked_nodes)
