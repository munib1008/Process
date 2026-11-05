@echo off
REM ============================================================
REM  Build MEA_Process_Hub.exe on Windows (needs Python 3.11+ and, for the offline editor, git)
REM  Output: dist\MEA_Process_Hub\  (exe + drawio_webapp + docs) and dist\MEA_Process_Hub_win64.zip
REM ============================================================
setlocal
cd /d "%~dp0"
if not exist .venv ( py -3 -m venv .venv || goto :err )
call .venv\Scripts\activate.bat || goto :err
python -m pip install --upgrade pip || goto :err
python -m pip install -r requirements-dev.txt || goto :err
python -m pytest tests -q || goto :err
pyinstaller build\mea_hub.spec --noconfirm --distpath dist\bin --workpath build\work || goto :err
if exist dist\MEA_Process_Hub rmdir /s /q dist\MEA_Process_Hub
mkdir dist\MEA_Process_Hub
copy dist\bin\MEA_Process_Hub.exe dist\MEA_Process_Hub\ >nul
copy README.md dist\MEA_Process_Hub\ >nul
xcopy docs dist\MEA_Process_Hub\docs\ /e /i /q >nul
mkdir dist\MEA_Process_Hub\source_documents
if exist source_documents xcopy source_documents dist\MEA_Process_Hub\source_documents\ /e /i /q >nul
where git >nul 2>nul && (
  echo Fetching draw.io web app for fully offline flowchart editing...
  python fetch_drawio.py && xcopy drawio_webapp dist\MEA_Process_Hub\drawio_webapp\ /e /i /q >nul
) || echo git not found - skipping draw.io download. The app will use the online draw.io host instead.
powershell -NoProfile -Command "Compress-Archive -Path dist\MEA_Process_Hub\* -DestinationPath dist\MEA_Process_Hub_win64.zip -Force"
echo.
echo DONE: dist\MEA_Process_Hub\MEA_Process_Hub.exe
exit /b 0
:err
echo BUILD FAILED
exit /b 1
