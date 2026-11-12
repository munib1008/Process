# MEA Process Hub in a Microsoft Teams channel

## The point to settle first
The proposed route (convert the page into an SPFx web part, package it as `.sppkg`, App Catalog, Sync to Teams) assumes a page made of
HTML, CSS and JavaScript only. **MEA Process Hub is not such a page.** It is a server program: the database, the Word import, the
review workflow, the exports and the audit log run on a server. None of that can be put into an SPFx package or into Teams.

What Teams (and SPFx) can do is **display** the tool from the server where it runs. So every route below needs the hosted
installation described in [SERVER_AND_SHAREPOINT.md](SERVER_AND_SHAREPOINT.md) first; the package only tells Teams the address.

## The simplest route for readers: publish to SharePoint
If people only need to **read** the library, no server and no Teams app are needed: the tool exports a read-only publication, a SharePoint
web part shows it, and the page is added to the channel with **+ ▸ SharePoint ▸ Pages**. See [SHAREPOINT_PUBLISHING.md](SHAREPOINT_PUBLISHING.md).
The routes below are for the live tool with editing.

## Three routes, ranked
| # | Route | Who must act | Effort | Use when |
|---|---|---|---|---|
| 1 | **Teams app package** (`.zip`, built by the tool) – a native channel tab | Teams administrator (or a user allowed to upload custom apps) | Lowest: one upload | You only need Teams. **Recommended.** |
| 2 | **SPFx web part** (`.sppkg`, your proposal) – same web part on SharePoint pages and as a Teams tab | SharePoint administrator (App Catalog) **and** Teams administrator | Higher: two admin steps, SPFx toolchain for changes | You want one package for SharePoint pages and Teams, or custom app upload is blocked but the App Catalog route is allowed |
| 3 | Teams **Website** tab | Nobody | None | Quick trial. In the current Teams client a Website tab usually opens the address in the browser instead of inside Teams [Medium Confidence] |

Routes 1 and 2 show exactly the same tool. Route 2 adds no function; it adds a second approval and a build chain.

## Before either route
1. The tool runs on a server and is reachable at an **https** address from the users' PCs (IIS or nginx in front, company certificate).
2. The server allows Teams to display it. Start it with `--embed-origins teams` (route 1) or
   `--embed-origins teams,https://<tenant>.sharepoint.com` (route 2). In `deploy\windows\start_server.bat`: `set "MEA_HUB_EMBED_ORIGINS=teams"`.
   *Administration ▸ Teams & SharePoint* shows whether this is in effect.

## Route 1 – Teams app package
1. Open the tool at its https address as administrator ▸ **Administration ▸ Teams & SharePoint ▸ Download Teams app package**.
   (Without the browser: `python tools/make_teams_app.py --url https://processhub.example.com`.)
2. Teams ▸ **Apps ▸ Manage your apps ▸ Upload an app ▸ Upload a custom app** (for one team), or the Teams admin center ▸
   **Teams apps ▸ Manage apps ▸ Upload new app** (for the organisation). Custom app upload must be allowed by the Teams policies.
3. In the channel: **+ (Add a tab)** ▸ choose *MEA Process Hub* ▸ pick what the tab opens (Dashboard, Master Handbook, Process Library,
   one department such as `LOG`, or one process) ▸ **Save**.
4. Each person signs in once inside the tab with their MEA Process Hub user name.

The package holds `manifest.json` (channel / group-chat tab, personal tab, the server's host name as the only valid domain) and two icons.
Uploading the package again with a higher `--version` updates the app.

## Route 2 – SPFx web part (your six steps)
| Your step | Status here |
|---|---|
| 1. Convert the page into an SPFx web part | Done as a **frame** web part in `deploy/teams/spfx/` (SPFx 1.24.1). The tool itself stays on the server |
| 2. Enable Teams channel support (`"TeamsTab"` in `supportedHosts`) | Done: `SharePointWebPart`, `SharePointFullPage`, `TeamsTab`, `TeamsPersonalApp` |
| 3. Build and package | Done: `deploy/teams/MEA_Process_Hub_SharePoint_Teams.sppkg`, built here from that source, lint clean |
| 4. Deploy to the SharePoint App Catalog | For your SharePoint administrator: upload the `.sppkg`, **Deploy**, tick *Make this solution available to all sites* if wanted |
| 5. Make it available in Teams | For the administrator: select the package in the App Catalog ▸ **Add to Teams** (older view: *Sync to Teams*); the Teams administrator may have to allow the app |
| 6. Add it to the channel | Channel ▸ **+** ▸ choose the app ▸ **Save**, then open the tab's **Settings** and enter the https address of the tool |

Steps 4 to 6 need your tenant and could not be carried out here.

## What was tested, and what was not
| Check | Result |
|---|---|
| Teams manifest against Microsoft's manifest schemas 1.16, 1.17, 1.19, 1.24 | Valid |
| Tab settings page with Microsoft's Teams JavaScript SDK 2.59 against a stand-in Teams host (same messages as Teams: initialise, save, store address) | Works: validity is reported, the chosen address is stored, success is confirmed |
| Tool framed by the origin `https://teams.microsoft.com` in Chromium: sign-in and pages | Works |
| A site that is not on the allow-list | Refused by the browser |
| `.sppkg` build with SPFx 1.24.1 / Node 22 | Built; contains the web part with `TeamsTab` |
| Upload to a real Teams tenant, App Catalog deployment, Teams desktop client, Teams mobile | **Not tested** – no tenant available |

## Limits and risks
| Risk | Why it matters | Mitigation |
|---|---|---|
| Line-of-sight to the server | Teams loads the tool from the user's device. Outside the corporate network / VPN (typically Teams mobile) the tab stays empty | State it in the tab name or channel description; or publish the server through the company's application proxy |
| Sign-in | Without single sign-on the tool has its own users. With it ([SSO_ENTRA.md](SSO_ENTRA.md)) people use their Microsoft account, but the Teams desktop client may block the sign-in window | Configure single sign-on; in the Teams desktop client use *Full window ↗* or the SharePoint publication for readers |
| Browser rules for framed content | Inside Teams the tool is third-party content. The cookie is set so that Edge/Chrome (and the Teams desktop client, which uses the same engine) keep it [High Confidence]; other engines are untested | *Full window ↗* in the top bar opens the tool in the browser |
| One address per web part instance (route 2) | A page editor could enter another https address in the web part settings | Fix the address in the source (see `deploy/teams/spfx/README.md`) before deployment |
| Admin dependency | Custom app upload (route 1) and App Catalog (route 2) are often restricted | Ask the Teams / SharePoint administrators early; route 3 as a stop-gap |
| Not a Microsoft-store app, no vendor support | Internal custom app | Named owner in your organisation |

The Teams JavaScript library is served by the tool itself (`/teams/teams-js.min.js`, MIT licence). It tries to refresh its list of Teams
hosts from a Microsoft address; the tool's security policy does not allow that call, and the library then uses its built-in list.
