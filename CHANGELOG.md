# Release notes – MEA Process Hub

Every release has a section here; the build publishes the section of a version as the text of its GitHub Release and
refuses to publish a version that has none. Newest first.

## 1.5.0 – 2026-11-13
Phase 4: scale and assurance.
- **Many people at once.** A load test (`tools/load_test.py`) showed that answers slowed from 20 ms to more than 10 s between 50 and 100
  simultaneous users. Cause: several requests working on the database at the same time slow each other down inside one Python process.
  Short requests now pass one at a time, long jobs (exports, imports, sign-in) stay outside, list pages use a few bulk queries instead of one
  per process. Measured after the change on the same machine: 400 simultaneous users, 95 % of all actions within 0.09 s, no errors.
  A database server (PostgreSQL) is therefore not needed for capacity; see `docs/LOAD_TEST.md`.
- **Signed decisions.** Every review, approval, release and review confirmation is recorded with the person, the time and a SHA-256
  fingerprint of the content and flowchart. Records are chained; *Administration ▸ Audit log ▸ Check the register now* proves that nothing was
  removed or altered and that every released version still has the approved content. Optional setting: ask for the password again at each
  decision (single sign-on users: sign-in within the last 15 minutes). Shown on the History tab and in Word / PDF exports.
- **Restore drill.** *Administration ▸ Backup & restore ▸ Run restore drill now* (or `run.py --restore-drill`) restores a new backup into a
  temporary folder and checks it without touching the live library; the result is logged and a reminder appears after six months.
- **Accessibility.** The main pages pass the automated WCAG 2.1 A/AA check (axe-core): form fields are named for screen readers, red text has
  sufficient contrast, links in text are underlined, scrolling tables can be reached by keyboard, keyboard focus is visible.
- **Build.** The build now runs a browser journey through the real pages with five roles, the accessibility check, a load test and a scan of
  the dependencies for known vulnerabilities before the Windows package is made. Dependencies are pinned (`requirements-lock.txt`) and watched
  by Dependabot.
- Not built: PostgreSQL / a second server node (not needed at the measured capacity), BPMN import.

## 1.4.0 – 2026-11-13
Phase 3 completed.
- Readers can suggest a change on the version they read, optionally on one step; owner, department owner and Document Controller get a task.
- Audit comments can be pinned to a step of the flow.
- Process landscape: enterprise maps → department overview maps → process; linked shapes are clickable on the picture.
- KPI actuals per month, quarter or year with rating against a target that states a direction, trend, Excel in and out.
- Reading statistics (counts only, readers stored under a pseudonym).
- Layout for phones and tablets.
- Flow builder: parallel steps between split and join bars, swimlane layout.
- Fixed: a slow page could overwrite the page opened after it.

## 1.3.0 – 2026-11-12
- BPMN 2.0 export of every flow (process page and Diagrams ZIP).
- Version comparison: word-level text differences, table rows, flow steps, roles and connectors.
- Periodic review: overdue / due list and "Confirm – no change".

## 1.2.0 – 2026-11-12
- Notifications by e-mail and Teams about waiting work, with a daily digest option.
- Security review pack for IT (`docs/SECURITY_REVIEW_PACK.md`).
- The build signs the EXE when a code-signing certificate is provided.

## 1.1.0 – 2026-11-12
- Single sign-on with Microsoft Entra ID (OpenID Connect); roles from app roles; sign-in inside Teams and SharePoint frames.

## 1.0.2 – 2026-11-12
- Read-only publication of the library into SharePoint (no server needed for readers), with a SharePoint / Teams web part.

## 1.0.1 – 2026-11-12
- Hosting on an internal server behind IIS or nginx, embedding in SharePoint and in a Teams tab.
- Master legend editor, import of newly delivered source files, roadmap.

## 1.0.0 – 2026-11-12
First packaged release.
- Import of the Word handbooks and the draw.io master canvas into structured, linked processes; 90 editable flows.
- Workflow: draft → review → approval → publication with separation of duties and immutable published versions.
- Flow Studio (draw.io), flow builder from text, flow check, document pictures and export areas.
- Draft RACI per process and draft SAP work instructions derived from the flows.
- Exports: Word, PDF, HTML, Excel register, Diagrams ZIP. Backup and restore. Windows EXE.
