<img src="mea_hub/static/brand/dormakaba_logo.png" alt="dormakaba" height="28">

# MEA Process Hub

Local enterprise **process & document management** for dormakaba MEA. The application, not Word, is the source of
truth: processes, flowcharts (native draw.io XML), RACI, KPIs, escalation rules, approvals and revision history live in
one database, and the handbook is generated from it as **DOCX / PDF / HTML**.

Runs on one PC as a single **`MEA_Process_Hub.exe`** (no installation, no cloud, no database server).
Your documents never leave the machine unless you choose the online draw.io fallback (see below).

## Quick start (Windows)

1. Download `MEA_Process_Hub_win64_<version>.zip` from the repository's **Releases** page (or build it, see *Building the EXE*) and unzip it anywhere.
2. The repository's `source_documents/` folder (supplied `.docx` / `.drawio` files and the 72 per-process flows) is shipped inside the package and **imported automatically on the first start**, so the tool opens already populated. To add more later, drop files into **Import & Sources** (or into `source_documents` before a first start).
3. Double-click `MEA_Process_Hub.exe`. A console window opens and your browser goes to `http://127.0.0.1:8765/`.
4. First start prints a **one-time admin password** (also saved to `data\FIRST_RUN_ADMIN_PASSWORD.txt`). Sign in as `admin`; you must change it immediately.
5. Create users under **Administration → Users & roles**. Keep the console window open while using the app; close it to stop.

Everything the app stores is in the `data` folder next to the EXE (database, imported originals, images, exports, backups).

Options: `MEA_Process_Hub.exe --port 9000 --no-browser --demo-users` (one evaluation user per role, password `ChangeMe!123`), `--import a.docx b.docx`, `--backup`, `--reconcile-report report.md`. Binding to the network (`--host 0.0.0.0`) is possible for a trusted LAN but there is **no TLS**; the default is this PC only.

## What it does

| Area | Implemented |
|---|---|
| Import | **DOCX** → headings, paragraphs, tables (merged cells), images, chart IDs, "Responsible" lists, escalation tables, KPIs; checklist documents become controlled **forms**. **Native `.drawio`** (multi-page supported) → kept as editable XML, and activities (ordered by connectors), lane owners, SAP transaction codes, required-documents / SLA notes and "recommended addition" lanes (labelled *[PROPOSED]*) are extracted. Originals kept byte-for-byte. Process IDs, regions (UAE & EXP / KSA), duplicates, ID collisions, title-vs-content mismatches and missing flowcharts are detected and logged as **findings** (Source Audit Register). Imported content is *Imported / Unverified* – never auto-published. |
| Flows per process | A one-page **master canvas** (all approved flows side by side) is cut into **one draw.io file per process**, restyled to the dormakaba process-map look with the **master legend** inside each flow, and linked: activities, roles (outline colour), SAP codes and linked processes are read from the diagram and **re-read on every save**. See `docs/FLOWS.md`. |
| Process library | Departments, process types, countries, owners, parent/next/supports/approval/triggers/exception links, orphan detection, process map, upstream/downstream trace. |
| Editing | Structured form + rich-text sections (headings, lists, tables, links, callouts), autosave to a draft. |
| Flow Studio | Real **draw.io** in an iframe (embed JSON protocol), exclusive edit lease, optimistic revision check, revision history, PNG preview captured from draw.io on every save, templates, `.drawio` import/download, SVG export, per-shape business metadata (process link, SAP transaction, role, approval…). |
| Governance | Draft → Under review → Pending approval → Approved → Published → Superseded. Published versions are immutable; rollback = a new controlled draft; separation of duties; before/after comparison; audit log; review schedule dates; findings register with recorded decisions. |
| Export Center | DOCX (real Word text/tables, cover, document control, TOC, headers/footers, page numbers, flowchart preview, source references, revision appendix), PDF (A4, TOC with page numbers, repeating table headers), HTML, ZIP of editable `.drawio` + previews, Excel **process register**. Every export is built from one consistent snapshot, hashed and logged. |
| Ownership & data loading | Bulk-assign owners/reviewers per department; round-trip Excel register (Ownership, RACI, KPI sheets → loaded into *draft* revisions); "My tasks" inbox (reviews, approvals, publishing, overdue); decision workbench (recommended action per finding, bulk decisions with rationale); suggested handover links derived from the Level 1 value stream (flagged *suggested*, removable). |
| Audit & Review | Comments, questions, observations and non-conformities per process, tied to the **version they were raised on**, with severity, section, replies, mandatory resolution note, status history in the audit log, and an Excel register. |
| Admin | Users, 7 roles with server-side checks on every endpoint, CSRF protection, backup / restore, audit log. |

The UI and all exports use the dormakaba corporate identity – see `docs/BRANDING.md`.

Read `docs/COMPLETION_REPORT.md` for the honest status of every requirement (including what is **not** built yet) and
`docs/SOURCE_RECONCILIATION_REPORT.md` for what the importer found in the supplied documents.

## draw.io (flowchart editor)

* **Fully local (recommended):** run `python fetch_drawio.py` once (needs `git` and internet) – it downloads the Apache-2.0
  `jgraph/drawio` web app into `drawio_webapp/`, and the app serves it at `/drawio/`. The release ZIP built by GitHub Actions already includes it.
* **Fallback:** without that folder the app embeds `https://embed.diagrams.net`; diagram content is then exchanged with that host.
* The jgraph README describes the repository as an evaluation/test edition and points to separate production arrangements, and it has no real-time co-editing.
  **Review licence/production terms before relying on it**; the app compensates for the missing co-editing with its own lease and revision conflict checks.

## Building the EXE

A Windows `.exe` can only be produced on Windows. Two ways:

* **GitHub Actions (no Windows PC needed):** *Actions → Build Windows EXE → Run workflow*. Download the `MEA_Process_Hub_win64` artifact. To publish the package as a **GitHub Release** with a permanent download link, enter a release tag (for example `v1.0.1`) in the *Run workflow* dialog, or push a `v*` tag.
* **Locally on Windows:** install Python 3.11+ (and git), then run `build_exe.bat`. Result: `dist\MEA_Process_Hub\MEA_Process_Hub.exe` and a ZIP.

PyInstaller executables are sometimes flagged by antivirus; code-sign the EXE or ask IT to allow-list it. The same spec was built and
smoke-tested here as a Linux binary (import of the real documents + all exports).

## Run from source / tests

```bash
pip install -r requirements-dev.txt
python run.py                 # http://127.0.0.1:8765
python -m pytest tests -q     # 36 tests: import, workflow, immutability, permissions, CSRF, diagram locks, exports, backup/restore
```

## Architecture (deliberate deviations from the brief)

The brief proposed Next.js + PostgreSQL + Redis + Docker. The request here is a tool that runs locally from an EXE, so the
stack is a single-process Python app: stdlib HTTP server, **SQLite** (WAL), vanilla-JS UI (no build step), python-docx / reportlab / openpyxl for exports.
SQLite serialises writers – ideal for one PC or a small team on a LAN, not for hundreds of concurrent editors. The data model
(processes, versions, diagrams, mappings, findings, audit, exports) is relational and would port to PostgreSQL.
The editor is `contenteditable` (not Tiptap) to avoid a JS build chain.

## Run it from GitHub for a review (no installation)
Open the repository in **GitHub Codespaces** – the app installs, imports the source documents and starts by itself. Steps, sharing and limits: [docs/HOSTING.md](docs/HOSTING.md).

## Internal server and SharePoint
One shared installation behind IIS or nginx, optionally shown inside a SharePoint page (Embed web part): [docs/SERVER_AND_SHAREPOINT.md](docs/SERVER_AND_SHAREPOINT.md). Ready-made files are in `deploy/`.

## Microsoft Teams
Channel tab that shows the hosted tool: Teams app package from *Administration ▸ Teams & SharePoint*, or the SPFx web part in `deploy/teams/` (also for SharePoint pages). What the packages can and cannot do: [docs/TEAMS.md](docs/TEAMS.md).

## Roadmap
What is needed to turn the tool into an approved, trusted company platform – content first, then single sign-on, then depth: [docs/ROADMAP.md](docs/ROADMAP.md).
