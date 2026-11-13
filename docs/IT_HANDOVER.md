# IT hand-over – MEA Process Hub 1.5.1

For IT Infrastructure, IT Security and the SharePoint / Microsoft 365 administrators. Purpose: get a **decision**, a **pilot environment** and a **security review**
without a long explanation round. Details are in the documents named in section 9; this page only says what is needed and why.

**What it is:** a process library that replaces the departmental Word handbooks – flowcharts, review and approval workflow, signed decisions, exports.
One Python program with a SQLite database, delivered as a Windows EXE or run from source. Classification of the content: *Internal*. No telemetry,
no update service, no outbound connection unless IT configures one.

## 1. Critical points first
| # | Point | Consequence | Treatment |
|---|---|---|---|
| 1 | **Not an approved company system.** No IT review has happened; no penetration test; one maintainer. | Do not enter production approvals until section 6 is done. | Security review (section 6) and a named second maintainer. |
| 2 | **Sign-in with Entra ID is built but was never run on the company tenant.** Tested only against a stand-in identity provider. | Until it is proven, users would need local passwords, no MFA and no automatic leaver handling. | App registration, about 20 minutes (section 3, request 2). |
| 3 | **The source repository was public before it was made private.** It contains the delivered Word and draw.io handbooks, no passwords, keys or user data. | The documents may have been copied while public. | The information owner decides whether the exposure needs a record. |
| 4 | **One server, one SQLite database, no fail-over.** Measured: 400 simulated users, 95 % of actions within 0.09 s on a 4-core machine (both sides on one machine). | Fine for the expected load; an outage stops everybody until restored. | Backup copies off the server; one full restore on a second machine before go-live. |
| 5 | **Data folder and backups are not encrypted by the tool.** | Whoever reads the disk reads the library and the password hashes. | Disk encryption and a folder permission for the service account only. |

## 2. Decisions requested from IT
| Decision | Options (best first) | Recommendation | If no decision |
|---|---|---|---|
| **Where does the live tool run?** | 1. Internal Windows server behind IIS with the company certificate. 2. Azure App Service / VM in the company tenant (one instance). 3. Single PC (EXE) – no shared data. | **1**, because IIS/ARR, the service account and the firewall rules are standard for IT. Option 2 works in principle but was never set up. | Only option 3 remains: every copy has its own data, so there is no shared approval workflow. |
| **How do readers get the content?** | 1. Read-only publication in a SharePoint library with the web part (no server, Microsoft 365 sign-in). 2. The live tool on the server. | **1 for all readers**, the live tool only for authors, reviewers and approvers. Needs only the App Catalog upload and a library. | Readers get exported Word/PDF files by e-mail, which are uncontrolled copies. |
| **Is Microsoft Teams a channel?** | Tab in a Teams channel, same package as SharePoint. | Optional, after SharePoint works. Teams desktop sign-in in a frame is not covered. | Not used. |
| **Who maintains it?** | Named IT or business owner as second maintainer; escrow of the build. | At least a second maintainer before go-live. | Fixes depend on one person. |

## 3. Requests to IT (in this order)
| # | Request | Owner | Effort (estimate) | Needed for | Reference |
|---|---|---|---|---|---|
| 1 | **Pilot server**: Windows Server, service account `svc_processhub` with Modify rights on the data folder only, data folder on a backed-up drive. | Infrastructure | 1 working session | Everything below | `SERVER_AND_SHAREPOINT.md` §1 |
| 2 | **Entra app registration**: single tenant, redirect URI `https://<host>/auth/callback`, client secret (owner and expiry date in a calendar), app roles `admin`, `controller`, `approver`, `reviewer`, `editor[.DEPT]`, `dept_owner.DEPT`, `viewer`, *Assignment required = Yes*, only `openid`, `profile`, `email` – no Graph permission. Send tenant ID, client ID and the secret to the server owner through the company's secret channel. | Entra administrator | about 20 minutes plus 10 on the server | MFA, leaver handling, role mapping | `SSO_ENTRA.md` |
| 3 | **HTTPS address and certificate**, IIS with URL Rewrite and ARR (or nginx), firewall 443 to the user network only; port 8765 stays closed (the app listens on 127.0.0.1). | Infrastructure | 1 working session | Access | `deploy/iis/web.config`, `deploy/nginx/` |
| 4 | **Outbound**: the server must reach `login.microsoftonline.com` (through the proxy if required: `HTTPS_PROXY`). Nothing else is needed; mail relay and a Teams webhook are optional. | Network | Ticket | Single sign-on | `SSO_ENTRA.md` Before you start |
| 5 | **SharePoint**: upload `MEA_Process_Hub_SharePoint_Teams.sppkg` to the tenant App Catalog (it asks for no API permissions and contains no process data), a document library `processhub`, a page with the web part. | SharePoint administrator, site owner | One upload, one library, one page (estimate: 1 working session) | Reader access without a server | `SHAREPOINT_PUBLISHING.md` |
| 6 | **Backup and restore**: include the data folder in the server backup; copy the ZIP from *Administration ▸ Backup* off the server; perform one full restore on a second machine; schedule `MEA_Process_Hub.exe --restore-drill` (exit code 1 on failure). | Infrastructure | 1 working session | Recovery | `ADMIN_GUIDE.md` Restore drill |
| 7 | **Anti-malware**: allow-list the EXE by hash (it is unsigned unless a certificate is added to the build) or run from source with Python 3.12; exclude the data folder from on-access scanning if policy allows, scanning every database write slows the tool. | Endpoint security | Ticket | Start-up | `ADMIN_GUIDE.md` Code signing |
| 8 | **Security review** with the scope in section 6. | IT Security | Their estimate | Production data | `SECURITY_REVIEW_PACK.md` |
| 9 | **Mail relay** for notifications (optional): host, port, sender address, account; the password is read from a file, never stored in the database. | Messaging | Ticket | Reminders to reviewers | `NOTIFICATIONS.md` |

## 4. What is proven and what is not
| Area | Status | Evidence |
|---|---|---|
| Application behaviour: workflow, approvals, exports, import, roles, department scope | **Proven** by 46 automated tests, and by a browser journey with five roles | Build `build-exe.yml` runs tests, browser test, accessibility check, dependency scan, load test; the EXE is only built when all pass |
| Capacity | **Measured** on one 4-core machine, both sides on it | `docs/LOAD_TEST.md`; rerun on the real server with `tools/load_test.py --from-data <copy>` |
| Dependencies | **Scanned** in every build (pip-audit, npm audit) and pinned. The first scan found 42 vulnerabilities in the image library; fixed in 1.5.0. | `requirements-lock.txt`; versions 1.0.0 to 1.4.0 were not scanned |
| Accessibility | WCAG 2.1 A/AA automated rules on nine pages, no finding. **Manual keyboard and screen-reader check still open.** | `tests/e2e/run.js` |
| Entra sign-in | Tested with a stand-in; **not on the tenant** | `SSO_ENTRA.md` What was tested |
| IIS / nginx, Windows service, SharePoint web part, Teams, mail relay | Scripts and package written; **not run on company systems** | `SERVER_AND_SHAREPOINT.md` |
| Penetration test, code review | **None** | – |
| Signed decisions | Tamper-evident chain with content fingerprints. **Not** a qualified electronic signature (eIDAS) and the tool is not validated for regulated records. | `ADMIN_GUIDE.md` Signed decisions |

## 5. Data protection
| Item | Fact |
|---|---|
| Personal data | User name, display name, role, last sign-in, audit trail of changes; with Entra also the object ID. |
| Reading statistics | One row per person, process and day, the person as keyed hash; counts only in the report; deleted after 400 days. Whoever holds the database **and** the key can test whether a named person opened a process. If the works council or the data-protection officer requires it, counting can be switched off – ask before the wide rollout. |
| Location | One data folder on the host. No cloud service, no third-party AI or diagram service: draw.io is served locally. |
| Leavers | With Entra: cannot sign in again; a session already open ends after at most 12 hours. Local accounts are deactivated by an administrator. |

## 6. Suggested security review scope
1. Sign-in and sessions, local and Entra, including the sign-in window in a frame.
2. Authorisation on `/api/*`: by role and by department.
3. Hostile `.docx` and `.drawio` uploads; rendering of stored rich text, comments and flow labels; exports with hostile content.
4. Configuration: file permissions on the data folder and the secret files, proxy headers, host allow-list.
Known gaps, to be accepted or treated, are in `SECURITY_REVIEW_PACK.md` §4: no idle time-out and no forced sign-out when an Entra account is disabled (up to 12 hours), no
general request rate limit (limit at the proxy), uploads not scanned for malware, audit log in the same database as the data, `synchronous = NORMAL` (a power cut can lose the last commits, not corrupt the file).

## 7. Why this might fail, and what we do about it
| Risk | Likelihood / effect | Mitigation |
|---|---|---|
| IT refuses hosting or sign-in | Medium; the live workflow stays on one PC | Start with the SharePoint publication (no server, no sign-in work) and run the pilot with the document controller's PC; revisit with the pilot results |
| No business owners named | High; nothing gets approved, the tool becomes a second unmaintained handbook | Separate decision for management, not an IT task; the library stays "draft" |
| The secret expires unnoticed | Medium; sign-in stops | Expiry in a calendar with an owner; local break-glass administrator always works |
| Maintainer leaves | Medium; no fixes | Second maintainer, escrow of the build, exit route: all content exports to Word, PDF, XLSX and draw.io |
| Users keep working in the old Word files | High | Readers' link in SharePoint and Teams; withdraw the Word copies after approval |
| IT builds a competing solution and the work is duplicated | Low to medium | Agree early whether this is a pilot or the target; the exit route above keeps the content portable |

## 8. Pilot and exit criteria
| Step | Result needed before the next |
|---|---|
| 1. Pilot server + HTTPS + SharePoint publication | A reader on the corporate network opens the library, nothing else |
| 2. Entra sign-in for 5 named people | Name and role correct in the top bar; a disabled account is refused |
| 3. Restore test on a second machine | `--restore-drill` passes and the restored copy opens |
| 4. Security review | No open high finding |
| 5. One department, real approvals | Signed-decision register check passes; owners confirm the workflow |
Go / no-go after step 4: no open high finding, restore proven, Entra proven, a named second maintainer.

## 9. Where to find things
Release package: GitHub release v1.5.1 (the ZIP with the EXE, `deploy/`, `docs/`). Documents: `docs/SERVER_AND_SHAREPOINT.md`, `docs/SHAREPOINT_PUBLISHING.md`, `docs/SSO_ENTRA.md`,
`docs/ADMIN_GUIDE.md`, `docs/SECURITY_REVIEW_PACK.md`, `docs/LOAD_TEST.md`, `docs/NOTIFICATIONS.md`, `docs/TEAMS.md`, `CHANGELOG.md`.
Questions about the content: the business owner (to be named). Questions about the tool: the maintainer (to be named).
