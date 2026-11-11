#!/usr/bin/env bash
# Brandora: one command, one port.
# Installs anything missing, rebuilds the React app when its sources changed,
# then FastAPI serves both the UI and the API on http://localhost:8000.
#
#   ./start.sh         normal use
#   ./start.sh --lan   also reachable from phones on the same Wi-Fi (the Android app)
#   ./start.sh --dev   live reload while coding (UI on http://localhost:5173)
set -euo pipefail
cd "$(dirname "$0")"
PORT=8000
HOST=127.0.0.1
[ "${1:-}" = "--lan" ] && HOST=0.0.0.0

# Python environment
[ -x venv/bin/python ] || python3 -m venv venv
if [ ! -f venv/.brandora-deps ] || [ backend/requirements.txt -nt venv/.brandora-deps ]; then
  echo "Installing Python packages..."
  venv/bin/pip install -q -r backend/requirements.txt
  touch venv/.brandora-deps
fi

# Frontend packages + build
command -v npm >/dev/null || { echo "Node.js 18+ is required (npm not found)."; exit 1; }
if [ ! -f frontend/node_modules/.package-lock.json ] ||
   [ frontend/package-lock.json -nt frontend/node_modules/.package-lock.json ]; then
  echo "Installing frontend packages..."
  (cd frontend && npm install --no-audit --no-fund)
fi

[ -f .env ] || echo "Note: no .env found. Copy .env.example to .env and add your Cloudflare keys."
curl -s -m 2 http://localhost:11434/api/tags >/dev/null ||
  echo "Note: Ollama is not reachable on :11434. Start it (ollama serve) for catalogue retrieval."

if [ "${1:-}" = "--dev" ]; then
  venv/bin/uvicorn app:app --app-dir backend --reload --reload-dir backend --port "$PORT" &
  trap 'kill $! 2>/dev/null' EXIT
  cd frontend && npx vite
  exit
fi

if [ ! -f frontend/dist/index.html ] ||
   [ -n "$(find frontend/src frontend/index.html frontend/vite.config.js -newer frontend/dist/index.html -print -quit)" ]; then
  echo "Building the frontend..."
  (cd frontend && npm run build --silent)
fi

echo "Brandora is starting on http://localhost:$PORT"
if [ "$HOST" = 0.0.0.0 ]; then
  LAN_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
  echo "Phones on this Wi-Fi: enter http://${LAN_IP:-YOUR-PC-IP}:$PORT in the Brandora app."
  echo "Anyone on this network can use the app (and your Cloudflare quota) while it runs."
fi
exec venv/bin/uvicorn app:app --app-dir backend --host "$HOST" --port "$PORT"
