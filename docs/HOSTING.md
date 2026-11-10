# Hosting MEA Process Hub from GitHub (review phase)

MEA Process Hub is a server application (Python + a database). **GitHub Pages cannot run it** – Pages serves static files only.
The way to run it straight from the GitHub repository is **GitHub Codespaces**: GitHub starts a Linux machine from the repository,
this repository's `.devcontainer` installs everything and starts the app, and GitHub gives the port an HTTPS address.

Use this for **review and finalisation**. It is not a production host (see *Limits*).

## Start (once, about 3 minutes)
1. On github.com open the repository, switch to the branch you want to review (currently `claude/gifted-heisenberg-ivbeoa`).
2. **Code ▸ Codespaces ▸ Create codespace on <branch>**.
3. Wait until the terminal prints the block with **Open: https://…-8765.app.github.dev/** and the one-time admin password.
   (If the block has scrolled away: run `bash tools/codespace_start.sh` in the terminal – it prints it again.)
4. Open the address, sign in as `admin` with the one-time password and set your own password.
   All supplied documents and the 72 flows are imported automatically at this first start.

## Share the address with reviewers
The address is **private by default** – only your GitHub account can open it.
- **PORTS** tab ▸ right-click *MEA Process Hub (8765)* ▸ **Port Visibility**:
  - *Private* – only you (default).
  - *Private to Organization* – members of the GitHub organisation (only offered when the repository belongs to an organisation).
  - *Public* – anyone who has the address reaches the sign-in page.
- Create one user per reviewer in **Administration ▸ Users** (role *Reviewer* or *Viewer*). Do not share the admin account.

**Before you choose *Public*:** the address is then on the internet and the documents are protected only by the app's user names and
passwords. The content is classified *Internal*. Check with IT Security / the document owner first, do not start with `--demo-users`
(known passwords), and switch the port back to *Private* when the review session is over.

## Limits (why this is not the final host)
- The address works **only while the Codespace is running**. GitHub stops an idle Codespace (default 30 minutes) and the address then
  shows an error until you start the Codespace again (github.com/codespaces). The app starts by itself at every start.
- Data (edits, comments, users) is kept in the Codespace's `data/` folder. It survives stop/start but is **lost when the Codespace is
  deleted** – GitHub deletes unused Codespaces after a retention period (default 30 days). Before deleting: **Administration ▸ Backup**
  and download the ZIP; the EXE (or any other installation) restores it.
- Codespaces usage is metered per GitHub account (free monthly quota, then billed).
- One machine, one database: suitable for a handful of concurrent reviewers, not for the whole region.

## What changes for a hosted start
- `MEA_HUB_HOST=0.0.0.0` and `MEA_HUB_PORT` (or `PORT`) are read from the environment; `.devcontainer` sets them.
- Behind an HTTPS address the session cookie is marked `Secure` (detected from `X-Forwarded-Proto: https`, or force with `MEA_HUB_SECURE_COOKIE=1`).
- Sign-in is throttled: 8 failed attempts for a user name block that name for 15 minutes (also in the EXE).
- Forgot the admin password in a Codespace: stop the app (`pkill -f run.py`), `python run.py --reset-admin`, `bash tools/codespace_start.sh`.

## After the review
Download a backup, build the Windows EXE from the same branch (GitHub Actions ▸ *build-exe*), restore the backup in the EXE.
For permanent multi-user hosting use a company server or the company's Azure tenant, not Codespaces.
