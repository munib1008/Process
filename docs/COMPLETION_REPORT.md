# Completion Report – MEA Process Hub 1.0

Status vocabulary: **Tested** = automated test and/or driven in a real browser; **Built, untested** = code exists, not verified;
**Partial**; **Not implemented**; **Blocked**. The platform is **not** declared complete against the full brief – see §3 and §4.

## 0. Latest round (flows per process, audit tool, add-options, branching, performance)
**State with all supplied files loaded (2026-11-12, first start of the current version):** 130 records – the 100 processes from the supplied documents and flows plus
30 generated draft SAP work instructions. 90 of the 100 processes have native, editable, linked flows; **none carries a picture any more**; 10 are reference chapters,
forms or records without a flow. 1,387 activities were read from the flows, 899 with a role. Draft RACI for 84 processes. 308 open findings (18 high), 6 resolved by decision.
Nothing is published: every record is *Imported / Unverified* or *Draft* until an owner takes it through review.

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

**Phase 4 – scale and assurance (2026-11-13, version 1.5.0).** *Done, tested (45 automated tests, a 10-step browser journey, load test):*
**load test** with a finding that mattered – answers went from 0.02 s to more than 10 s between 50 and 100 simultaneous users because
overlapping requests slowed each other down inside one Python process; fixed by passing short requests one at a time, bulk queries for list
pages and a longer connection queue; measured afterwards 400 simultaneous users within 0.09 s, no errors (`docs/LOAD_TEST.md`).
**Signed decisions** (review, approval, release, review confirmation) with content fingerprint, chained register, register check, optional
password at the decision, shown in History and exports. **Restore drill** into a temporary folder with integrity, count and file-hash checks,
logged, reminder after six months, also as a command. **Browser journey and accessibility check in the build** (five roles, nine pages, axe-core
WCAG 2.1 A/AA, all findings fixed: field names, contrast, link marking, keyboard access to scrolling tables). **Dependency scanning** (pinned
versions, pip-audit, Dependabot) and **release notes** enforced by the build.
*Not built, on purpose:* PostgreSQL and a second node – the measured limit was not the database. *Limits:* load test on one machine with 183
processes; the signature is an audit record, not a qualified electronic signature, and tamper-evident rather than tamper-proof; the automated
accessibility check does not replace a manual check with keyboard and screen reader; nothing of this was run on the company server.

**Phase 3, remaining items 4–10 (2026-11-13, version 1.4.0).** *Done, tested (43 automated tests, browser checks on desktop and an emulated phone):*
(4) **change requests from readers** – every signed-in user can send a suggestion on the version they read (optionally on one step); it becomes a task
for owner, department owner and Document Controller and is answered in the audit thread; the reader sees status and answer on the dashboard; at most 25
open suggestions per person. (9) **comments pinned to a flow step** – audit comments and suggestions can name one step of the flow of that version.
(8) **reading statistics** – one reading per person, process and day, readers stored under a keyed pseudonym, 400 days retention, report with
30/90-day readers and never-opened processes. (7) **KPI actuals** – values per month / quarter / year, rating against a target that states a direction,
trend, Excel sheet *KPI Actuals* out and in; actuals never create a document version. (6) **process landscape** – enterprise maps → department overview
maps → process, with the linked shapes clickable on the draw.io picture (positions verified against the drawing; a picture that does not match the
drawing gets no click areas). (10) **phone layout** – top menu bar, folding process list, sideways-scrolling tables. (5) **flow builder** – parallel
steps between split/join bars and a swimlane layout; both read back into the activity table, pass the flow check and export to BPMN (parallel gateways);
the 84 shipped flows still regenerate byte-identically. Also fixed: a slow page could overwrite the page opened after it.
*Limits, stated plainly:* the landscape is only as clickable as the maps are linked (measured on the supplied maps: Level 1 value stream 9 of 77 shapes,
Level 0 none, department overviews 0–8); no imported KPI has a target, so every KPI shows "not rated" until owners write targets with a direction;
reading in the SharePoint copy and in exports is not counted; the phone layout was checked in an emulated iPhone 13 only; swimlanes are background
shapes – dragging a step to another lane does not change its role; lanes are not exported as BPMN lanes. *Not built:* BPMN import.

**Phase 3, first three items (2026-11-12, version 1.3.0).** *Done, tested:* (1) **BPMN 2.0 export** (`mea_hub/bpmn.py`): events, tasks with the role as performer,
gateways with named flows, call activities, annotations, swimlanes as groups, diagram interchange with the layout; button on the process page and `.bpmn` files in the
Diagrams ZIP. All 90 supplied flows parse without warnings in the bpmn.io parser; two opened in the bpmn.io viewer. (2) **Version comparison**: word-level text changes,
table rows added / removed / changed, flow steps added / removed / reworded, role changes and connectors – steps are matched by wording first, so a redrawn flow compares
correctly. (3) **Periodic review**: *Governance ▸ Periodic review* with overdue / due-soon / later, and "Confirm – no change" for the owner, department owner or Document
Controller, logged, published version untouched. *Not built:* BPMN import. *Not tested:* import of the BPMN files into a commercial process platform.

**Notifications, security review pack, optional code signing (2026-11-12, version 1.2.0).** *Done, tested:* `mea_hub/notify.py` tells people by e-mail when work is
waiting for them (review, approval, publication, changes requested, review due or overdue, published), once per task, with a weekly or daily summary; optional post to one
Teams channel; per-person switch on the Dashboard; failures are recorded and retried; state and last messages under *Administration ▸ Notifications*. Automated test against
a stand-in mail server and webhook. `Strict-Transport-Security` is sent behind HTTPS. `docs/SECURITY_REVIEW_PACK.md` gives IT Security the controls, their tests and the
known gaps. *Built, not run:* the build signs the EXE when a certificate is supplied as repository secret (no certificate here). *Not tested:* the company mail relay and a
real Teams Workflows webhook.

**Single sign-on with Microsoft Entra ID (2026-11-12, version 1.1.0).** *Done, tested:* OpenID Connect authorization code flow with PKCE (`mea_hub/sso.py`): one-time
state, ID-token signature (RS256, key from the tenant's key set, verified in the tool without an extra library), issuer, audience, tenant, validity and nonce; roles and
department scope from Entra app roles at every sign-in, or kept in the tool; automatic creation of the user; local administrators as break-glass; passwords can be switched
off; framed pages sign in through a sign-in window with a one-time hand-over. Automated test against a stand-in identity provider (accepts genuine answers, refuses
forged, altered, expired, replayed, wrong-application and wrong-tenant ones) and a run in Chromium for both paths. *Not tested:* a real Entra tenant, Conditional Access,
guest users, the Teams desktop client (its sign-in windows are not handled yet). *Limits:* client secret only (no certificate), a session stays valid up to 12 hours
after the account is disabled in Entra, no automatic provisioning or removal of users. Guide: `docs/SSO_ENTRA.md`.

**Library hosted in SharePoint without a server (2026-11-12).** *Done, tested:* new export format *SharePoint publication* (`mea_hub/publish.py`): `handbook.json`,
flow pictures and text pictures in one folder; a reader (`deploy/teams/spfx/src/viewer/viewer.ts`) compiled into the SharePoint web part and into `viewer.js` for other
web hosts: department navigation, search, process pages with flows in parts, RACI, SAP, relations, draft banner. Tested in Chromium against a real export of 130
processes (navigation, search, pictures, links, phone width) and with a tampered file (no script runs). The web part now has two modes: published library from a
SharePoint folder, or frame around the live tool. `.sppkg` rebuilt with SPFx 1.24.1, lint clean. *Not tested:* installation on a tenant. Guide: `docs/SHAREPOINT_PUBLISHING.md`.

**Closing the open development points (2026-11-12).** *Done, tested:* (1) a former process ID still leads to the process after a controlled ID change; (2) a data
folder created by an older version is offered the new or corrected source files of the installed version (*Import & Sources ▸ Import them now*), which also brings the
editable flows to libraries that still show pictures; (3) exports carry the flowchart legend once (Appendix B: shape key and the role colours that occur), because the
flow pictures no longer contain it; (4) flows much taller than a page are printed in consecutive parts cut between shapes – flows printed below 60 % drop from nine to
five, the rest are very wide maps that need export areas or a landscape page; (5) the master legend is editable under *Administration ▸ Settings*; (6) the flow builder
accepts loops (`No: Back to 2`). *Still open, not development:* owner decisions (duplicates, canvas versions, accountable roles), tenant-side deployment and its tests.
The way forward is in `docs/ROADMAP.md`.

**Microsoft Teams channel tab (2026-11-12).** *Done, tested:* the tool can be displayed in a Teams channel tab from the hosted server. (1) Teams app package built by the
tool (*Administration ▸ Teams & SharePoint* or `tools/make_teams_app.py`), manifest valid against Microsoft's schemas 1.16–1.24; tab settings page `/teams/config.html` with
Microsoft's Teams JavaScript SDK 2.59 (served locally), exercised against a stand-in Teams host; `--embed-origins teams` allows the Teams hosts; sign-in and pages work when
framed by the origin `https://teams.microsoft.com` (Chromium). (2) The proposed SPFx route: frame web part with `TeamsTab` in `supportedHosts`, generated with Microsoft's
generator 1.24.1 and built here to `deploy/teams/MEA_Process_Hub_SharePoint_Teams.sppkg`. *Not possible, stated plainly:* the tool itself cannot be converted into an SPFx
package – it is a server program; both packages only display it. *Not tested:* upload to a real tenant, App Catalog, Teams desktop and mobile clients. Guide: `docs/TEAMS.md`.

**Internal server and SharePoint embedding (2026-11-12).** *Done, tested:* embedding is opt-in per site (`MEA_HUB_EMBED_ORIGINS` → `frame-ancestors`, cookie
`SameSite=None; Secure; Partitioned`, CSRF header still required), host allow-list and `--allow-hosts` / `--embed-origins` options, `/api/health`, *Full window* link inside a
frame; checked in Chromium with a page on another site (sign-in, library, nested draw.io editor; unlisted site refused). *Built, not run:* `deploy/` files for a Windows
service task, IIS, nginx and the SharePoint snippet – no Windows server, IIS, nginx or SharePoint tenant was available here. *Limits:* no single sign-on (own users), one
server with SQLite, Safari behaviour inside a frame unverified. Guide: `docs/SERVER_AND_SHAREPOINT.md`.

**Draft RACI and draft SAP work instructions (2026-11-12).** *Done, tested:* `mea_hub/drafts.py` derives a RACI for every process that has steps (84 processes, 1,068 rows
on a fresh import) and one draft work instruction per distinct step that names SAP or a transaction (30 drafts); both are created on first start, can be created later from
the RACI tab / Governance, are editable and go through the normal review. **What the drafts contain, measured:** R is filled in 899 rows (84 %), I in 346, **A in 4
rows and C in none** – the flows say who does a step and who receives it, they do not say who is accountable or consulted, and no value was assumed. Only 8 transaction
codes are written in the supplied flows (MM01, MM02, VK11, VK12, ME11, ME12, LS24, PP1); 25 of the 30 work instructions therefore have the transaction as an open point,
and all have screen sequence, entries and checks open. *Limits:* a further 96 distinct steps name an SAP document (PO, SO, PGI, GRN, invoice …) without naming SAP – drafts
for them are optional (second button) because "done in SAP" is an assumption; the library grows from 100 to 130 records; 5 processes get no RACI because they have no steps of their own (2 without a flow, 3 overviews that only link to other processes).

**No picture flows left (2026-11-12).** *Done, tested:* the 13 processes that still showed a flowchart picture now carry editable flows: five project phases cut as
sections out of the project E2E flow on the canvas, seven records that show the same steps as an existing canvas flow (twins), and one flow that is not on the canvas
(earlier Stock Correction version) redrawn step by step from its picture and flagged for confirmation. Fresh import: 100 processes as before, **90 with native editable
flows, 0 pictures**, 1,387 activities; 278 open findings (18 high) – the 35 additional ones document the replacements. The newer `SC-M-VS-01` file replaces the older
Level-1 page. Native files outside `flows/` now have draw.io-rendered pictures. *Limits:* a data folder that was created earlier keeps its pictures until the new flow
files are imported into it (Import & Sources) or the folder is started fresh; twins do not answer whether two records are one process; the redrawn flow reflects my
reading of the picture and needs the owner's check.

**Flow pictures in documents (2026-11-12).** *Done, tested:* DOCX / PDF / HTML show the flow without frame, title bar and master legend, at drawn size unless the page
forces a reduction (50 of the 72 supplied flows now print at 100 %); "Export area" shape in Flow Studio – only the part inside goes into the document, several areas give
several pictures; preview on the process page and in Flow Studio; *Whole sheet* remains selectable in the Export Center. Checked in the real draw.io editor (area dragged
from the shape panel, saved, picture identical to the window). *Limits:* nine large end-to-end maps are still reduced to 22–58 % because one page cannot hold them – they
need export areas drawn by their owners; the master legend is no longer printed with each flow, so readers of a flow-only document do not see the colour key unless
*Whole sheet* is chosen; data folders created before this version keep the old tall pictures of the three corrected purchasing flows until those flows are re-imported or saved once.

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
