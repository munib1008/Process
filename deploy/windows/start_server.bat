@echo off
REM ============================================================================
REM  MEA Process Hub - server start (internal Windows server behind IIS or nginx)
REM  Edit the four SET lines, then run this file (or register it with
REM  register_startup_task.ps1 so that it starts with the server).
REM ============================================================================
setlocal
cd /d "%~dp0..\.."

REM 1. Where the database, uploads, exports and backups live. Put it on a drive that is backed up.
set "MEA_HUB_DATA=D:\MEAProcessHubData"

REM 2. The host name users type (the HTTPS site in IIS/nginx). Several names: comma-separated.
set "MEA_HUB_ALLOW_HOSTS=processhub.example.com"

REM 3. Sites that may show the tool inside a page (SharePoint Embed web part). Leave empty to forbid embedding.
REM    Example: https://contoso.sharepoint.com
set "MEA_HUB_EMBED_ORIGINS="

REM 3b. Single sign-on with Microsoft Entra ID (docs\SSO_ENTRA.md). Leave empty to use the tool's own user names and passwords.
set "MEA_HUB_PUBLIC_URL="
set "MEA_HUB_OIDC_TENANT="
set "MEA_HUB_OIDC_CLIENT_ID="
set "MEA_HUB_OIDC_CLIENT_SECRET_FILE="
REM    Optional: MEA_HUB_OIDC_DEFAULT_ROLE (viewer | none), MEA_HUB_OIDC_ROLE_SOURCE (entra | tool), MEA_HUB_OIDC_ONLY (1 = no passwords except local admins)

REM 3c. Notifications (docs\NOTIFICATIONS.md). Leave empty for none.
set "MEA_HUB_SMTP_HOST="
set "MEA_HUB_SMTP_PORT=25"
set "MEA_HUB_MAIL_FROM="
set "MEA_HUB_TEAMS_WEBHOOK_FILE="
REM    Optional: MEA_HUB_SMTP_STARTTLS (1), MEA_HUB_SMTP_USER, MEA_HUB_SMTP_PASSWORD_FILE, MEA_HUB_NOTIFY_DIGEST (weekly | daily | off), MEA_HUB_NOTIFY_DIGEST_HOUR (8)

REM 4. Port on this server. The reverse proxy forwards to http://127.0.0.1:8765
set "MEA_HUB_PORT=8765"

if not exist "%MEA_HUB_DATA%" mkdir "%MEA_HUB_DATA%"

REM The app listens on 127.0.0.1 only: users reach it through the HTTPS reverse proxy, never directly.
if exist "MEA_Process_Hub.exe" (
  "MEA_Process_Hub.exe" --host 127.0.0.1 --no-browser >> "%MEA_HUB_DATA%\server.log" 2>&1
) else (
  python run.py --host 127.0.0.1 --no-browser >> "%MEA_HUB_DATA%\server.log" 2>&1
)
