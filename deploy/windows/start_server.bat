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

REM 4. Port on this server. The reverse proxy forwards to http://127.0.0.1:8765
set "MEA_HUB_PORT=8765"

if not exist "%MEA_HUB_DATA%" mkdir "%MEA_HUB_DATA%"

REM The app listens on 127.0.0.1 only: users reach it through the HTTPS reverse proxy, never directly.
if exist "MEA_Process_Hub.exe" (
  "MEA_Process_Hub.exe" --host 127.0.0.1 --no-browser >> "%MEA_HUB_DATA%\server.log" 2>&1
) else (
  python run.py --host 127.0.0.1 --no-browser >> "%MEA_HUB_DATA%\server.log" 2>&1
)
