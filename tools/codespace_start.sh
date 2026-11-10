#!/usr/bin/env bash
# Start MEA Process Hub in the background (runs at every start of the Codespace) and print where to open it.
cd "$(dirname "$0")/.."
mkdir -p data
PORT="${MEA_HUB_PORT:-8765}"
if python - "$PORT" <<'PY'
import socket, sys
s = socket.socket()
try:
    s.settimeout(1); s.connect(("127.0.0.1", int(sys.argv[1]))); sys.exit(0)
except OSError:
    sys.exit(1)
PY
then
  echo "MEA Process Hub is already running on port $PORT."
else
  MEA_HUB_HOST="${MEA_HUB_HOST:-0.0.0.0}" nohup setsid python run.py --no-browser --port "$PORT" > data/server.log 2>&1 &
  for i in $(seq 1 90); do
    grep -q "MEA Process Hub is running" data/server.log 2>/dev/null && break
    sleep 1
  done
fi
echo "=================================================================="
if [ -n "$CODESPACE_NAME" ]; then
  echo " Open:  https://${CODESPACE_NAME}-${PORT}.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}/"
  echo " (or the PORTS tab > MEA Process Hub > globe icon)"
else
  echo " Open:  http://127.0.0.1:${PORT}/"
fi
if [ -f data/FIRST_RUN_ADMIN_PASSWORD.txt ]; then
  echo " First sign-in:"; sed 's/^/   /' data/FIRST_RUN_ADMIN_PASSWORD.txt
fi
echo " Log:   data/server.log"
echo "=================================================================="
