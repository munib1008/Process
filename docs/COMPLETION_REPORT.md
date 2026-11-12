# Completion Report – MEA Process Hub 1.0

Status vocabulary: **Tested** = automated test and/or driven in a real browser; **Built, untested** = code exists, not verified;
**Partial**; **Not implemented**; **Blocked**. The platform is **not** declared complete against the full brief – see §3 and §4.

## 0. Latest round (flows per process, audit tool, add-options, branching, performance)
**State with all supplied files loaded:** 100 processes, and no department is empty; 76 have native, editable, linked flows
(72 files from the master canvas, plus the earlier native diagrams); 13 still carry pictures (the five project phases, which the canvas does not draw separately, and
duplicates from the "Approval" document). 1,270 activities were read from the flows, 795 with a role. 243 open findings (18 high), 6 resolved by decision.

**Process IDs (update of 2026-11-10).** By owner decision the four project phases that the Word documents all label `PM-M-IN-01` carry the IDs of the approved canvas:
Planning `PM-M-PL-01`, Execution `PM-M-EX-01`, Monitoring and Control `PM-M-MC-01`, Closing `PM-M-CL-01` (Initiation stays `PM-M-IN-01`). The decision is stored in
`source_documents/_canvas/canvas_mapping.json` (`id_corrections`), so a new installation imports with these IDs and an existing data folder is corrected at the next start.
The six related conflict findings are closed with the decision; the source chart ID remains visible on each process, and the Word documents themselves still show
`PM-M-IN-01` (to be corrected at their next revision). A controlled **Change ID** function (Document Controller / Administrator, reason mandatory, change-log entry,
diagram codes and links follow) is available on every process page for the remaining 49 provisional-ID findings. 30 automated tests pass. *Not done:* no bulk ID change
screen; old IDs are not redirected, so bookmarks to `…/PM-M-IN-01.2` no longer resolve.

**Review hosting from GitHub (2026-11-10).** `.devcontainer` + `tools/codespace_*.sh` start the app in GitHub Codespaces with an HTTPS address (`docs/HOSTING.md`).
Verified here: set-up and start scripts on a clean copy (import of all 82 files, address and one-time password printed), access through a forwarded host name,
`Secure` session cookie behind HTTPS, sign-in throttling. *Not verified:* an actual Codespace on github.com (cannot be created from this session) – in particular the
automatic start after the Codespace is created; the fallback is `bash tools/codespace_start.sh`. GitHub Pages is not possible (static files only).

**Creating new flows (2026-11-12).** *Done, tested:* text-to-flow builder on every process page and in Flow Studio (roles from the master legend, decisions with Yes/No branches,
notes, linked processes, SAP codes; standard frame and legend; linked to the document; previous flowchart kept as a revision); dormakaba shape library inside the editor (verified in the
real draw.io: 50 shapes with the 41 legend roles); flow check on the process page and after every save; templates now produce the same standard, readable flows.
All 72 imported flows read exactly as before (compared before/after). *Limits:* the builder draws one main path with side branches – loops back to an earlier step, parallel paths and
nested decisions on a branch are completed by hand in Flow Studio; steps appear in the activity table in reading order of the connectors, so a side branch can be numbered between two
main steps; a role that is not in the master legend cannot be given a colour (the legend itself is not editable in the app yet). *Windows EXE:* the GitHub build of the previous
commit succeeded including the smoke test (first-start import, sign-in, DOCX and PDF export) – first confirmation of the EXE on Windows.

| Item | Status |
|---|---|
| One flow file per process from the master canvas, master legend inside each, dormakaba style | **Done, tested** (30 automated tests; all 72 files open in draw.io and were rendered by it) |
| Flow linked to the document (activities/roles/SAP re-read on save) | **Done, tested** via API; the browser test opened flows but did not draw inside draw.io |
| Flow *correctness* for the business | **Not verified** – only structural checks (see `FLOWS.md`); 20 flows have steps not connected to the start |
| Mapping of flows to processes | **Partly inferred** – recorded in `canvas_mapping.json`; uncertain ones are findings (e.g. QA/QC "modified March 12, 2025" → KSA) |
| Add user / KPI / RACI / SAP / escalation / activities / department / relationship | **Done, browser-tested** (buttons on the tabs and in Governance; changes go into a draft) |
| Department branching (handbook tree, department page) | **Done** – branch = process type or business line; regional variants nested |
| Audit & Review (comments tied to versions, register, Excel) | **Done, tested** |
| Content writing | **Limited on purpose** – titles tidied, a factual scope sentence generated from each flow; objectives, RACI, KPIs are not invented |
| Performance | First-start import 26 s → 3.3 s; handbook PDF 35 s → 16.5 s; flow editor reopen 1.6 s → 0.8 s; images cached (392 KB → 10 KB on revisit). Page queries were already 6–13 ms, so there was no 100× to gain there |
| Windows EXE | Built by GitHub Actions on push; **result not seen from here** |

## 1. Input actually received
Only **5 of the 12** briefed source documents were supplied (Supply Chain v1.0, Finance & Accounts v0.1, Logistics & Warehouse v2.1, Approval Processes, MM Cleaning charter).
Missing: Purchase & Planning, Production, Project Management, Sales Support MENA, Sales Support Movable Wall, Service & Installation, Product Marketing & Management.
Five supplementary files were added later and imported: `WL-M-VS-01` Virtual Stock Request (native draw.io), `PMM-M-PR-01` SAP Pricing & Master Data Maintenance (native draw.io), the Level 0 / Level 1 Enterprise Architecture (native draw.io, 2 pages), and two versions of the Sales Support / MRP validation checklist (DOCX). The briefed documents are still missing for the departments below.
These departments show *"No documented processes – Documentation Required"* and are logged as high-severity gaps. **Nothing was invented.**

Key audit results on the 5 files (details: `SOURCE_RECONCILIATION_REPORT.md`): the *Finance & Accounts* file is Project Management content; the *Supply Chain* handbook contains only Finance-costing + Project processes (no E2E chapters);
the *Approval Processes* file is mostly Logistics; chart ID `PM-M-IN-01` is used for five different project phases; `WL-S-SC-01`, `WL-M-SP-01` and others are reused; `PP-` prefixes are attached to Logistics/Project processes;
`FI-M-PC-01` (Production Costing) has no flowchart. With all 10 files loaded: 45 process records. New-file findings: `PMM-M-PR-01` page name vs diagram title (`PMM-MM-PR-01`) disagree; `Validate Request` is parented to the Procurement lane but drawn in the PMM lane; the Virtual Stock diagram contains a "RECOMMENDED ADDITION (not in original process)" exception lane (imported but labelled [PROPOSED]); the two checklist files describe the same two checklists with different wording (64% / 82% text similarity – owner must pick one). Source-text typos (e.g. "ACCPETED?", "fo the request") are preserved as written.

## 2. Acceptance tests (brief §19)
| # | Scenario | Result |
|---|---|---|
| 1 | Initial migration | **Tested on 5/12 files**: all indexed, source mapping per process, uncertainties visible, originals byte-identical. Not met for the 7 missing files. |
| 2 | Edit existing process | **Tested** (pytest + browser, 4 roles): draft created, published untouched, diff, approve → new published version. |
| 3 | Edit diagram | **Tested in browser** (draw.io loads saved XML, edit saves revision 2, history kept); lock/conflict/XML safety **tested in pytest**. Not in pytest: GUI reopen of revision N. |
| 4 | Create new process | **Tested**: unique auto ID, appears in library, template diagram, workflow. |
| 5 | Cross-functional linking | **Tested**: links recorded, other processes unmodified, trace works. |
| 6 | Export single page | **Tested**: DOCX (real tables + picture), PDF, ZIP with `.drawio`. DOCX opened in LibreOffice and checked visually. Not opened in Microsoft Word. |
| 7 | Export complete handbook | **Generated** (39 processes: DOCX 3.8 MB, PDF 4.9 MB, HTML, ZIP) incl. from the frozen binary. DOCX page numbers need a Word field update; PDF has TOC + page numbers. Visual check of full 100+ page output was sampled, not exhaustive. |
| 8 | Approval and rollback | **Tested**: immutable history, new active version, restore = new draft, audit trail. |
| 9 | Permissions | **Tested**: viewer/editor/approver/admin (+scoped editor), 401/403, CSRF, Host check, draft text not searchable by viewers. |
| 10 | Backup and recovery | **Tested**: restore returns processes, versions, diagrams, assets; post-backup change removed; sessions invalidated. |

## 3. Feature status
**Tested** – login/roles/server-side authorisation/CSRF · DOCX import pipeline & findings · process library, types, regions · version workflow with separation of duties · immutability & rollback · version compare · draw.io embed (local copy), lease, optimistic conflict check, revisions, PNG preview capture · node metadata (process link/SAP/role…, searchable) · relationships, trace, orphan list · permission-aware search · dashboard counts · exports DOCX/PDF/HTML/ZIP + XLSX register with consistent snapshot hash and export log · backup/restore · PyInstaller build (Linux binary from the same spec: import + all exports).

**Built, untested** – Windows `.exe` build itself and the GitHub Actions workflow (written, not run: no Windows host here) · online draw.io fallback · rich-text toolbar across browsers (`execCommand`) · LAN mode.

**Partial**
* Native draw.io import: structure is extracted by rule (connector order, drawn lane, SAP-code pattern); decision criteria, RACI, KPIs and SLA owners are not in the diagrams. Multi-lane overlaps/nesting are read by drawn position. The server-rendered preview is approximate until the diagram is opened once in the editor (then replaced by draw.io's own PNG).
* Import review workspace: accept / edit / reassign department / mark conflict / request owner review. **No merge, no split** of processes.
* Imported flowcharts are *pictures*: wrapped as a locked reference layer in an editable draw.io page, flagged *Requires Functional Validation*. Automatic reconstruction of shapes was deliberately not attempted. The diagram XML for new/edited diagrams is native and editable.
* Diagram clicking: linked shapes navigate via the *Open related process* list / fallback SVG; the PNG preview itself is not clickable.
* Process map: simple department columns + edges; no expand/collapse, no "missing handover" analysis beyond orphans.
* RACI checks (missing A, multiple A, no R) – works on RACI data that owners enter; the sources contain none, so every process reports "No RACI".
* Review schedule: dates set at publish, overdue shown on dashboard; no reminder notifications.
* Branding: organisation name + export footer only (no logo, cover design, margins, typography editor, multiple templates).
* Comments: per-process comments and review notes; no inline/anchored comments or change-request objects (the revision workflow plays that role).
* Search: substring match (AND of terms) over an index; no ranking, no deep-link to the exact section.
* Export: PDF text uses a Latin font (Arabic/other scripts will not render); DOCX hyperlinks to the editable source are textual references, not live links; no page-range export, no landscape switching.

**Added after review (tested)** – ownership workbench, Excel register round-trip, task inbox, findings recommendations + bulk decisions, value-stream link suggestions (name-match; 18 links on the supplied data – suggestions only).

**Not implemented** – A4 print-layout preview mode · reusable content blocks transcluded across processes (single definition is enforced by relationships, not transclusion) · configurable business-approval matrices (sales order, credit, GP …) · e-mail/push notifications (an in-app task inbox exists) · SharePoint/OneDrive integration · AI-assisted drafting · Visio `.vsdx` output (draw.io chosen) · legacy `.doc` · per-document access rules beyond role+department · Docker deployment (replaced by the EXE) · real-time co-editing (lease + revision check instead).

**Blocked / needs input** – content for the 7 missing documents · master E2E value-stream chapters, department handovers, RACI, KPI definitions, SAP transaction lists and escalation ownership: absent in the sources, so left as *Documentation Required* · ID scheme and ownership decisions listed in the findings register.

## 4. Known risks and limits
* SQLite: single writer – fine for one PC / a small LAN team, not an enterprise-scale concurrent deployment.
* The draw.io upstream README calls its repository an evaluation edition: confirm production licensing/terms. With the online fallback host, diagram XML is sent to that host.
* PyInstaller EXEs can trigger antivirus heuristics; sign the executable.
* Heuristic classification (department, process type, duplicate similarity) is a *proposal*: every record starts Imported / Unverified and every conflict is surfaced rather than resolved.
* Rich text is sanitised server-side, but only against the allow-list implemented and tested here (script, handlers, `javascript:` links, foreign images are stripped).
