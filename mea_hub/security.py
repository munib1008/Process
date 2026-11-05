"""Password hashing, HTML sanitising, XML safety checks."""
import base64
import hashlib
import hmac
import os
import re
import secrets
from html import escape
from html.parser import HTMLParser

ITER = 200_000


def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, ITER)
    return f"pbkdf2${ITER}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, it, salt, dk = stored.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", pw.encode(), base64.b64decode(salt), int(it))
        return hmac.compare_digest(calc, base64.b64decode(dk))
    except Exception:
        return False


def new_token() -> str:
    return secrets.token_urlsafe(32)


# ---------------------------------------------------------------- HTML sanitiser
ALLOWED = {"p", "br", "b", "strong", "i", "em", "u", "ul", "ol", "li", "h3", "h4", "h5", "h6", "table", "thead",
           "tbody", "tr", "td", "th", "a", "span", "div", "sub", "sup", "hr", "blockquote", "img"}
VOID = {"br", "hr", "img"}
ALLOWED_ATTR = {"a": {"href"}, "img": {"src", "alt"}, "td": {"colspan", "rowspan"}, "th": {"colspan", "rowspan"}, "div": {"class"}}
ALLOWED_DIV_CLASS = {"callout", "pagebreak"}
SAFE_URL = re.compile(r"^(https?://|mailto:|#|/)", re.I)


class _San(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self.stack = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "iframe", "object", "embed"):
            self.skip += 1
            return
        if self.skip or tag not in ALLOWED:
            return
        if tag == "h1" or tag == "h2":
            tag = "h3"
        a = []
        for k, v in attrs:
            if k in ALLOWED_ATTR.get(tag, ()) and v is not None:
                if k == "href" and not SAFE_URL.match(v.strip()):
                    continue
                if k == "src" and not re.fullmatch(r"/api/assets/\d+", v.strip()):
                    continue
                if tag == "div" and k == "class" and v not in ALLOWED_DIV_CLASS:
                    continue
                if k in ("colspan", "rowspan") and not v.isdigit():
                    continue
                a.append(f' {k}="{escape(v, quote=True)}"')
        if tag == "a":
            a.append(' rel="noopener noreferrer" target="_blank"')
        self.out.append(f"<{tag}{''.join(a)}>")
        if tag not in VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in ("script", "style", "iframe", "object", "embed"):
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag in ("h1", "h2"):
            tag = "h3"
        if tag in self.stack:
            while self.stack:
                t = self.stack.pop()
                self.out.append(f"</{t}>")
                if t == tag:
                    break

    def handle_data(self, data):
        if not self.skip:
            self.out.append(escape(data, quote=False))

    def close(self):
        super().close()
        while self.stack:
            self.out.append(f"</{self.stack.pop()}>")


def sanitize_html(html: str) -> str:
    if not html:
        return ""
    p = _San()
    p.feed(html)
    p.close()
    return "".join(p.out)


def strip_tags(html: str) -> str:
    t = re.sub(r"<(br|/p|/li|/tr|/h\d|/div)\s*/?>", "\n", html or "", flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    from html import unescape
    return re.sub(r"[ \t]+", " ", unescape(t)).strip()


def unsafe_xml(data: bytes) -> bool:
    head = data[:200000].lower()
    return b"<!doctype" in head or b"<!entity" in head
