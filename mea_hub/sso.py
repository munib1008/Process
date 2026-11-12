"""Single sign-on with Microsoft Entra ID (OpenID Connect, authorization code flow with PKCE).

Switched on by configuration of the server, never from the user interface (docs/SSO_ENTRA.md):

    MEA_HUB_PUBLIC_URL               https address under which users reach the tool, e.g. https://processhub.example.com
    MEA_HUB_OIDC_TENANT              directory (tenant) ID of the organisation
    MEA_HUB_OIDC_CLIENT_ID           application (client) ID of the app registration
    MEA_HUB_OIDC_CLIENT_SECRET_FILE  file that holds the client secret (preferred), or MEA_HUB_OIDC_CLIENT_SECRET
    MEA_HUB_OIDC_ROLE_SOURCE         entra (default): roles come from the app roles in the token at every sign-in
                                     tool: Entra only proves who the person is, roles are given in the tool
    MEA_HUB_OIDC_DEFAULT_ROLE        role of a person without an app role: viewer (default), another role, or none = no access
    MEA_HUB_OIDC_ONLY                1 = passwords are accepted only for local administrators (break-glass)

What is checked at every sign-in: the state and PKCE verifier of this sign-in attempt, then the ID token's signature
(RS256, key from the tenant's published key set), issuer, audience, tenant, validity period and nonce.
The tool never sees the person's password and stores no token: only the object ID, name and user name."""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request

from . import db, service as svc
from .db import one

STATE_MINUTES = 10
HANDOFF_SECONDS = 90
SKEW = 120
_CACHE = {}


class SsoError(Exception):
    pass


def settings():
    """Configuration, or None when single sign-on is not (completely) configured."""
    env = os.environ.get
    tenant, client, public = (env("MEA_HUB_OIDC_TENANT") or "").strip(), (env("MEA_HUB_OIDC_CLIENT_ID") or "").strip(), (env("MEA_HUB_PUBLIC_URL") or "").strip().rstrip("/")
    authority = (env("MEA_HUB_OIDC_AUTHORITY") or "").strip().rstrip("/")
    if not authority and tenant:
        if not re.fullmatch(r"[A-Za-z0-9.-]{3,80}", tenant) or tenant.lower() in ("common", "organizations", "consumers"):
            return None                                      # one named tenant only
        authority = f"https://login.microsoftonline.com/{tenant}/v2.0"
    if not (authority and client and public):
        return None
    local = re.fullmatch(r"http://(localhost|127\.0\.0\.1)(:\d+)?(/.*)?", authority) is not None      # test identity provider only
    if not (authority.startswith("https://") or local) or not (public.startswith("https://") or re.fullmatch(r"http://(localhost|127\.0\.0\.1)(:\d+)?", public)):
        return None
    secret = env("MEA_HUB_OIDC_CLIENT_SECRET") or ""
    path = env("MEA_HUB_OIDC_CLIENT_SECRET_FILE")
    if path:
        try:
            with open(path, encoding="utf-8") as f:
                secret = f.read().strip()
        except OSError:
            secret = ""
    default = (env("MEA_HUB_OIDC_DEFAULT_ROLE") or "viewer").strip().lower()
    return dict(authority=authority, client_id=client, client_secret=secret, public_url=public, redirect_uri=public + "/auth/callback",
                role_source="tool" if (env("MEA_HUB_OIDC_ROLE_SOURCE") or "").strip().lower() == "tool" else "entra",
                default_role=default if default in svc.ROLES else ("none" if default == "none" else "viewer"), only=env("MEA_HUB_OIDC_ONLY") == "1")


def enabled():
    return settings() is not None


def passwords_restricted():
    s = settings()
    return bool(s and s["only"])


def _get_json(url, data=None):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode() if data else None,
                                 headers={"Accept": "application/json", **({"Content-Type": "application/x-www-form-urlencoded"} if data else {})})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8"))
        except ValueError:
            body = {}
        raise SsoError(f"The identity provider answered {e.code}: {body.get('error_description') or body.get('error') or 'no details'}"[:400])
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise SsoError(f"The identity provider could not be reached ({e}).")


def discovery(cfg):
    key = ("disc", cfg["authority"])
    hit = _CACHE.get(key)
    if not hit or hit[0] < time.time() - 3600:
        doc = _get_json(cfg["authority"] + "/.well-known/openid-configuration")
        for k in ("issuer", "authorization_endpoint", "token_endpoint", "jwks_uri"):
            if not isinstance(doc.get(k), str):
                raise SsoError("The identity provider's configuration document is incomplete.")
        hit = _CACHE[key] = (time.time(), doc)
    return hit[1]


def _keys(cfg, kid):
    key = ("jwks", cfg["authority"])
    hit = _CACHE.get(key)
    if not hit or kid not in hit[1] and hit[0] < time.time() - 60 or hit[0] < time.time() - 86400:
        doc = _get_json(discovery(cfg)["jwks_uri"])
        hit = _CACHE[key] = (time.time(), {k.get("kid"): k for k in doc.get("keys", []) if k.get("kty") == "RSA"})
    return hit[1].get(kid)


def _b64(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def rsa_verify(n: int, e: int, signature: bytes, message: bytes) -> bool:
    """RSASSA-PKCS1-v1_5 with SHA-256 (the "RS256" of the tokens). A public-key operation: no secret is involved."""
    k = (n.bit_length() + 7) // 8
    if n.bit_length() < 2048 or e < 3 or e % 2 == 0 or len(signature) != k:
        return False
    m = pow(int.from_bytes(signature, "big"), e, n).to_bytes(k, "big")
    digest_info = bytes.fromhex("3031300d060960864801650304020105000420") + hashlib.sha256(message).digest()
    return hmac.compare_digest(m, b"\x00\x01" + b"\xff" * (k - 3 - len(digest_info)) + b"\x00" + digest_info)


def verify_id_token(cfg, token: str, nonce: str) -> dict:
    try:
        h64, p64, s64 = token.split(".")
        header, claims, sig = json.loads(_b64(h64)), json.loads(_b64(p64)), _b64(s64)
    except (ValueError, AttributeError):
        raise SsoError("The sign-in answer is not a valid token.")
    if header.get("alg") != "RS256":
        raise SsoError("The token uses a signature method that is not accepted.")
    jwk = _keys(cfg, header.get("kid"))
    if not jwk:
        raise SsoError("The token was signed with a key the identity provider does not publish.")
    try:
        n, e = int.from_bytes(_b64(jwk["n"]), "big"), int.from_bytes(_b64(jwk["e"]), "big")
    except (KeyError, ValueError):
        raise SsoError("The identity provider's signing key is unreadable.")
    if not rsa_verify(n, e, sig, f"{h64}.{p64}".encode()):
        raise SsoError("The token's signature is not valid.")
    now = time.time()
    issuer = discovery(cfg)["issuer"]
    aud = claims.get("aud")
    if claims.get("iss") != issuer:
        raise SsoError("The token was issued by another directory.")
    if not (aud == cfg["client_id"] or isinstance(aud, list) and cfg["client_id"] in aud):
        raise SsoError("The token was issued for another application.")
    if not isinstance(claims.get("exp"), (int, float)) or claims["exp"] < now - SKEW or claims.get("nbf", 0) > now + SKEW:
        raise SsoError("The token is expired or not yet valid.")
    if not nonce or not hmac.compare_digest(str(claims.get("nonce", "")), nonce):
        raise SsoError("The token does not belong to this sign-in attempt.")
    m = re.search(r"/([0-9a-fA-F-]{36})/", issuer + "/")
    if m and claims.get("tid") and claims["tid"].lower() != m.group(1).lower():
        raise SsoError("The token belongs to another tenant.")
    if not (claims.get("oid") or claims.get("sub")):
        raise SsoError("The token names no person.")
    return claims


def begin(popup=False):
    """Start a sign-in: remember state, nonce and PKCE verifier for ten minutes and return the address of the sign-in page."""
    cfg = settings()
    if not cfg:
        raise SsoError("Single sign-on is not configured on this server.")
    state, nonce, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(24), secrets.token_urlsafe(48)
    c = db.db()
    c.execute("DELETE FROM sso_states WHERE created < ?", (time.time() - STATE_MINUTES * 60,))
    c.execute("INSERT INTO sso_states(state,nonce,verifier,popup,created) VALUES(?,?,?,?,?)", (state, nonce, verifier, 1 if popup else 0, time.time()))
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    q = dict(client_id=cfg["client_id"], response_type="code", redirect_uri=cfg["redirect_uri"], response_mode="query", scope="openid profile email",
             state=state, nonce=nonce, code_challenge=challenge, code_challenge_method="S256")
    return discovery(cfg)["authorization_endpoint"] + "?" + urllib.parse.urlencode(q)


def role_from_claims(claims):
    """Highest tool role named in the token's app roles: "<role>" or "<role>.<DEPARTMENT CODE>", optionally prefixed "ProcessHub."."""
    best = None
    for value in claims.get("roles") or []:
        v = re.sub(r"^processhub\.", "", str(value).strip(), flags=re.I)
        role, _, dept = v.partition(".")
        role = role.lower()
        if role not in svc.ROLES:
            continue
        dept_id = None
        if dept:
            d = one("SELECT id FROM departments WHERE upper(code)=?", (dept.upper(),))
            if not d:
                continue                                     # a role for a department the tool does not know is ignored
            dept_id = d["id"]
        rank = svc.ROLES.index(role)
        if best is None or rank < best[0]:
            best = (rank, role, dept_id)
    return (best[1], best[2]) if best else None


def _username(claims):
    for k in ("preferred_username", "email", "upn"):
        v = str(claims.get(k) or "").strip().lower()
        if re.fullmatch(r"[a-z0-9_.@-]{3,64}", v):
            return v
    return "entra-" + re.sub(r"[^a-z0-9]", "", str(claims.get("oid") or claims.get("sub")).lower())[:24]


def finish(code, state):
    """Complete a sign-in. -> (user row, popup flag). Raises SsoError with a message that may be shown to the person."""
    cfg = settings()
    if not cfg:
        raise SsoError("Single sign-on is not configured on this server.")
    st = one("SELECT * FROM sso_states WHERE state=?", (state or "",))
    if st:
        db.db().execute("DELETE FROM sso_states WHERE state=?", (state,))      # one use only
    if not st or st["created"] < time.time() - STATE_MINUTES * 60:
        raise SsoError("This sign-in attempt is unknown or older than ten minutes. Start again.")
    if not code:
        raise SsoError("The identity provider returned no authorisation code.")
    form = dict(client_id=cfg["client_id"], grant_type="authorization_code", code=code, redirect_uri=cfg["redirect_uri"], code_verifier=st["verifier"])
    if cfg["client_secret"]:
        form["client_secret"] = cfg["client_secret"]
    tok = _get_json(discovery(cfg)["token_endpoint"], form)
    claims = verify_id_token(cfg, tok.get("id_token") or "", st["nonce"])
    ext = str(claims.get("oid") or claims.get("sub"))
    uname = _username(claims)
    name = str(claims.get("name") or uname)[:120]
    mail = next((v for v in (str(claims.get("email") or ""), str(claims.get("preferred_username") or "")) if re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", v)), None)
    mapped = role_from_claims(claims) if cfg["role_source"] == "entra" else None
    with db.tx():
        u = one("SELECT * FROM users WHERE external_id=?", (ext,)) or one("SELECT * FROM users WHERE username=?", (uname,))
        if u and not u["active"]:
            svc.audit(uname, "login_failed", "user", u["id"], "single sign-on: account deactivated in the tool")
            raise SsoError("Your account is deactivated in MEA Process Hub. Contact its administrator.")
        if cfg["role_source"] == "entra":
            role, dept = mapped or ((cfg["default_role"], None) if cfg["default_role"] != "none" else (None, None))
        else:
            role, dept = (u["role"], u["department_id"]) if u else ((cfg["default_role"], None) if cfg["default_role"] != "none" else (None, None))
        if not role:
            svc.audit(uname, "login_failed", "user", u["id"] if u else None, "single sign-on: no role assigned")
            raise SsoError("You are signed in to Microsoft, but no role in MEA Process Hub is assigned to you. Ask the administrator of the tool.")
        c = db.db()
        if u:
            c.execute("UPDATE users SET display_name=?, role=?, department_id=?, auth='entra', external_id=?, must_change=0, last_login=?, email=COALESCE(?, email), pw_hash=CASE WHEN auth='entra' THEN pw_hash ELSE ? END WHERE id=?",
                      (name, role, dept, ext, svc.now(), mail, svc.hash_password(secrets.token_urlsafe(32)), u["id"]))
            uid = u["id"]
        else:
            if one("SELECT 1 FROM users WHERE username=?", (uname,)):
                uname = (uname[:50] + "-" + ext[:8]).lower()
            uid = c.execute("INSERT INTO users(username,display_name,pw_hash,role,department_id,must_change,created_at,auth,external_id,last_login,email) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                            (uname, name, svc.hash_password(secrets.token_urlsafe(32)), role, dept, 0, svc.now(), "entra", ext, svc.now(), mail)).lastrowid
            svc.audit(uname, "user_created", "user", uid, f"first single sign-on, role {role}")
        user = one("SELECT * FROM users WHERE id=?", (uid,))
    return user, bool(st["popup"])


def handoff_create(user_id):
    """One-time code (90 seconds) with which the page inside a frame receives the session that a sign-in window obtained."""
    token = secrets.token_urlsafe(32)
    c = db.db()
    c.execute("DELETE FROM sso_handoffs WHERE created < ?", (time.time() - HANDOFF_SECONDS,))
    c.execute("INSERT INTO sso_handoffs(token,user_id,created) VALUES(?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), user_id, time.time()))
    return token


def handoff_redeem(token):
    key = hashlib.sha256((token or "").encode()).hexdigest()
    row = one("SELECT * FROM sso_handoffs WHERE token=?", (key,))
    if row:
        db.db().execute("DELETE FROM sso_handoffs WHERE token=?", (key,))
    if not row or row["created"] < time.time() - HANDOFF_SECONDS:
        raise svc.Forbidden("The sign-in window's answer is no longer valid. Sign in again.")
    return one("SELECT * FROM users WHERE id=? AND active=1", (row["user_id"],))


def status():
    """For the administration page: what is configured (never the secret) and whether the identity provider answers."""
    cfg = settings()
    if not cfg:
        missing = [k for k in ("MEA_HUB_PUBLIC_URL", "MEA_HUB_OIDC_TENANT", "MEA_HUB_OIDC_CLIENT_ID") if not (os.environ.get(k) or "").strip()]
        return dict(enabled=False, missing=missing)
    out = dict(enabled=True, authority=cfg["authority"], client_id=cfg["client_id"], redirect_uri=cfg["redirect_uri"], has_secret=bool(cfg["client_secret"]),
               role_source=cfg["role_source"], default_role=cfg["default_role"], only=cfg["only"], role_values=svc.ROLES)
    try:
        out["issuer"] = discovery(cfg)["issuer"]
        out["reachable"] = True
    except SsoError as e:
        out["reachable"], out["error"] = False, str(e)
    return out
