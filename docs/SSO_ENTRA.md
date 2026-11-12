# Single sign-on with Microsoft Entra ID

## What it does
People open MEA Process Hub and click **Sign in with Microsoft**. They sign in at Microsoft with their company account (including
MFA and Conditional Access, which Entra enforces), and the tool receives a signed statement of who they are and which role they have.
The tool never sees a password and stores no token.

| Topic | Behaviour |
|---|---|
| Who may sign in | People of **one** tenant; with *Assignment required* only those assigned to the application |
| Role in the tool | From the **app roles** of the Entra application, read at every sign-in (or kept in the tool, see *Variants*) |
| First sign-in | The user is created automatically with name, user name and role |
| Leaver / disabled account | Cannot sign in again. A session that is already open ends after at most 12 hours |
| Role changed in Entra | Applies at the person's next sign-in |
| Blocked in the tool (*Users & roles ▸ deactivate*) | No entry, even with a valid Microsoft sign-in |
| Local accounts | Keep working unless switched off; local administrators always keep working (break-glass) |

This applies to the **live tool on a server** (`docs/SERVER_AND_SHAREPOINT.md`). The read-only SharePoint publication needs none of this.

## Before you start
* The tool runs behind HTTPS at a fixed address, for example `https://processhub.example.com`.
* The server can reach `https://login.microsoftonline.com` (through the company proxy: set `HTTPS_PROXY` for the service).
* You have someone who may register applications in Entra ID.

## Part A – Entra ID (administrator, about 20 minutes)
1. **Entra admin center ▸ Applications ▸ App registrations ▸ New registration**
   * Name: `MEA Process Hub`
   * Supported account types: **Accounts in this organizational directory only (single tenant)**
   * Redirect URI: platform **Web**, value `https://processhub.example.com/auth/callback` (exactly the address shown under
     *Administration ▸ Single sign-on* in the tool)
2. On the overview page note the **Application (client) ID** and the **Directory (tenant) ID**.
3. **Certificates & secrets ▸ New client secret**. Copy the **Value** now (it is shown once). Note the expiry date in a calendar:
   when the secret expires, sign-in stops until a new one is configured.
4. **App roles ▸ Create app role** – one per role you will use. *Allowed member types*: Users/Groups. The **Value** must be:

   | Value | Role in the tool |
   |---|---|
   | `admin` | Administrator |
   | `controller` | Document Controller (publishes, imports, changes IDs) |
   | `approver` | Approver |
   | `reviewer` | Reviewer |
   | `dept_owner.LOG` | Department Owner of one department (code after the dot) |
   | `editor.LOG` | Editor of one department |
   | `editor` | Editor for all departments |
   | `viewer` | Reader |

   A prefix `ProcessHub.` is accepted (`ProcessHub.editor.LOG`). A person with several roles gets the highest one.
   Department codes are listed under *Administration ▸ Single sign-on*.
5. **Enterprise applications ▸ MEA Process Hub ▸ Properties**: set **Assignment required?** to **Yes**, so that only assigned people can sign in.
6. **Enterprise applications ▸ MEA Process Hub ▸ Users and groups ▸ Add user/group**: assign people (or groups, if your licence allows
   group assignment) to the app roles.
7. API permissions: the tool asks only for sign-in (`openid`, `profile`, `email`). No Microsoft Graph permission is needed.
   If your tenant requires it, grant admin consent.

## Part B – the server (about 10 minutes)
1. Save the client secret in a text file that only the service account can read, for example `D:\MEAProcessHubData\oidc_secret.txt`.
2. In `deploy\windows\start_server.bat` fill in:
   ```
   set "MEA_HUB_PUBLIC_URL=https://processhub.example.com"
   set "MEA_HUB_OIDC_TENANT=<Directory (tenant) ID>"
   set "MEA_HUB_OIDC_CLIENT_ID=<Application (client) ID>"
   set "MEA_HUB_OIDC_CLIENT_SECRET_FILE=D:\MEAProcessHubData\oidc_secret.txt"
   ```
3. Restart the service. Sign in as local administrator and open **Administration ▸ Single sign-on**: it must say
   *Switched on. The directory answers.*
4. In a private browser window open the tool and click **Sign in with Microsoft**. Check your name and role in the top bar.
5. When this works for a few people, switch off passwords for everyone except local administrators:
   `set "MEA_HUB_OIDC_ONLY=1"` and restart.

## Variants
| Setting | Effect |
|---|---|
| `MEA_HUB_OIDC_DEFAULT_ROLE=viewer` (default) | A person without an app role becomes a reader |
| `MEA_HUB_OIDC_DEFAULT_ROLE=none` | A person without an app role is refused |
| `MEA_HUB_OIDC_ROLE_SOURCE=tool` | Entra only proves who the person is; roles are given under *Users & roles*. New people get the default role |
| `MEA_HUB_OIDC_ONLY=1` | Passwords are accepted only for local administrators |

An existing local account whose user name equals the person's Microsoft user name (their sign-in e-mail address) is taken over at the
first Microsoft sign-in: it becomes a Microsoft account and its password stops working.

## Inside SharePoint and Teams
Microsoft's sign-in page refuses to be shown inside a frame. When the tool runs framed, **Sign in with Microsoft** therefore opens a
small sign-in window; after sign-in the window closes and the framed page is signed in. If the browser blocks the window, allow pop-ups
for the page or use *Full window ↗*. The Teams **desktop** client may block such windows – this case is not covered yet; use Teams in the
browser, the full window, or the SharePoint publication for readers.

## What is checked and stored
* Each sign-in uses a one-time state value and PKCE; an answer can be used once and for ten minutes.
* The ID token must be signed by the tenant's published key (RS256, at least 2048 bit), issued by this tenant, for this application,
  for this sign-in attempt, and be within its validity period. Anything else is refused and logged as a failed sign-in.
* Stored per person: Entra object ID, user name, display name, role, last sign-in. Sign-ins and failures are in the audit log.
* Only tenant-specific sign-in is accepted (`common` / multi-tenant is refused). Client certificates instead of a secret are not supported.

## Troubleshooting
| Message | Cause | Fix |
|---|---|---|
| `AADSTS50011` redirect URI mismatch | The redirect URI in Entra differs from the tool's address | Register exactly the URI shown under *Administration ▸ Single sign-on*; set `MEA_HUB_PUBLIC_URL` to the address users type |
| `AADSTS7000215` invalid client secret | Wrong or expired secret; the secret *ID* was copied instead of its *Value* | Create a new secret and put its Value into the file |
| `AADSTS50105` user not assigned | *Assignment required* is on and the person has no assignment | Part A step 6 |
| `AADSTS700016` application not found | Wrong client ID or tenant ID | Compare both IDs with the overview page |
| "The identity provider could not be reached" | The server has no route to login.microsoftonline.com | Proxy / firewall; `HTTPS_PROXY` |
| "no role in MEA Process Hub is assigned to you" | `MEA_HUB_OIDC_DEFAULT_ROLE=none` and no app role | Assign an app role |
| Signed in, but as reader although a role was assigned | The app role *Value* is not one of the table above, or the department code is unknown | Correct the value; the person signs in again |
| The button is missing | Single sign-on is not completely configured | *Administration ▸ Single sign-on* lists what is missing |

## What was tested
| Check | Result |
|---|---|
| Complete sign-in against a stand-in identity provider that answers like Entra (configuration document, key set, token endpoint): role mapping, department scope, default role, refusal of forged, altered, expired, replayed, wrong-application and wrong-tenant answers | Automated test, passes |
| Sign-in in Chromium: full window and from inside a framed page through the sign-in window | Works |
| A real Entra tenant, Conditional Access, guest users, the Teams desktop client | **Not tested** – needs your tenant |
