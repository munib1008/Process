#!/usr/bin/env bash
# One-time set-up of a GitHub Codespace (or any Linux host): Python packages and the local draw.io editor.
set -e
cd "$(dirname "$0")/.."
python -m pip install --quiet -r requirements.txt
if [ ! -d drawio_webapp ]; then
  python fetch_drawio.py || echo "draw.io could not be downloaded - Flow Studio will not open until 'python fetch_drawio.py' succeeds."
fi
echo "Set-up finished."
