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
**Reports → Process inventory** downloads the Excel process register.

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

## Change a process ID (Document Controller / Administrator)
Open the process and choose **Change ID**. Enter the new ID and the reason (mandatory). The versions, flowchart, relationships, comments and change log stay with the
process; the diagram code (`DG-<ID>`) and links from other flows follow; the open "provisional ID" finding is closed with your reason. The chart ID stated in the source
document is kept for traceability. An ID that is already in use is refused. The old ID is not kept as an alias, so inform users who bookmarked it.
