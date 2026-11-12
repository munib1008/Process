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

## ID decisions recorded with the flows
A flow entry in `canvas_mapping.json` may carry `id_corrections`: `{"chart": "<chart ID in the documents>", "name": "<process name>", "to": "<new ID>", "reason": "…"}`.
They are written into the flow file, applied after import and re-checked at every start (idempotent; skipped when the target ID exists or the process is not found
exactly once). Current entries: the project phases Planning / Execution / Monitoring and Control / Closing → `PM-M-PL-01`, `PM-M-EX-01`, `PM-M-MC-01`, `PM-M-CL-01`.

## Document pictures (flow only, export areas)
`mea_hub/flowpic.py` cuts the document picture out of the sheet picture that draw.io rendered – nothing is redrawn, so the document cannot differ from the flow.
* No export area: the region inside the frame, below the title bar and clear of the master legend, with white margins trimmed.
* Export areas (style key `meaExport=1`, shape "Export area" in the dormakaba MEA library): one picture per area, in reading order, cut 3 units inside the dashed outline.
* Position on the sheet: Flow Studio stores the graph bounds reported by draw.io with every saved picture (`diagram_versions.preview_box`); for the supplied flow files the
  frame gives the position. If neither fits the picture's proportions the whole sheet is used and the preview says so – a picture is never cut blindly.
* Three purchasing flows (`PP-M-GS-01`, `PP-M-OC-01`, `PP-M-PC-01`) carried a "Yes" label about 2,700 units above their connector on the canvas, which made their sheet
  three times as tall. Labels further than 600 units from their connector now return to it (`canvas.STRAY_LABEL`).

## New flows (text-to-flow, shape library, flow check)
- `mea_hub/flowbuild.py` builds a flow from one line per step (`build`), offers the activity table or a template as starting text and produces the Flow Studio shape library
  (`library_entries`, one tagged activity per role of the master legend). Built flows use the same tags (`meaKind`, `meaRole`), frame and legend as the flows cut from the canvas,
  so `flowread` reads them the same way. Templates (`New process`, Flow Studio) go through the same builder.
- `flowread.read` additionally returns `checks` (no_start, no_end, unreached, dead_end, one_branch, unlabelled, no_role). When a tagged shape is recoloured to another legend colour,
  the colour wins over the old `meaRole` tag; roles that share a colour keep their tag.
- API: `POST /api/flows/build {process_id|title, steps, link}`, `GET /api/flows/steps?process_id=…|template=…`, `GET /api/flow-library`, `GET /api/flow-library.xml`.
- The library reaches the embedded editor through draw.io's `configure` message (inline data); URL libraries are not used because draw.io ignores them in offline mode.
- Flow check on the 72 imported flows today: 15 without any point; dead_end in 37 flows, no_role 33, unreached 20, unlabelled 18, one_branch 7, no_end 2, no_start 1.
  These are review points for the process owners, not errors of the import.
