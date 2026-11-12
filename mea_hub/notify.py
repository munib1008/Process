"""Notifications: tell people when work is waiting for them, so that reviews and approvals do not stall.

What is sent
  new tasks   as soon as something appears in a person's task list (review requested, approval requested, ready to
              publish, changes requested, review overdue) and when a periodic review comes up within 30 days
  published   to the author when their revision has been published
  digest      all open tasks of a person, weekly (Monday) or daily, at a set hour
One message per person and run lists everything new. A task is announced once; it is announced again only if it
disappears and comes back.

Channels (configured on the server, docs/NOTIFICATIONS.md)
  e-mail      MEA_HUB_SMTP_HOST [, MEA_HUB_SMTP_PORT, MEA_HUB_SMTP_STARTTLS, MEA_HUB_SMTP_USER, MEA_HUB_SMTP_PASSWORD_FILE], MEA_HUB_MAIL_FROM
  Teams       MEA_HUB_TEAMS_WEBHOOK_FILE - a file with the address of a Teams "Workflows" webhook; one channel gets a
              summary of what is newly waiting (no personal task lists)
Options       MEA_HUB_NOTIFY_MINUTES (5), MEA_HUB_NOTIFY_DIGEST (weekly | daily | off), MEA_HUB_NOTIFY_DIGEST_HOUR (8)

Sending never blocks or fails a workflow step: a background run does it, and a failure is recorded and tried again."""
import datetime as dt
import json
import os
import re
import smtplib
import ssl
import threading
import time
import urllib.error
import urllib.request
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from . import db, service as svc
from .db import one, q

DUE_SOON_DAYS = 30
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_lock = threading.Lock()


def settings():
    env = lambda k, d="": (os.environ.get(k) or d).strip()
    host = env("MEA_HUB_SMTP_HOST")
    port = int(env("MEA_HUB_SMTP_PORT", "25") or 25)
    pw = ""
    if env("MEA_HUB_SMTP_PASSWORD_FILE"):
        try:
            with open(env("MEA_HUB_SMTP_PASSWORD_FILE"), encoding="utf-8") as f:
                pw = f.read().strip()
        except OSError:
            pw = ""
    hook = ""
    if env("MEA_HUB_TEAMS_WEBHOOK_FILE"):
        try:
            with open(env("MEA_HUB_TEAMS_WEBHOOK_FILE"), encoding="utf-8") as f:
                hook = f.read().strip()
        except OSError:
            hook = ""
    if not re.fullmatch(r"https://[^\s]+|http://(localhost|127\.0\.0\.1)(:\d+)?/[^\s]*", hook):
        hook = ""
    digest = env("MEA_HUB_NOTIFY_DIGEST", "weekly").lower()
    sender = env("MEA_HUB_MAIL_FROM")
    return dict(smtp_host=host, smtp_port=port, smtp_starttls=env("MEA_HUB_SMTP_STARTTLS", "1" if port == 587 else "0") == "1", smtp_user=env("MEA_HUB_SMTP_USER"),
                smtp_password=pw, mail_from=sender if EMAIL_RE.fullmatch(sender) else "", teams_webhook=hook,
                public_url=env("MEA_HUB_PUBLIC_URL").rstrip("/"), minutes=max(1, int(env("MEA_HUB_NOTIFY_MINUTES", "5") or 5)),
                digest=digest if digest in ("weekly", "daily", "off") else "weekly", digest_hour=min(23, max(0, int(env("MEA_HUB_NOTIFY_DIGEST_HOUR", "8") or 8))))


def mail_ready(cfg=None):
    cfg = cfg or settings()
    return bool(cfg["smtp_host"] and cfg["mail_from"])


def enabled():
    cfg = settings()
    return mail_ready(cfg) or bool(cfg["teams_webhook"])


def address(user):
    """E-mail address of a user: the stored one, else the user name when it is an address (single sign-on users)."""
    for v in (user.get("email") or "", user.get("username") or ""):
        if EMAIL_RE.fullmatch(v.strip()):
            return v.strip()
    return ""


def _link(cfg, pid):
    return f"{cfg['public_url']}/#/process/{urllib.request.quote(pid, safe='')}" if cfg["public_url"] else ""


def _tasks(user):
    """Task list of a user as {key: item}; adds periodic reviews that come up within 30 days."""
    out = {}
    for t in svc.inbox(user):
        out[f"{t['kind']}|{t['process_id']}|{t['detail']}"] = t
    today, soon = dt.date.today().isoformat(), (dt.date.today() + dt.timedelta(days=DUE_SOON_DAYS)).isoformat()
    me = {user["username"].lower(), user["display_name"].lower()}
    for r in q("SELECT process_id,name,owner,next_review FROM processes WHERE next_review IS NOT NULL AND next_review>=? AND next_review<=?", (today, soon)):
        if (r["owner"] or "").lower() in me or user["role"] in ("admin", "controller"):
            out[f"Review due soon|{r['process_id']}|due {r['next_review']}"] = dict(kind="Review due soon", process_id=r["process_id"], name=r["name"], detail=f"due {r['next_review']}")
    return out


def _published_for(user, since):
    rows = q("SELECT p.process_id,p.name,v.version,v.published_at FROM process_versions v JOIN processes p ON p.id=v.process_id "
             "WHERE v.status='published' AND v.author=? AND v.published_at>?", (user["username"], since))
    return {f"Published|{r['process_id']}|v{r['version']}": dict(kind="Published", process_id=r["process_id"], name=r["name"], detail=f"v{r['version']} is now the valid version") for r in rows}


def _compose(cfg, user, items, digest):
    n = len(items)
    subject = f"MEA Process Hub: {n} open task{'s' if n != 1 else ''}" if digest else f"MEA Process Hub: {n} new item{'s' if n != 1 else ''} for you"
    lines = [f"Hello {user['display_name']},", "", "these are your open tasks in MEA Process Hub:" if digest else "this is new for you in MEA Process Hub:", ""]
    html = [f"<p>Hello {_esc(user['display_name'])},</p><p>{'These are your open tasks' if digest else 'This is new for you'} in MEA Process Hub:</p><table cellpadding='6' style='border-collapse:collapse;font-family:Segoe UI,Arial,sans-serif;font-size:14px'>"]
    for t in sorted(items, key=lambda t: (t["kind"], t["process_id"])):
        link = _link(cfg, t["process_id"])
        lines.append(f"- {t['kind']}: {t['process_id']} – {t['name']} ({t['detail']})" + (f"\n  {link}" if link else ""))
        name = f"<a href='{_esc(link)}'>{_esc(t['process_id'])} – {_esc(t['name'])}</a>" if link else f"{_esc(t['process_id'])} – {_esc(t['name'])}"
        html.append(f"<tr><td style='border-bottom:1px solid #ddd'><b>{_esc(t['kind'])}</b></td><td style='border-bottom:1px solid #ddd'>{name}</td><td style='border-bottom:1px solid #ddd;color:#555'>{_esc(t['detail'])}</td></tr>")
    foot = "You receive this because you have a role in MEA Process Hub. Switch these messages off on the Dashboard (My tasks)."
    lines += ["", foot]
    html.append(f"</table><p style='color:#666;font-size:12px'>{foot}</p>")
    return subject, "\n".join(lines), "".join(html)


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("'", "&#39;").replace('"', "&quot;")


def send_mail(cfg, to, subject, text, html=None):
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"], msg["Date"], msg["Message-ID"] = cfg["mail_from"], to, subject, formatdate(localtime=True), make_msgid(domain=cfg["mail_from"].split("@")[-1])
    msg["Auto-Submitted"] = "auto-generated"
    msg.set_content(text)
    if html:
        msg.add_alternative(f"<html><body>{html}</body></html>", subtype="html")
    with smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"], timeout=20) as s:
        if cfg["smtp_starttls"]:
            s.starttls(context=ssl.create_default_context())
        if cfg["smtp_user"]:
            s.login(cfg["smtp_user"], cfg["smtp_password"])
        s.send_message(msg)


def post_teams(cfg, title, lines, link=""):
    """Adaptive Card for a Teams 'Workflows' webhook (When a Teams webhook request is received > Post card in a chat or channel)."""
    body = [dict(type="TextBlock", text=title, weight="Bolder", size="Medium", wrap=True)] + [dict(type="TextBlock", text=x, wrap=True, spacing="Small") for x in lines[:25]]
    card = {"$schema": "http://adaptivecards.io/schemas/adaptive-card.json", "type": "AdaptiveCard", "version": "1.4", "body": body}
    if link:
        card["actions"] = [dict(type="Action.OpenUrl", title="Open MEA Process Hub", url=link)]
    data = json.dumps(dict(type="message", attachments=[dict(contentType="application/vnd.microsoft.card.adaptive", contentUrl=None, content=card)])).encode()
    req = urllib.request.Request(cfg["teams_webhook"], data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        r.read()


def _log(user_id, channel, subject, ok, error=""):
    db.db().execute("INSERT INTO notifications(user_id,channel,subject,status,error,created_at) VALUES(?,?,?,?,?,?)",
                    (user_id, channel, subject[:200], "sent" if ok else "failed", str(error)[:300], svc.now()))


def _digest_due(cfg, now):
    if cfg["digest"] == "off" or now.hour < cfg["digest_hour"] or (cfg["digest"] == "weekly" and now.weekday() != 0):
        return False
    return svc.cfg("notify_last_digest", "") != now.date().isoformat()


def run_once(now=None):
    """One pass: new tasks to each person, the Teams summary, the digest when it is due. -> counts"""
    cfg = settings()
    out = dict(mails=0, failed=0, teams=0, people_without_address=0)
    if not (mail_ready(cfg) or cfg["teams_webhook"]):
        return out
    now = now or dt.datetime.now()
    with _lock:
        c = db.db()
        digest = _digest_due(cfg, now)
        since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        fresh_all = {}
        for u in q("SELECT * FROM users WHERE active=1"):
            user = dict(id=u["id"], username=u["username"], display_name=u["display_name"], role=u["role"], department_id=u["department_id"], email=u["email"])
            tasks = _tasks(user)
            current = dict(tasks, **_published_for(user, since))
            known = {r["key"] for r in q("SELECT key FROM notified WHERE user_id=?", (u["id"],))}
            fresh = {k: v for k, v in current.items() if k not in known}
            for k in known - set(current):                   # a task that is gone may be announced again if it returns
                c.execute("DELETE FROM notified WHERE user_id=? AND key=?", (u["id"], k))
            for k, v in fresh.items():
                if v["kind"] != "Published":
                    fresh_all[f"{v['kind']}|{v['process_id']}"] = v
            to = address(user)
            wants = u["notify"] != 0
            sent = True
            if mail_ready(cfg) and wants and (fresh or (digest and tasks)):
                if not to:
                    out["people_without_address"] += 1
                    sent = False
                else:
                    for items, is_digest in ((list(fresh.values()), False), (list(tasks.values()), True)):
                        if not items or (is_digest and not digest):
                            continue
                        subject, text, html = _compose(cfg, user, items, is_digest)
                        try:
                            send_mail(cfg, to, subject, text, html)
                            _log(u["id"], "email", subject, True)
                            out["mails"] += 1
                        except (OSError, smtplib.SMTPException) as e:
                            _log(u["id"], "email", subject, False, e)
                            out["failed"] += 1
                            sent = False
            if sent or not mail_ready(cfg) or not wants:     # not sent because of a failure or a missing address: try again next time
                for k in fresh:
                    c.execute("INSERT OR IGNORE INTO notified(user_id,key,sent_at) VALUES(?,?,?)", (u["id"], k, svc.now()))
        if cfg["teams_webhook"]:
            announced = {r["key"] for r in q("SELECT key FROM notified WHERE user_id=0")}
            new = {k: v for k, v in fresh_all.items() if k not in announced}
            if new:
                lines = [f"**{v['kind']}**: {v['process_id']} – {v['name']} ({v['detail']})" for v in sorted(new.values(), key=lambda v: (v["kind"], v["process_id"]))]
                title = f"MEA Process Hub: {len(new)} item{'s' if len(new) != 1 else ''} waiting"
                try:
                    post_teams(cfg, title, lines, cfg["public_url"] + "/#/dashboard" if cfg["public_url"] else "")
                    _log(None, "teams", title, True)
                    out["teams"] += 1
                    for k in new:
                        c.execute("INSERT OR IGNORE INTO notified(user_id,key,sent_at) VALUES(0,?,?)", (k, svc.now()))
                except (OSError, urllib.error.URLError) as e:
                    _log(None, "teams", title, False, e)
                    out["failed"] += 1
            c.execute("DELETE FROM notified WHERE user_id=0 AND sent_at<?", ((dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=60)).strftime("%Y-%m-%dT%H:%M:%SZ"),))
        if digest:
            svc.set_cfg("notify_last_digest", now.date().isoformat())
        c.execute("DELETE FROM notifications WHERE id NOT IN (SELECT id FROM notifications ORDER BY id DESC LIMIT 2000)")
    return out


def send_test(user):
    cfg = settings()
    if not mail_ready(cfg):
        raise svc.Invalid("E-mail is not configured on this server (MEA_HUB_SMTP_HOST and MEA_HUB_MAIL_FROM).")
    to = address(user)
    if not to:
        raise svc.Invalid("Your user has no e-mail address. Enter one under Users & roles.")
    subject = "MEA Process Hub: test message"
    try:
        send_mail(cfg, to, subject, f"Hello {user['display_name']},\n\nthis is a test message from MEA Process Hub. Notifications by e-mail work.\n")
        _log(user["id"], "email", subject, True)
    except (OSError, smtplib.SMTPException) as e:
        _log(user["id"], "email", subject, False, e)
        raise svc.Invalid(f"The mail server refused or could not be reached: {e}"[:300])
    return to


def status():
    cfg = settings()
    users = q("SELECT id,username,display_name,email,notify FROM users WHERE active=1")
    return dict(email=dict(configured=mail_ready(cfg), host=cfg["smtp_host"], port=cfg["smtp_port"], starttls=cfg["smtp_starttls"], sender=cfg["mail_from"], login=bool(cfg["smtp_user"])),
                teams=dict(configured=bool(cfg["teams_webhook"])), links=bool(cfg["public_url"]), minutes=cfg["minutes"], digest=cfg["digest"], digest_hour=cfg["digest_hour"],
                without_address=[u["username"] for u in users if not address(u)], switched_off=[u["username"] for u in users if u["notify"] == 0],
                recent=q("SELECT n.id,n.channel,n.subject,n.status,n.error,n.created_at,u.username FROM notifications n LEFT JOIN users u ON u.id=n.user_id ORDER BY n.id DESC LIMIT 30"))


def start_worker():
    """Background runs every few minutes while the server is up (only when a channel is configured)."""
    if not enabled():
        return None

    def loop():
        time.sleep(20)
        while True:
            try:
                run_once()
            except Exception:                                # never let a notification problem stop the loop
                try:
                    import traceback
                    from . import config
                    with open(os.path.join(config.DATA_DIR, "error.log"), "a", encoding="utf-8") as f:
                        f.write(f"{svc.now()} notifications: {traceback.format_exc()}\n")
                except OSError:
                    pass
            time.sleep(settings()["minutes"] * 60)
    t = threading.Thread(target=loop, name="notifications", daemon=True)
    t.start()
    return t
