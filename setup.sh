#!/bin/bash
# NeuralForge: one-time setup. Safe to re-run.
#
#   bash setup.sh            install Python packages and the UI, check the EDA tools
#   bash setup.sh --retrain  also retrain the demo models (needs torch + scikit-learn)

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OS="$(uname -s)"

ok()   { printf "  ✓ %s\n" "$*"; }
miss() { printf "  ✗ %s\n" "$*"; MISSING=1; }
MISSING=0

install_hint() {  # name, brew formula, apt package
  if [ "$OS" = "Darwin" ]; then echo "brew install $2"; else echo "sudo apt install $3"; fi
}

echo ""
echo "NeuralForge setup"
echo ""

# --- Python --------------------------------------------------------------
PYTHON=""
for candidate in python3.12 python3.13 python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then PYTHON="$(command -v "$candidate")"; break; fi
done
if [ -n "$PYTHON" ] && "$PYTHON" -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
  ok "Python: $("$PYTHON" --version)"
  echo "    Installing Python packages..."
  if ! "$PYTHON" -m pip install -q -r "$SCRIPT_DIR/backend/requirements.txt" 2>/dev/null; then
    "$PYTHON" -m pip install -q --break-system-packages -r "$SCRIPT_DIR/backend/requirements.txt" \
      && ok "Python packages" || miss "Python packages (try a virtualenv: python3 -m venv .venv && source .venv/bin/activate)"
  else
    ok "Python packages"
  fi
else
  miss "Python 3.10+   →  $(install_hint python python@3.12 python3)"
fi

# --- EDA tools -----------------------------------------------------------
command -v yosys    >/dev/null 2>&1 && ok "Yosys: $(yosys -V 2>&1 | head -1)" || miss "Yosys   →  $(install_hint yosys yosys yosys)"
command -v iverilog >/dev/null 2>&1 && ok "Icarus Verilog: $(iverilog -V 2>&1 | head -1)" || miss "Icarus Verilog   →  $(install_hint iverilog icarus-verilog iverilog)"
[ -f "$SCRIPT_DIR/pdk/sky130.lib" ] && ok "SkyWater 130 nm liberty (pdk/sky130.lib)" || miss "pdk/sky130.lib missing  →  git checkout -- pdk/sky130.lib"
command -v netlistsvg >/dev/null 2>&1 && ok "netlistsvg (optional)" || echo "  · netlistsvg not installed (optional: npm install -g netlistsvg)"

# --- UI ------------------------------------------------------------------
if command -v npm >/dev/null 2>&1; then
  echo "    Installing and building the UI..."
  (cd "$SCRIPT_DIR/frontend" && npm install --silent && npm run build --silent >/dev/null) \
    && ok "UI built (frontend/dist)" || miss "UI build failed (see npm output above)"
else
  miss "Node.js   →  $(install_hint node node nodejs)  (needed once, to build the UI)"
fi

# --- Optional retrain ----------------------------------------------------
if [ "${1:-}" = "--retrain" ]; then
  echo "    Retraining demo models..."
  (cd "$SCRIPT_DIR/backend" && "$PYTHON" model_trainer.py) || miss "Model training (needs: pip install torch scikit-learn)"
fi

echo ""
if [ "$MISSING" = 0 ]; then
  echo "  Ready. Start it with:  bash start.sh"
else
  echo "  Install the items marked ✗, then run setup again."
fi
echo ""
