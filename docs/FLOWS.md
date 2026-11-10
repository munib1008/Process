# Flows: from the master canvas to one linked flow per process

## What was done
The file `source_documents/_canvas/dormakaba_All_Approved_process_Project_1.44_master_canvas.drawio` is **one page with
2,171 shapes** – every approved flow drawn side by side. It was turned into **one draw.io file per process**
(`source_documents/flows/<ID>_<Name>.drawio`, 71 flows + 1 file with the unassigned notes) by:

1. **Cutting** the canvas: shapes joined by connectors form a flow; the large title above it names it; loose notes are
   attached to the nearest flow. Nothing is dropped – whatever belongs to no flow is in `SC-RF-NT-01`.
2. **Mapping** each flow to a process in `source_documents/_canvas/canvas_mapping.json` (title → ID, name, department,
   "attach to the existing process" or "new process"). IDs come from the canvas's own overview blocks ("Ref: PP-M-VA-01");
   where the canvas gives none, a *provisional* ID is used and flagged.
3. **Revamping** to the dormakaba process-map style: blue title bar "Process Map – Name – ID", Arial, green *Yes* / red *No*
   connectors, green-ringed start, black-ringed end, grey "linked process" boxes, yellow notes.
   **The outline colour of a step is kept because it means the responsible role** (normalised to one colour per role).
4. Adding the **master legend** (shape key + all role colours; the roles used in that flow are bold) inside every flow.
5. **Rendering** each flow once with the real draw.io engine (`<same name>.png`), so Word/PDF exports look exactly like the editor.

## How a flow is linked to its process
* Importing a flow file **replaces the picture** on the existing process (the picture stays as diagram revision 1) or creates the process.
* The tool reads the diagram: **ordered activities, role per step (outline colour → legend), decisions with their branches,
  linked processes, SAP codes, checklist notes, and a scope sentence**. These fill the process page and the exports.
* While *"linked to the flowchart"* is on (Activities tab / editor), **every save of the diagram re-reads it** – change a step,
  recolour it, add a box, and the activity table, roles and SAP list of the draft follow. Published versions never change; the
  draft goes through review and approval as usual.
* A shape that names another process ("Ref S#: WL-S-QC-01") becomes a clickable link and a relationship.
* New flows created in Flow Studio start with the same master legend. Give a new box the outline colour of its role.

## Checks the tool runs (and records as findings)
* steps not connected to the start node (20 flows, mostly sheets with several variants or disconnected segments);
* steps with a neutral outline, i.e. no role (475 of 1,270 steps);
* flows mapped by inference (e.g. "QA/QC modified March 12, 2025" → KSA) and flows that exist twice on the canvas.
These are *structural* checks. Whether a flow is correct for the business must be confirmed by its owner.

## Regenerating
```bash
python -m mea_hub.canvas source_documents/_canvas/<canvas>.drawio source_documents/_canvas/canvas_mapping.json source_documents/flows
python run.py --no-browser &                       # needs drawio_webapp/ (python fetch_drawio.py)
node tools/render_flow_previews.js                 # real draw.io renders (needs Node + Playwright)
python tools/optimize_previews.py                  # 29 MB -> 7 MB
```
A canvas uploaded through **Import & Sources** without a mapping file is still split by its titles (provisional IDs, no role legend).
