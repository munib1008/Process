# User Guide

## Sign in and find a process
* **Master Handbook** – tree of departments → processes (left), process page (right). **Process Library** – filterable table. The top search box searches names, IDs, SAP transactions, KPI text, content and diagram labels.
* Status chips: *Imported / Unverified* (extracted automatically – check it), *Draft*, *Under Review*, *Pending Approval*, *Approved*, *Published*, *Superseded*.
* Viewers only see **published** processes.

## Edit a process (Editor / Department Owner / Controller)
1. Open the process → **Edit draft** (or *Edit (creates draft)* for a published process – the published version stays untouched).
2. Change fields, tables (RACI, SAP, KPI, escalation, activities) and rich-text sections. Changes **autosave** every ~2 seconds ("Saved hh:mm" at the top).
3. **Submit for review**: enter a change summary; choose whether it is a major change.
4. Reviewer: *Approve review* or *Request changes* (comment required). Approver: *Approve* or *Reject*. Controller: *Publish*.
   The author cannot review or approve their own revision (an admin can relax this for pilots).
5. **History** tab: all versions, who/when, **Compare** (before/after), and the change log. To roll back, open an old version → *Restore this version* – it creates a new draft that goes through the same approval.

## Edit a flowchart
Process page → **Edit diagram** (or *Create from template*). The real draw.io editor opens with the saved XML.
* Changes autosave as a new **revision**; a PNG preview is stored with each. If someone else holds the edit lease, or the diagram changed since you opened it, you get a clear message and **nothing is overwritten**.
* Imported flowcharts are a **locked reference picture** inside a draw.io page, flagged *Requires Functional Validation*: redraw the shapes on top, delete the reference, and have the owner confirm.
* Side panel: link a shape to a process (`process_ref`), a SAP transaction, role, approval, evidence… (stored separately from geometry, searchable).
* **Download .drawio / Export SVG** are available on the process page and in the editor. Use *Replace diagram* to import an existing `.drawio` file.

## Relationships and the process map
Process page → **Related** tab → choose a type (next, supports, parent, approval, triggers, exception, related) and a process ID.
**Governance → Process map** shows the graph and the orphan processes.

## Import and review
**Import & Sources** (Controller/Admin): drop `.docx` and `.drawio` files (native diagrams keep their editable XML; activities, lane owners and SAP codes are pre-filled and marked as auto-extracted – verify them). The **Import Review Workspace** shows the original extraction (left) next to the generated record (right):
*Accept extraction*, *Edit*, *Reassign department*, *Mark conflict* (goes to the findings register), *Request owner review* (comment).
**Reports → Findings register** lists every conflict / gap / duplicate / uncertainty; record a decision on each.

## Export
**Export Center** or the DOCX / PDF buttons on a page: one process, selected processes, a department manual, or the complete handbook.
Choose whether unapproved processes are included (they are labelled and the cover shows *UNCONTROLLED DRAFT*).
DOCX contains editable Word text and tables; flowcharts are preview pictures – the editable source is the `.drawio` in the **ZIP** format.
In Word, right-click the Contents list → *Update Field* to add page numbers.

**Flow pictures in documents.** DOCX, PDF and HTML show the **flow only** – the titled frame, its blue title bar and the master legend stay on the sheet in the tool.
A flow is printed at its drawn size and reduced only when it would not fit the page.
* **Show only a part:** open the flow in Flow Studio and drag **Export area (document picture)** from the *dormakaba MEA* shapes around the part you want (red dashed window).
  Only what lies inside goes into the document. Move, resize or delete the window at any time; it is saved with the flow revision.
* **Split a long flow:** draw several export areas. Each becomes its own picture, from top to bottom ("Part 1 of 3"); the text you type on an area becomes its caption.
* **Check before exporting:** *Document picture* on the process page, or *Preview* in the Flow Studio side panel, shows exactly what will be printed.
* **Long flows:** a flow much taller than a page is printed automatically in consecutive parts, cut between shapes. Draw your own export areas if you want other parts.
* **Legend:** the document ends with *Appendix B – Flowchart legend* (shape key and the role colours that occur in it).
* **Whole sheet with legend:** in the Export Center choose *Flow pictures ▸ Whole sheet*.
An export area is not a process step: it does not appear in the activity table or the flow check.
**Reports → Process inventory** downloads the Excel process register.
**SharePoint publication** (Export Center ▸ Format) produces a read-only copy of the library that SharePoint can show without a server: [SHAREPOINT_PUBLISHING.md](SHAREPOINT_PUBLISHING.md).

## Add things quickly
* **RACI, KPI, SAP, escalation, activities**: open the process → the tab → **+ Add / Edit**. Or Governance → RACI / KPIs / Escalation → **+ Add … for a process**. Changes are saved to a draft.
* **Users**: Administration → Users & roles → **+ Add user**. **Departments**: Administration → Settings → **+ Add department**.
* **Links between processes**: process → Related → **+ Add link**.

## Flows linked to the document
See `FLOWS.md`. In short: *Edit diagram*, change the flow, and the Activities tab (steps, role per step, SAP codes) follows on save while the link is on.
The role of a step is its outline colour – the master legend is inside every flow.

## Audit & Review
Process → **Audit & comments**: choose type (comment, question, observation, improvement, non-conformity), severity and the part concerned, and post.
Each item shows the version it was raised on, can be replied to, moved to *in progress*, **resolved with a mandatory note**, closed or reopened.
**Audit & Review** (left menu) is the register across all processes with filters and an Excel export; ⚑ marks items raised on an older version.
The History tab shows the version comment (change summary) of every revision and how many audit comments it has.

**Pin a comment to a step.** When the process has a native flow, the comment form offers **Flow step**: choose the step the comment is about.
The thread then shows *Step: …* next to the comment, so the editor knows exactly which shape is meant.

## Suggest a change (every signed-in user, including readers)
On every process page: **Suggest a change**. Say what should change and why, optionally choose the step concerned, and send.
- The suggestion is recorded against the version you are reading, with your name. The process itself does not change.
- The process owner, the department owner and the Document Controller get it as a task (*Dashboard ▸ My tasks*, and by e-mail if notifications are on).
  They answer it under *Audit & comments* (resolve with a note) and, if they agree, revise the process through the normal workflow.
- **Dashboard ▸ My change requests** shows your suggestions with their status and the owner's answer.
- A reader can have at most 25 unanswered suggestions at a time.

## Process landscape (find a process by where it sits in the business)
**Process Landscape** (left menu) goes from the enterprise maps down to the single process:
1. **Enterprise** – the Level 0 / Level 1 maps. Shapes marked blue open the process behind them.
2. **Department** – tile under the map, or a click on a shape: the department's overview maps, then all its processes by branch.
3. **Process** – click a shape or a name.

A shape is clickable when it is **linked to a process** in Flow Studio (select the shape ▸ *Linked process*). The page says how many shapes of a map are linked.
Readers see published maps only. **Full size** shows large maps unscaled.

## KPIs with actual values
*Governance ▸ KPIs* lists every KPI with its target, the latest actual, a rating and the trend of the last 12 periods.
- **Enter value**: period (month `2026-10`, quarter `2026-Q4` or year `2026`), value, optional note. Saving the same period again replaces the value; an empty value removes it.
- **Rating**: *target met / missed* needs a target with a direction – write `≥ 95 %`, `at least 95 %`, `max. 2 days`, `< 5 %`. A target such as `95 %` or free text is shown as *not rated*; the tool does not guess whether more or less is better.
- Actual values are operating data: they need no approval and do not create a document version. The KPI itself (name, definition, target) stays part of the controlled document.
- **Excel**: the register workbook has a sheet *KPI Actuals* (Process ID, KPI, Period, Value, Note). Fill it and load the workbook under *Governance ▸ Ownership & register* to enter many values at once.

## Reading statistics
*Reports ▸ Reading statistics* (not for readers): per process the number of different people who opened it in the last 30 and 90 days, and when it was last opened.
Use it to see whether published processes are used, and which documents nobody needs.
- Counted: one reading per person, process and day, in this tool. **Not counted:** reading in the SharePoint copy or in exported Word / PDF files.
- Readers are counted under a pseudonym; neither the report nor the database shows who opened what. Entries older than 400 days are deleted.

## On a phone or tablet
The same address works on a phone. The menu becomes a bar across the top (swipe sideways), the process list folds away while a process is open
(*Master Handbook ▾ browse all processes*), wide tables scroll sideways, and flow pictures can be opened full screen. Editing flows needs a computer.

## Create a new flow (Editor / Department Owner / Controller)
Open the process and choose **New flow from steps…** (for a process that still carries a picture: **Redraw from steps…**). Write one line per step:

| Line | Result |
|---|---|
| `Logistics: Create delivery (VL01N)` | Activity of a role of the master legend (outline colour = role). SAP codes are picked up. |
| `Credit limit sufficient?` | Decision. The next line is the **Yes** path. |
| `No: Credit Controller: Block the order` | The other answer of the decision above. Repeat `No:` for more steps on that branch; `No: End` finishes it; `No: Back to 2` (step number, or the start of the step's text) loops back to an earlier step. `Yes:` works the same way when the main path is the "No" path. |
| `Parallel: Finance: Issue invoice` | Two to four lines in a row that start with `Parallel:` run at the same time. They are drawn side by side between a split bar and a join bar. |
| `Note: Check incoterms on the PO` | Note or checklist attached to the step above. |
| `Ref: WL-M-OB-01 Outbound delivery` | Linked process (becomes a link when that process exists). |
| `Start: …` / `End: …` | Own wording for the start and end shapes (optional). |

- **Layout**: *Single column* (branches beside the main column) or *Swimlanes* (one lane per role, in the order the roles first appear; every step sits in the lane of its role, a step without a role stays in the lane of the step before it). Use swimlanes for cross-functional processes with up to about six roles.
- **Insert role…** lists the roles of the master legend; a role that is not in the legend is reported and the line is kept as plain text – nothing is guessed.
- **Start from template…** fills the box with the steps of a template; **Use the activity table** turns the existing activity table of the process into steps.
- The result is a standard flow: start/end, role colours, titled frame and the master legend. It opens in Flow Studio for refinement.
- With **Link the flow to the document** ticked, the activity table, the responsible roles and the SAP references are replaced by what the flow says and follow every later save.
- An existing flowchart is not lost: the new flow becomes the next revision; the old one stays in **Revision history**.
- A branch that you do not continue in the text is left open on purpose and listed by the flow check.

**In Flow Studio** the shape panel shows **dormakaba MEA**: start, end, decision, linked process, note, Yes/No connectors and one activity shape per role. Drag these instead of the generic
shapes so that the document can read role and step type. To change the role of a step, change its outline colour to the colour of the role in the legend, or replace it with the role's shape.
**Shape library** downloads the same shapes for draw.io Desktop (File ▸ Open Library).

**Flow check** (process page and Flow Studio, after every save) lists what a reviewer would raise: no start or end, steps that cannot be reached, steps without a next step,
decisions with one branch or unlabelled branches, activities without a role. It informs only – nothing is corrected automatically.

## Draft RACI and draft SAP work instructions (derived from the flows)
The tool can prepare two kinds of drafts. Both use **only** what the flows and the process records say; what the sources do not say stays empty or is written as an open point.

**Draft RACI** – *RACI* tab of a process ▸ **Create draft RACI from the flow** (Editor), or **Governance ▸ RACI ▸ Create draft RACI for all of them** (Document Controller).
| Column | Filled from |
|---|---|
| R | the role of the step (outline colour / lane in the flow) |
| A | the process owner recorded for the process; or the approver the step names ("approval from Logistics Head") – written as in the step |
| C | a party the step names for coordination ("coordinate with …", "consult …", "clarification from …") |
| I | the role of the next step (it receives the result) and recipients the step names ("notify …", "share … with …") |
A yellow note marks the table as *draft – not confirmed* in the tool and in exports. It disappears as soon as someone edits the RACI. To fill column A for a whole process,
record its owner (*Governance ▸ Ownership*) and derive the draft again. Published versions are never changed in bulk.

**Draft SAP work instructions** – **Governance ▸ RACI ▸ Create missing draft work instructions** (Document Controller). One draft (type *Work instruction*, status *Draft*)
per distinct step that names SAP or a transaction code. It contains the step, its role, the steps before and after it and the transaction if the step names one; the
transaction name is the SAP standard name. Screen sequence, entries, organisational data and checks are marked **[to be completed by the process owner]**.
Open a draft, choose **Edit draft**, complete it and send it for review like any other document. The second button extends this to steps that name an SAP *document*
(PO, SO, PGI, GRN, invoice …) without naming SAP – whether those steps are done in SAP is for the owners to confirm.
On the first start of a new installation both kinds of drafts are created automatically.

## Compare two versions
*History* tab of a process ▸ **Compare with shown**. The dialog lists what changed between the two versions:
* text fields word by word (removed words struck through in red, added words green);
* table rows added, removed and changed (activities, RACI, SAP references, KPIs, escalation);
* the flowchart: steps added, removed or reworded, role changes, connectors added or removed. If only the drawing moved, it says so.

## Periodic review
A published process gets a review date (default every 12 months; set per process under *Governance ▸ Ownership*).
**Governance ▸ Periodic review** lists all published processes with their date: overdue, due within 30 days, later.
* Nothing changed: **Confirm – no change**. The published version stays, the next date moves on, and the confirmation is logged with your name and remark.
  Allowed for the process owner, the department owner and the Document Controller.
* Something changed: open the process and revise it through the normal workflow; publishing sets the next date.
Owners are reminded 30 days before and when the date has passed (Dashboard, and by e-mail if notifications are switched on).

## Signed decisions
Approving a review, approving a revision, publishing it and confirming a periodic review are **signed**: the tool records who decided, when,
and a fingerprint of exactly the content and flowchart the decision was taken on.
- **History** tab ▸ *Signed decisions* lists them. *Content unchanged* means the version still has exactly the signed content.
- Word and PDF exports print the signed decisions of the exported version in the process header.
- If the administrator has switched on *ask for the password again*, you type your password at the moment of the decision. With company
  sign-in the tool instead requires that you signed in within the last 15 minutes; otherwise sign out and in again, then decide.
- Sending a revision back (request changes, reject) is logged but is not a signature.
This is a record for audits. It is not a qualified electronic signature in the legal sense.

## Exchange with other tools (BPMN)
**BPMN** on the process page downloads the flow in BPMN 2.0 for process platforms and modelling tools. What is and is not carried over: `docs/FLOWS.md`.

## Change a process ID (Document Controller / Administrator)
The former ID keeps working: links, bookmarks and the search by the old ID lead to the process under its new ID.

Open the process and choose **Change ID**. Enter the new ID and the reason (mandatory). The versions, flowchart, relationships, comments and change log stay with the
process; the diagram code (`DG-<ID>`) and links from other flows follow; the open "provisional ID" finding is closed with your reason. The chart ID stated in the source
document is kept for traceability. An ID that is already in use is refused. The old ID is not kept as an alias, so inform users who bookmarked it.
