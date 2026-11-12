# Hosting on an internal server and showing the tool inside SharePoint

MEA Process Hub is a server program with its own database. SharePoint cannot run it, and neither can a static host
(GitHub Pages, Azure Static Web Apps, a storage static website). The working arrangement is therefore:

```
user's browser ──HTTPS──► IIS or nginx on a company server ──► MEA Process Hub (127.0.0.1:8765) ──► data folder
        ▲
        └── SharePoint page with an Embed web part pointing at the same HTTPS address (optional)
```

One installation, one data folder: everyone works on the same processes, approvals and audit comments.
This is the difference to handing out the EXE, where every copy has its own data.

## What was built for this, and what was tested
| Item | Status |
|---|---|
| App reachable through a reverse proxy: host allow-list (`MEA_HUB_ALLOW_HOSTS`), `Secure` cookie behind HTTPS, `/api/health` probe | Done, automated test |
| Embedding is **off by default**; `MEA_HUB_EMBED_ORIGINS` names the sites that may frame the tool (`Content-Security-Policy: frame-ancestors`, no `X-Frame-Options`) | Done, automated test |
| Sign-in inside the frame: session cookie `SameSite=None; Secure; Partitioned`; changes still need the CSRF header | Done, automated test; checked in Chromium with a stand-in page on another site (sign-in, library, nested draw.io editor; a site not on the list is refused) |
| *Full window ↗* link in the top bar when the tool runs inside a frame | Done |
| `deploy/windows/start_server.bat`, `register_startup_task.ps1`, `deploy/iis/web.config`, `deploy/nginx/mea-process-hub.conf`, `deploy/sharepoint/embed_snippet.html` | Written; **not run** on a Windows server, IIS, nginx or a SharePoint tenant from here |

## 1. Server (Windows Server + IIS; nginx is the same idea)
1. Unzip the release package to the server, e.g. `D:\MEAProcessHub`. Choose a data folder on a drive that is backed up.
2. Edit `deploy\windows\start_server.bat`:
   * `MEA_HUB_DATA` – the data folder
   * `MEA_HUB_ALLOW_HOSTS` – the host name users will type, e.g. `processhub.example.com`
   * `MEA_HUB_EMBED_ORIGINS` – leave empty for now
3. Run it once in a console. The first start imports the source documents and prints the one-time `admin` password
   (also in `<data folder>\FIRST_RUN_ADMIN_PASSWORD.txt`). Check `http://127.0.0.1:8765/api/health` on the server.
4. Make it start with the server: `.\register_startup_task.ps1 -Account "DOMAIN\svc_processhub"` (elevated PowerShell).
   Use a service account that has Modify rights on the data folder and nothing else.
5. Publish it with IIS: install *URL Rewrite* and *Application Request Routing*, enable the ARR proxy, allow the server
   variable `HTTP_X_FORWARDED_PROTO`, create a site with an **HTTPS binding and the company certificate**, and put
   `deploy\iis\web.config` in its folder. (nginx: `deploy/nginx/mea-process-hub.conf`.)
6. Firewall: open 443 to the user network only. Port 8765 stays closed – the app listens on `127.0.0.1`.
7. From a user PC open `https://processhub.example.com/`, sign in, create the users.

The app has no TLS of its own. Do not expose port 8765 to the network; always put the HTTPS proxy in front.

## 2. SharePoint page
1. On the server add the SharePoint address to `MEA_HUB_EMBED_ORIGINS`, e.g. `https://contoso.sharepoint.com`, and restart the task.
   Only `https://` origins are accepted (host name only, no path; `https://*.sharepoint.com` is allowed but wider than needed).
2. In SharePoint, a site owner allows the domain for embedding: **Site settings ▸ HTML Field Security ▸ allow iframes from
   `processhub.example.com`**. Without this the Embed web part refuses the address.
3. Edit the page ▸ add a one-column (full-width) section ▸ **Embed** web part ▸ paste the address or the snippet from
   `deploy/sharepoint/embed_snippet.html`.
4. Users sign in inside the frame with their MEA Process Hub user name. **There is no single sign-on with Microsoft 365** –
   the tool has its own users and roles.

### Browser behaviour inside the frame
The tool is a "third party" inside a SharePoint page, so the browser applies its third-party cookie rules.
| Browser | Expected | Confidence |
|---|---|---|
| Edge / Chrome (current versions) | Works; the cookie is kept per embedding site (`Partitioned`) even when third-party cookies are blocked | High – checked in Chromium here |
| Firefox | Works; Firefox partitions third-party storage by default | Medium – not tested here |
| Safari | May refuse the cookie depending on version and settings | Low – not tested here |
If sign-in does not hold inside the frame, the user clicks **Full window ↗** (or opens the address directly); nothing is lost.
A user signed in through the frame is not automatically signed in when opening the tool in its own tab, and the other way round.

For a Microsoft Teams channel tab see [TEAMS.md](TEAMS.md).

## 3. Operation
* **Backup:** *Administration ▸ Backup* creates a ZIP of the database and files; additionally include the data folder in the server backup.
* **Update:** stop the task, replace the program files (not the data folder), start the task. Database changes are applied automatically at start.
* **Monitoring:** `GET /api/health` answers `{"ok": true}` without a session.
* **Log:** `<data folder>\server.log`; application errors in `<data folder>\error.log`.

## 4. Limits and risks – decide with IT before go-live
| Risk | Why it matters | Mitigation |
|---|---|---|
| Own user names and passwords, no Entra ID / SSO, no MFA | Accounts must be created, disabled and reset in the tool; a leaver is not removed automatically | Keep the site reachable from the corporate network only; name an account owner; review users quarterly |
| One server, SQLite database | No fail-over; suitable for tens of concurrent users, not hundreds of simultaneous editors | Server backup; restore test; accept a short outage for maintenance |
| Embedding widens the attack surface | With embedding on, the cookie is sent on cross-site requests | Changes need the CSRF header (tested); list only the exact SharePoint origin; leave embedding off if it is not needed |
| Viewer needs line-of-sight | A SharePoint page opened outside the corporate network / VPN shows an empty frame | State this on the page; or publish through the company's application proxy |
| Unsigned program | Server anti-malware may flag the EXE | Have IT allow-list it by hash, or run from source with Python (`python run.py`) |
| Not penetration-tested | Security controls were built and unit-tested, not assessed by a third party | IT Security review before production data is entered |

## 5. Azure instead of an internal server
Possible on **Azure App Service (Linux, Python) or a VM** in the company tenant: same program, same environment variables,
`/home` as the data folder, **one instance only** (SQLite), HTTPS from the platform. Azure Static Web Apps and a storage static
website cannot run it. This variant has not been set up or tested here.
