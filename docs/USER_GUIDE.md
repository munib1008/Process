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
**Import & Sources** (Controller/Admin): drop `.docx` files. The **Import Review Workspace** shows the original extraction (left) next to the generated record (right):
*Accept extraction*, *Edit*, *Reassign department*, *Mark conflict* (goes to the findings register), *Request owner review* (comment).
**Reports → Findings register** lists every conflict / gap / duplicate / uncertainty; record a decision on each.

## Export
**Export Center** or the DOCX / PDF buttons on a page: one process, selected processes, a department manual, or the complete handbook.
Choose whether unapproved processes are included (they are labelled and the cover shows *UNCONTROLLED DRAFT*).
DOCX contains editable Word text and tables; flowcharts are preview pictures – the editable source is the `.drawio` in the **ZIP** format.
In Word, right-click the Contents list → *Update Field* to add page numbers.
**Reports → Process inventory** downloads the Excel process register.
