# Host the process library inside SharePoint – no server

## What this is
SharePoint cannot run MEA Process Hub (the tool is a program with a database). SharePoint **can** hold and show a
**published, read-only copy** of the library. That is what this guide sets up:

```
Document controller's PC                         SharePoint Online (your tenant)
┌──────────────────────────┐   export + upload   ┌───────────────────────────────────────────┐
│ MEA Process Hub (the EXE)│ ──────────────────► │ Document library folder "processhub"      │
│ write, review, approve   │   "SharePoint       │   handbook.json  + flows/*.png            │
└──────────────────────────┘    publication"     │ Page with the web part "MEA Process Hub"  │──► readers, with their
                                                 │ (also as a Microsoft Teams tab)           │    Microsoft 365 sign-in
                                                 └───────────────────────────────────────────┘
```

| | In the tool (EXE) | In SharePoint |
|---|---|---|
| Who | Document controller, authors, reviewers, approvers | Every reader |
| What | Write, draw flows, review, approve, export | Browse, search, read, follow links between processes |
| Sign-in | The tool's own users | Microsoft 365 – nothing extra |
| Who may see it | Users created in the tool | Whoever has Read permission on the SharePoint library |
| Server needed | No (runs on the controller's PC) | No |

Nothing can be changed in SharePoint. A new export replaces the published copy.

## What you need
| Role | Needed for | How often |
|---|---|---|
| SharePoint administrator (App Catalog) | Part A: upload the package once | Once |
| Owner of a SharePoint site | Part B: library and page | Once |
| Document controller with MEA Process Hub 1.0.2 or later | Part C: publish | After each approval round |
| Files | `deploy/teams/MEA_Process_Hub_SharePoint_Teams.sppkg` from the program folder | |

## Part A – install the web part (SharePoint administrator, once)
1. Open the **SharePoint admin center ▸ More features ▸ Apps ▸ Open**. This is the tenant App Catalog.
2. **Apps for SharePoint ▸ Upload** ▸ choose `MEA_Process_Hub_SharePoint_Teams.sppkg`.
3. In the dialog choose **Enable this app and add it to all sites** (or *Only enable this app* and add it per site later) ▸ **Enable app**.
   The package asks for no API permissions. It contains the reader only; no process data.
4. Optional, for Teams: select the app in the list ▸ **Add to Teams**.

If your organisation uses a site-collection App Catalog instead, upload the package there; the rest is the same.

## Part B – library and page (site owner, once)
1. Choose or create a SharePoint site, for example **MEA Process Hub** (`/sites/MEAProcessHub`).
2. Create a document library for the published copy, for example **ProcessLibrary** (or use *Documents*).
3. Set permissions on the library: **Read** for the readers (a Microsoft 365 group or "Everyone except external users" –
   your decision), **Edit** for the document controller only. Whoever can edit this library can change what readers see.
4. Create a page: **New ▸ Page** ▸ a one-column, full-width section ▸ **+** ▸ search **MEA Process Hub** ▸ add the web part.
5. Click the pencil on the web part and fill **Folder that holds handbook.json** with the server-relative address of the folder that
   Part C will upload, for example

   ```
   /sites/MEAProcessHub/ProcessLibrary/processhub
   ```
   For the default library the address contains `Shared Documents`, not "Documents":
   `/sites/MEAProcessHub/Shared Documents/processhub`. To find it: open the folder in the library and copy the part of the browser
   address from `/sites/` to the folder name.
6. **Republish** the page. Until Part C is done it shows "could not be loaded" – that is expected.
7. Optional: make the page the site's home page (**Site settings ▸ Site contents ▸ Site Pages ▸ … ▸ Make homepage**).

## Part C – publish the library (document controller, each time)
1. In MEA Process Hub: **Export Center ▸ Format: SharePoint publication – read-only library, no server**.
2. Decide what goes out:
   * **Include unapproved processes** ticked: everything, marked *UNCONTROLLED DRAFT* (useful while the content is being reviewed).
   * Unticked: only published (approved) processes. Use this once the first processes are approved.
   * *Complete master handbook*, one department, or selected processes.
3. A ZIP is downloaded (`…_SharePoint.zip`). Unzip it. It contains the folder **processhub**.
4. Open the SharePoint library in the browser and **drag the folder `processhub` into it**. When SharePoint asks, choose **Replace** for existing files.
   SharePoint keeps earlier versions of `handbook.json` in its version history.
5. Open the page. The header of the reader shows the publication date and the snapshot number; they must match the export
   (*Export Center ▸ Recent exports*).

Size for orientation: 130 processes with 102 flow pictures are about 4.5 MB in 110 files.
`index.html` and `viewer.js` in the folder are only needed on other web hosts; SharePoint does not use them and they may be left out.

## Part D – Microsoft Teams (optional)
Two ways, both show the same page:
* **No administrator needed:** in the channel click **+ ▸ SharePoint ▸ Pages**, pick the page from Part B (or paste its link) ▸ **Save**.
* **As its own app:** after *Add to Teams* in Part A: channel **+ ▸ MEA Process Hub ▸ Save**, then open the tab's **Settings** and enter the
  same folder address as in Part B step 5.

## What readers get
* Departments and processes on the left, with the approval state of each process.
* Search across IDs, names, steps, roles and SAP transaction codes.
* Per process: objective, scope, responsible roles, the flow (long flows in consecutive parts), activity table, RACI, SAP references,
  KPIs, escalation, further text, related processes as links.
* A link to one process: add `#mph=<process ID>` to the page address, e.g. `…/SitePages/Process-Hub.aspx#mph=WL-M-IB-01`.
* A red banner when unapproved content is included.

## Routine
| When | Who | What |
|---|---|---|
| After each approval round, at least monthly | Document controller | Part C; note the snapshot number in the release record |
| When a process is withdrawn | Document controller | Export again; delete the old `processhub` folder before uploading so that no old pictures remain |
| Quarterly | Site owner | Check who has Read and Edit on the library |

## Security notes
* The published copy stays in your tenant. The reader loads `handbook.json` and pictures from the same SharePoint site and nothing else.
* Access is decided by SharePoint permissions on the library. The publication contains process content, role names and owner names;
  it contains no user accounts, passwords, comments, findings or audit log.
* The reader shows the text of the file as text and cleans formatted sections again (no scripts, no foreign pictures or frames), so a
  tampered file cannot run code in SharePoint. It still shows whatever content the file holds – keep Edit rights on the library narrow.
* The web part itself is installed by the SharePoint administrator and cannot be changed by site users.

## Limits
| Limit | Consequence |
|---|---|
| Read-only | Comments, change requests and approvals happen in the tool, not in SharePoint |
| As current as the last export | Publishing is a manual step; state the routine |
| One authoring installation | The controller's EXE (or the server installation) is the master; back it up (*Administration ▸ Backup*) |
| SharePoint search does not look inside the publication | Use the search box of the reader |
| Not yet installed on a tenant from here | The package was built with Microsoft's SharePoint Framework 1.24.1 and the reader was tested in a browser against a real export; Parts A, B and D could not be run without your tenant |

## Troubleshooting
| Symptom | Cause | Fix |
|---|---|---|
| Web part "MEA Process Hub" is not offered on the page | Package not enabled for this site | Part A step 3; or *Site contents ▸ New ▸ App* and add it |
| "could not be loaded … (HTTP 404)" | Folder address wrong, or folder not uploaded yet | Compare with the address of the folder in the library (Part B step 5) |
| "could not be loaded … (HTTP 403)" | The reader has no permission on the library | Give Read permission |
| Text appears, flow pictures do not | The `flows` sub-folder was not uploaded | Upload the whole `processhub` folder |
| Old content after an upload | Browser still shows the old page | Reload with Ctrl+F5; check the snapshot number in the footer |
| The web part settings reject the address | It must be a folder of this tenant, starting with `/sites/` (or `/teams/`) | Remove `https://…` of another tenant, query strings and `#` |

## Other ways to show the library
* The same `processhub` folder works on any web server or static web host (open `index.html`).
* The live tool with editing for many users: one installation on a company server, see [SERVER_AND_SHAREPOINT.md](SERVER_AND_SHAREPOINT.md) and [TEAMS.md](TEAMS.md).
