#!/bin/bash
# NeuralForge — Start both backend and frontend

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -z "$GEMINI_API_KEY" ]; then
  echo "ERROR: Set GEMINI_API_KEY first"
  echo "  export GEMINI_API_KEY=\"your-key-here\""
  exit 1
fi

# Use homebrew Python 3.12 (has google-genai installed)
PYTHON="/opt/homebrew/bin/python3.12"
if [ ! -f "$PYTHON" ]; then
  PYTHON="python3.12"
fi

# Default to gemini-2.5-flash-preview-04-17
export GEMINI_MODEL="${GEMINI_MODEL:-gemini-3.1-flash-lite-preview}"

echo "Starting NeuralForge..."
echo "  Python:  $($PYTHON --version)"
echo "  API Key: ${GEMINI_API_KEY:0:8}..."
echo "  Model:   $GEMINI_MODEL"
echo ""

# Kill any existing instances
pkill -f "uvicorn main:app" 2>/dev/null
sleep 1

# Start backend
cd "$SCRIPT_DIR/backend"
$PYTHON -m uvicorn main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
echo "Backend started (PID $BACKEND_PID) → http://localhost:8000"

# Start frontend
cd "$SCRIPT_DIR/frontend"
npx vite --port 5173 &
FRONTEND_PID=$!
echo "Frontend started (PID $FRONTEND_PID) → http://localhost:5173"

echo ""
echo "Mock mode: http://localhost:5173?mock=true"
echo "Press Ctrl+C to stop both."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT
wait
