"""SQLite schema and connection helpers (one connection per thread)."""
import json
import sqlite3
import threading
from contextlib import contextmanager

from . import config

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, display_name TEXT NOT NULL,
  pw_hash TEXT NOT NULL, role TEXT NOT NULL, department_id INTEGER, active INTEGER NOT NULL DEFAULT 1,
  must_change INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(
  token TEXT PRIMARY KEY, csrf TEXT NOT NULL, user_id INTEGER NOT NULL REFERENCES users(id),
  created_at TEXT NOT NULL, expires_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS departments(
  id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL, name TEXT NOT NULL, sort INTEGER NOT NULL DEFAULT 0,
  description TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS sources(
  id INTEGER PRIMARY KEY, filename TEXT NOT NULL, title TEXT, version_text TEXT, sha256 TEXT NOT NULL,
  size INTEGER NOT NULL, stored_path TEXT NOT NULL, declared_dept TEXT, actual_dept TEXT,
  stats TEXT NOT NULL DEFAULT '{}', confidence TEXT, imported_at TEXT NOT NULL, imported_by TEXT);
CREATE TABLE IF NOT EXISTS assets(
  id INTEGER PRIMARY KEY, sha256 TEXT NOT NULL, mime TEXT NOT NULL, filename TEXT, size INTEGER NOT NULL,
  path TEXT NOT NULL, source_id INTEGER REFERENCES sources(id), role TEXT NOT NULL DEFAULT 'diagram',
  width INTEGER, height INTEGER);
CREATE INDEX IF NOT EXISTS ix_assets_sha ON assets(sha256);
CREATE TABLE IF NOT EXISTS processes(
  id INTEGER PRIMARY KEY, process_id TEXT UNIQUE NOT NULL, chart_id TEXT, name TEXT NOT NULL,
  department_id INTEGER REFERENCES departments(id), kind TEXT NOT NULL DEFAULT 'sop',
  category TEXT NOT NULL DEFAULT '', countries TEXT NOT NULL DEFAULT '', owner TEXT NOT NULL DEFAULT '',
  reviewer TEXT NOT NULL DEFAULT '', parent_id INTEGER REFERENCES processes(id), sort_order INTEGER NOT NULL DEFAULT 0,
  review_months INTEGER, last_review TEXT, next_review TEXT, validation TEXT NOT NULL DEFAULT 'unverified',
  origin TEXT NOT NULL DEFAULT 'imported', created_at TEXT NOT NULL, created_by TEXT);
CREATE TABLE IF NOT EXISTS process_versions(
  id INTEGER PRIMARY KEY, process_id INTEGER NOT NULL REFERENCES processes(id), version TEXT NOT NULL,
  major INTEGER NOT NULL, minor INTEGER NOT NULL, status TEXT NOT NULL, content TEXT NOT NULL,
  diagram_version_id INTEGER, change_summary TEXT NOT NULL DEFAULT '', author TEXT, basis_version_id INTEGER,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, submitted_at TEXT, reviewed_by TEXT, reviewed_at TEXT,
  approved_by TEXT, approved_at TEXT, published_at TEXT, review_note TEXT NOT NULL DEFAULT '');
CREATE INDEX IF NOT EXISTS ix_pv_proc ON process_versions(process_id, status);
CREATE TABLE IF NOT EXISTS diagrams(
  id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL, process_id INTEGER REFERENCES processes(id), title TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'process', lock_user TEXT, lock_expires TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS diagram_versions(
  id INTEGER PRIMARY KEY, diagram_id INTEGER NOT NULL REFERENCES diagrams(id), ver_no INTEGER NOT NULL,
  xml TEXT NOT NULL, sha256 TEXT NOT NULL, preview_asset_id INTEGER REFERENCES assets(id), origin TEXT NOT NULL,
  validation TEXT NOT NULL DEFAULT 'ok', note TEXT NOT NULL DEFAULT '', author TEXT, created_at TEXT NOT NULL,
  UNIQUE(diagram_id, ver_no));
CREATE TABLE IF NOT EXISTS diagram_nodes(
  id INTEGER PRIMARY KEY, diagram_version_id INTEGER NOT NULL REFERENCES diagram_versions(id), node_id TEXT NOT NULL,
  label TEXT, meta TEXT NOT NULL DEFAULT '{}', UNIQUE(diagram_version_id, node_id));
CREATE TABLE IF NOT EXISTS relationships(
  id INTEGER PRIMARY KEY, from_id INTEGER NOT NULL REFERENCES processes(id), to_id INTEGER NOT NULL REFERENCES processes(id),
  rel_type TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', inferred INTEGER NOT NULL DEFAULT 0,
  UNIQUE(from_id, to_id, rel_type));
CREATE TABLE IF NOT EXISTS mappings(
  id INTEGER PRIMARY KEY, process_id INTEGER NOT NULL REFERENCES processes(id), source_id INTEGER NOT NULL REFERENCES sources(id),
  heading TEXT, chart_id TEXT, role TEXT NOT NULL, similarity REAL, location TEXT, excerpt_html TEXT NOT NULL DEFAULT '',
  asset_ids TEXT NOT NULL DEFAULT '[]');
CREATE TABLE IF NOT EXISTS findings(
  id INTEGER PRIMARY KEY, kind TEXT NOT NULL, severity TEXT NOT NULL, source_id INTEGER REFERENCES sources(id),
  process_id INTEGER REFERENCES processes(id), title TEXT NOT NULL, detail TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open',
  decision TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, resolved_by TEXT);
CREATE TABLE IF NOT EXISTS comments(
  id INTEGER PRIMARY KEY, process_id INTEGER NOT NULL REFERENCES processes(id), version_id INTEGER, author TEXT NOT NULL,
  body TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'comment', resolved INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit(
  id INTEGER PRIMARY KEY, ts TEXT NOT NULL, username TEXT, action TEXT NOT NULL, entity TEXT, entity_id TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS exports(
  id INTEGER PRIMARY KEY, ts TEXT NOT NULL, username TEXT, scope TEXT NOT NULL, fmt TEXT NOT NULL, status TEXT NOT NULL,
  filename TEXT, sha256 TEXT, size INTEGER, snapshot_hash TEXT, snapshot TEXT, error TEXT);
CREATE TABLE IF NOT EXISTS config(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS search_index(process_id INTEGER PRIMARY KEY REFERENCES processes(id), body TEXT NOT NULL, body_pub TEXT NOT NULL DEFAULT '');
"""

_local = threading.local()


def connect(path=None):
    c = sqlite3.connect(path or config.DB_PATH, timeout=30, isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    c.execute("PRAGMA journal_mode = WAL")
    return c


def db():
    c = getattr(_local, "conn", None)
    if c is None:
        c = connect()
        _local.conn = c
    return c


def close_all_for_thread():
    c = getattr(_local, "conn", None)
    if c is not None:
        c.close()
        _local.conn = None


def init():
    config.ensure_dirs()
    c = db()
    c.executescript(SCHEMA)


@contextmanager
def tx():
    """Transactional write block (BEGIN IMMEDIATE ... COMMIT / ROLLBACK)."""
    c = db()
    c.execute("BEGIN IMMEDIATE")
    try:
        yield c
        c.execute("COMMIT")
    except BaseException:
        c.execute("ROLLBACK")
        raise


def q(sql, args=()):
    return [dict(r) for r in db().execute(sql, args).fetchall()]


def one(sql, args=()):
    r = db().execute(sql, args).fetchone()
    return dict(r) if r else None


def jloads(s, default=None):
    try:
        return json.loads(s) if s else default
    except ValueError:
        return default
