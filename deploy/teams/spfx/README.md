# MEA Process Hub – SharePoint Framework web part (SharePoint page, Teams tab, Teams personal app)

A thin web part that shows MEA Process Hub, which runs on the company server, inside a frame.
**It contains no process data and none of the tool's program logic** – the server is still required
(see `docs/SERVER_AND_SHAREPOINT.md` and `docs/TEAMS.md` of the tool).

| | |
|---|---|
| SharePoint Framework | 1.24.1 (Heft build), generated with Microsoft's generator, then reduced to the frame |
| Node.js | 22.14 or newer 22.x (also 24.x / 26.x per `package.json`) |
| Supported hosts | `SharePointWebPart`, `SharePointFullPage`, `TeamsTab`, `TeamsPersonalApp` |
| Built package | `../MEA_Process_Hub_SharePoint_Teams.sppkg` (built from this source; not yet deployed to a tenant) |

## Two modes
1. **Published library (no server):** enter the SharePoint folder that holds `handbook.json` (the tool's *SharePoint publication* export). The reader in
   `src/viewer/viewer.ts` shows it. Guide: `docs/SHAREPOINT_PUBLISHING.md`.
2. **Live tool:** enter the https address of the tool on a company server; the web part frames it.

The reader is also built as a plain script for other web hosts (from this folder):
```bash
npx esbuild src/viewer/viewer.ts --bundle --format=iife --global-name=MEAProcessHubViewer --target=es2017 --minify --outfile=../../../mea_hub/static/viewer/viewer.js
```

## Build
```bash
npm install
npm run build
```
Result: `sharepoint/solution/mea-process-hub-tab.sppkg`.

## Settings of the web part (property pane; in Teams: *Settings* of the tab)
* **Address of MEA Process Hub** – the https address without a path, e.g. `https://processhub.example.com`. Anything else is rejected.
* **Opens with** – Dashboard, Master Handbook, Process Library, Departments, or another page such as `#/departments/LOG`.
* **Height** – on a SharePoint page; a Teams tab fills the window.

## Server side
The tool must allow the sites that frame it. For this web part that is the SharePoint tenant, and for a Teams tab additionally Teams:
```
MEA_HUB_EMBED_ORIGINS=teams,https://<tenant>.sharepoint.com
```

## To fix the address for everybody
Put the address into `properties.hubUrl` of `src/webparts/processHub/ProcessHubWebPart.manifest.json` and remove the address
field from `getPropertyPaneConfiguration()`; then page editors cannot point the frame at another site.
