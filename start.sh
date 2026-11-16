#!/bin/bash
# NeuralForge: one command, one address.
#
#   bash start.sh          build the UI if it changed, then serve everything at
#                          http://localhost:8000 and open the browser
#   bash start.sh --dev    hot-reloading UI on :5173 (backend still on :8000)
#
# API keys are set in the app (Settings). Environment variables also work: see README, "Model providers".
# NEURALFORGE_PORT changes the port; NEURALFORGE_NO_BROWSER=1 skips opening the browser.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PORT="${NEURALFORGE_PORT:-8000}"
URL="http://localhost:${PORT}"   # plain localhost: Safari's iCloud Private Relay leaves it alone
DEV=0
[ "${1:-}" = "--dev" ] && DEV=1

say()  { printf "  %s\n" "$*"; }
fail() { printf "\n  ✗ %s\n\n" "$*" >&2; exit 1; }

# --- Python --------------------------------------------------------------
PYTHON="${PYTHON:-}"
if [ -z "$PYTHON" ]; then
  for candidate in python3.12 python3.13 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then PYTHON="$(command -v "$candidate")"; break; fi
  done
fi
[ -n "$PYTHON" ] || fail "Python 3.10+ not found. Run: bash setup.sh"
"$PYTHON" -c 'import sys; sys.exit(sys.version_info < (3, 10))' || fail "Python 3.10+ needed ($("$PYTHON" --version) found)."
"$PYTHON" -c 'import fastapi, uvicorn, openai, anthropic, numpy' 2>/dev/null \
  || fail "Python packages missing. Run: $PYTHON -m pip install -r backend/requirements.txt  (or: bash setup.sh)"

# --- UI build ------------------------------------------------------------
FRONTEND="$SCRIPT_DIR/frontend"
if [ "$DEV" = 0 ]; then
  if [ ! -f "$FRONTEND/dist/index.html" ] || [ -n "$(find "$FRONTEND/src" "$FRONTEND/index.html" -newer "$FRONTEND/dist/index.html" 2>/dev/null | head -1)" ]; then
    command -v npm >/dev/null 2>&1 || fail "Node.js (npm) is needed to build the UI once. Install it: brew install node"
    say "Building the UI..."
    [ -d "$FRONTEND/node_modules" ] || (cd "$FRONTEND" && npm install --silent)
    (cd "$FRONTEND" && npm run build --silent >/dev/null)
  fi
fi

# --- Port ----------------------------------------------------------------
stale="$(pgrep -f "uvicorn main:app .*--port ${PORT}" || true)"
[ -n "$stale" ] && kill $stale 2>/dev/null && sleep 1
if lsof -ti "tcp:${PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
  fail "Port ${PORT} is in use by another program. Try: NEURALFORGE_PORT=8010 bash start.sh"
fi

# --- Backend -------------------------------------------------------------
cd "$SCRIPT_DIR/backend"
"$PYTHON" -m uvicorn main:app --host 127.0.0.1 --port "$PORT" --log-level warning &
BACKEND_PID=$!
PIDS="$BACKEND_PID"
trap 'kill $PIDS 2>/dev/null' EXIT INT TERM

for _ in $(seq 1 40); do
  curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1 && break
  kill -0 "$BACKEND_PID" 2>/dev/null || fail "The backend stopped while starting (see the error above)."
  sleep 0.25
done

OPEN_URL="$URL"
if [ "$DEV" = 1 ]; then
  (cd "$FRONTEND" && npx vite --port 5173 --strictPort >/dev/null) &
  PIDS="$PIDS $!"
  OPEN_URL="http://localhost:5173"
  sleep 1.5
fi

echo ""
echo "  NeuralForge is running"
echo ""
echo "    ➜  ${OPEN_URL}"
echo ""
echo "  Settings (provider, API key, setup checks) open from the ⚙ button in the app."
echo "  Press Ctrl+C to stop."
echo ""

if [ "${NEURALFORGE_NO_BROWSER:-0}" != 1 ]; then
  if command -v open >/dev/null 2>&1; then open "$OPEN_URL"
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$OPEN_URL" >/dev/null 2>&1 || true
  fi
fi

wait "$BACKEND_PID"
