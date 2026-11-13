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

## Updating an installation
1. Back up (*Administration ▸ Backup*), stop the program, replace the program files, keep the data folder, start again. Database changes are applied at start.
2. If the new version brings new or corrected source files, the console and **Import & Sources** say so. *Import them now* adds them to the existing library:
   a delivered flow becomes the next revision of the flowchart of its process (the earlier revision stays), nothing is published.
3. Draft RACI and draft SAP work instructions are created automatically only on the first start of a new data folder. In an existing library use *Governance ▸ RACI*.

## Master legend
*Administration ▸ Settings ▸ Master legend* lists the roles and their outline colours. They are used for new flows, the dormakaba MEA shapes in Flow Studio and the
legend page of exports. A flow that already exists keeps the legend drawn inside it until it is built again. Give each role its own colour where possible: the flow
reader recognises the role of a hand-drawn shape by its outline colour.

## Code signing (optional)
Add two repository secrets on GitHub – `CODESIGN_PFX_BASE64` (the certificate file, base64-encoded) and `CODESIGN_PFX_PASSWORD` – and the build signs
`MEA_Process_Hub.exe` before it is tested and packaged. Certificates kept on a hardware token cannot be exported this way; use the issuer's cloud signing service instead.
This step has not been run (no certificate was available).

## Hosting, SharePoint and Teams
One shared installation on an internal server: `docs/SERVER_AND_SHAREPOINT.md`. Teams channel tab: `docs/TEAMS.md`. Roadmap: `docs/ROADMAP.md`.

## Reading statistics and data protection (version 1.4.0)
Opening a process stores one row per person, process and day in the table `views`. The person is stored as a keyed hash (the key is the
configuration value `usage_salt`, created on first use), not as user ID or name; rows older than 400 days are deleted on the first day of a month.
The report under *Reports ▸ Reading statistics* shows counts only. Whoever holds the database **and** the key could still test whether a known
user opened a process – treat the database file as before (access for administrators only). If the works council or data protection officer
requires it, the counting can be stopped by deleting the rows (`DELETE FROM views`) and blocking the report for the roles concerned; ask before
rolling the tool out widely.

## Restore drill (version 1.5.0)
A backup is only worth something if it can be restored. *Administration ▸ Backup & restore ▸ Run restore drill now* makes a new backup,
unpacks it into a temporary folder – the live library is never touched – and checks: database integrity, references between tables, row
counts against the live library, every picture and source document present and identical, every document version and flowchart readable.
The result is shown, kept as "last drill" and written to the audit log; a reminder appears when the last successful drill is older than six months.

From the command line (for a scheduled task; exit code 1 when the check fails):
```
MEA_Process_Hub.exe --restore-drill
python run.py --restore-drill
```
What the drill does not prove: that the backup files are copied to another machine, and that a new server can be set up from them.
Do one full restore on a second machine before go-live and after every change of server (`docs/SERVER_AND_SHAREPOINT.md`).

## Signed decisions (version 1.5.0)
- Every review approval, approval, release and review confirmation writes a record into the table `signatures`: person, role, time, how the
  identity was proven, a SHA-256 fingerprint of the content and flowchart, and the hash of the record before it.
- *Administration ▸ Settings ▸ Ask for the password again…* makes local users type their password at each decision; single sign-on users
  must have signed in within the last 15 minutes. Wrong passwords count towards the sign-in lock (8 in 15 minutes).
- *Administration ▸ Audit log ▸ Check the register now* (also for the Document Controller through the address `/api/admin/signatures/verify`)
  recomputes the chain and compares every released version with its approved fingerprint. A change made directly in the database file is found.
- Limits: whoever can write to the database file **and** recompute the whole chain could forge it – keep file access to administrators and
  keep backups off the server. It is not a qualified electronic signature (eIDAS) and the tool is not validated for regulated records.

## Capacity (version 1.5.0)
Measured: 400 simultaneous users answered within 0.09 s on a 4-core machine (`docs/LOAD_TEST.md`). Before go-live run
`python tools/load_test.py --from-data <copy of your data folder>` on the real server. Exclude the data folder from on-access virus scanning
if IT allows it; scanning every database write can slow the tool considerably.
