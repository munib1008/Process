# Administration Guide

## Installation and data
* Unzip anywhere (a normal user folder is fine). All state is in `data\`. **Back it up** (Administration → Backup, or `MEA_Process_Hub.exe --backup`) – a backup ZIP holds the database, imported originals and images.
* **Restore**: Administration → Backup & restore (replaces everything, signs all users out), or unzip a backup over `data\` while the app is stopped.
* Environment variables: `MEA_HUB_DATA` (data folder), `MEA_HUB_DRAWIO_DIR` (draw.io web app folder), `MEA_HUB_DRAWIO_URL` (online fallback host), `MEA_HUB_ALLOW_HOSTS` (extra Host headers for LAN use).

## First run and users
* One-time admin password → `data\FIRST_RUN_ADMIN_PASSWORD.txt` (delete after use). New users get a temporary password and must change it at first login.
* Roles: `admin` (everything), `controller` (import, accept imports, edit, review, publish, findings), `dept_owner` / `editor` (edit, submit; scoped to a department if one is set), `reviewer`, `approver`, `viewer` (published only).
  Approval and publishing are separate rights by design (approver ≠ publisher). Settings → *Author may review/approve own revision* = No by default.

## draw.io
`python fetch_drawio.py` → `drawio_webapp\` next to the EXE. Confirm jgraph's licence and production terms with legal/IT before production use;
the app treats the editor as an untrusted iframe (only messages from its origin and window are accepted; diagram XML is validated server-side: no DOCTYPE/ENTITY, must be `<mxfile>`/`<mxGraphModel>`, compressed pages decoded safely).

## Security notes
* Binds to `127.0.0.1` only by default; Host-header check blocks DNS-rebinding. Session cookie is HttpOnly + SameSite=Strict; every state-changing call needs a per-session CSRF token. CSP forbids inline script. Rich text is sanitised on the server (allow-list); imported DOCX external links are kept as text and never fetched.
* LAN use (`--host 0.0.0.0`) has **no TLS**: put it behind a reverse proxy with HTTPS or keep it local.
* Passwords: PBKDF2-SHA256, 200k iterations. There is no password-reset email; an admin resets passwords.

## Operations
* Logs: console window; errors in `data\error.log`. Audit trail: Administration → Audit log (also Governance → Revision history for process events).
* Upgrade: replace the EXE, keep `data\`. The schema is created with `IF NOT EXISTS`; take a backup first.
* Rebuild/CI: see README *Building the EXE*.
