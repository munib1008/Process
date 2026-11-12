"""Microsoft Teams app package for MEA Process Hub (a ZIP with manifest.json and two icons).

The package does not contain the tool. It tells Teams where the tool is hosted (the HTTPS address of your server) and adds
  - a channel / group-chat tab whose settings page (/teams/config.html) lets the team choose the start view, and
  - a personal tab that opens the dashboard.
The manifest was validated against Microsoft's manifest schemas 1.16, 1.17, 1.19 and 1.24."""
import io
import json
import re
import uuid
import zipfile
from urllib.parse import urlparse

BLUE = "#003594"
SCHEMA = "https://developer.microsoft.com/en-us/json-schemas/teams/v1.16/MicrosoftTeams.schema.json"


def _glyph(size, fg, bg):
    """Three process boxes joined by connectors. Colour icon: white on blue, 192 px. Outline icon: white on transparent, 32 px."""
    from PIL import Image, ImageDraw
    k = size / 32.0
    im = Image.new("RGBA", (size, size), bg)
    d = ImageDraw.Draw(im)
    w = max(1, round(1.6 * k))
    for x0, y0, x1, y1 in ((10, 5, 22, 10), (10, 13.5, 22, 18.5), (10, 22, 22, 27)):
        d.rectangle([x0 * k, y0 * k, x1 * k, y1 * k], outline=fg, width=w)
    for y0, y1 in ((10, 13.5), (18.5, 22)):
        d.line([16 * k, y0 * k, 16 * k, y1 * k], fill=fg, width=w)
    return im


def icons():
    c, o = io.BytesIO(), io.BytesIO()
    _glyph(192, "#FFFFFF", BLUE).save(c, "PNG")
    _glyph(32, "#FFFFFF", (0, 0, 0, 0)).save(o, "PNG")
    return c.getvalue(), o.getvalue()


def manifest(url, name="MEA Process Hub", developer="dormakaba MEA", app_id=None, version="1.0.0", privacy_url=None, terms_url=None):
    u = urlparse(url)
    if u.scheme != "https" or not u.hostname or u.path not in ("", "/") or u.query or u.fragment:
        raise ValueError("--url must be the https address of the tool without a path, e.g. https://processhub.example.com")
    base = f"https://{u.netloc}"
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("--version must look like 1.0.0")
    short = name.strip()[:30]
    return {
        "$schema": SCHEMA, "manifestVersion": "1.16", "version": version,
        "id": app_id or str(uuid.uuid5(uuid.NAMESPACE_URL, base + "/mea-process-hub")),      # stable for one address, so an update replaces the app
        "developer": {"name": developer.strip()[:32], "websiteUrl": base + "/teams/about.html",
                      "privacyUrl": privacy_url or base + "/teams/about.html", "termsOfUseUrl": terms_url or base + "/teams/about.html"},
        "name": {"short": short, "full": name.strip()[:100]},
        "description": {"short": "Process library, flowcharts, review and approval.",
                        "full": "MEA Process Hub is the process library of the region: process documents, editable flowcharts, RACI, review and approval, "
                                "audit comments and exports. This app shows the tool hosted on the company server; sign in with your MEA Process Hub user name."},
        "icons": {"color": "color.png", "outline": "outline.png"}, "accentColor": BLUE,
        "configurableTabs": [{"configurationUrl": base + "/teams/config.html", "canUpdateConfiguration": True, "scopes": ["team", "groupChat"]}],
        "staticTabs": [{"entityId": "mea-process-hub-home", "name": short, "contentUrl": base + "/#/dashboard", "websiteUrl": base + "/", "scopes": ["personal"]}],
        "permissions": [], "validDomains": [u.netloc]}


def build(url, **kw):
    color, outline = icons()
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest(url, **kw), indent=2))
        z.writestr("color.png", color)
        z.writestr("outline.png", outline)
    return bio.getvalue()
