"""Runtime paths and settings. Everything lives under one data directory."""
import os
import sys


def app_root() -> str:
    """Folder that holds the EXE (frozen) or the repository (source run)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_dir() -> str:
    """Folder containing bundled read-only resources (static UI)."""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", app_root())
    return os.path.dirname(os.path.abspath(__file__))


DATA_DIR = os.environ.get("MEA_HUB_DATA") or os.path.join(app_root(), "data")
DB_PATH = os.path.join(DATA_DIR, "mea_hub.sqlite3")
ASSET_DIR = os.path.join(DATA_DIR, "assets")
SOURCE_DIR = os.path.join(DATA_DIR, "sources")
EXPORT_DIR = os.path.join(DATA_DIR, "exports")
BACKUP_DIR = os.path.join(DATA_DIR, "backups")
STATIC_DIR = os.path.join(resource_dir(), "static")
# Optional self-hosted draw.io web app (created by fetch_drawio.py)
DRAWIO_DIR = os.environ.get("MEA_HUB_DRAWIO_DIR") or os.path.join(app_root(), "drawio_webapp")
# Fallback editor host (only used when no local copy exists). Diagram XML is
# exchanged with it via postMessage, so diagram content is visible to that host.
DRAWIO_REMOTE = os.environ.get("MEA_HUB_DRAWIO_URL", "https://embed.diagrams.net")

_ORIGIN = __import__("re").compile(r"https://(\*\.)?[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+(:\d{1,5})?|http://localhost(:\d{1,5})?")


def embed_origins():
    """Sites that may show the app inside a frame (e.g. a SharePoint page): MEA_HUB_EMBED_ORIGINS, comma-separated
    https origins such as https://contoso.sharepoint.com (a leading *. is allowed). Empty = the app refuses to be framed
    by other sites. http://localhost is accepted for testing only."""
    out = []
    for o in os.environ.get("MEA_HUB_EMBED_ORIGINS", "").split(","):
        o = o.strip().rstrip("/")
        if o and _ORIGIN.fullmatch(o) and o not in out:
            out.append(o)
    return out


MAX_UPLOAD_BYTES = 80 * 1024 * 1024
MAX_JSON_BYTES = 40 * 1024 * 1024
SESSION_HOURS = 12
LOCK_MINUTES = 5


def ensure_dirs():
    for d in (DATA_DIR, ASSET_DIR, SOURCE_DIR, EXPORT_DIR, BACKUP_DIR):
        os.makedirs(d, exist_ok=True)
