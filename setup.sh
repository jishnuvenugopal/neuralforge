#!/bin/bash
# NeuralForge — One-time setup

echo "=== NeuralForge Setup ==="

# Check tools
echo "Checking tools..."
command -v yosys >/dev/null 2>&1 || { echo "MISSING: yosys (brew install yosys)"; exit 1; }
command -v iverilog >/dev/null 2>&1 || { echo "MISSING: iverilog (brew install icarus-verilog)"; exit 1; }
command -v dot >/dev/null 2>&1 || { echo "MISSING: graphviz (brew install graphviz)"; exit 1; }
echo "  yosys:    $(yosys -V 2>&1 | head -1)"
echo "  iverilog: $(iverilog -V 2>&1 | head -1)"
echo "  graphviz: OK"

# Check PDK
if [ ! -f "$(dirname "$0")/pdk/sky130.lib" ]; then
  echo "MISSING: pdk/sky130.lib"
  echo "Run: volare fetch --pdk sky130 && volare enable --pdk sky130"
  echo "Then: cp ~/.volare/sky130A/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib pdk/sky130.lib"
  exit 1
fi
echo "  sky130:   OK ($(wc -l < "$(dirname "$0")/pdk/sky130.lib") lines)"

# Install Python deps
echo ""
echo "Installing Python dependencies..."
pip3 install --break-system-packages google-genai websockets gdstk cairosvg scikit-learn 2>&1 | tail -1

# Install Node deps
echo "Installing frontend dependencies..."
cd "$(dirname "$0")/frontend"
npm install 2>&1 | tail -1
npm install -D tailwindcss @tailwindcss/vite 2>&1 | tail -1

# Install netlistsvg
npm install -g netlistsvg 2>&1 | tail -1

# Train models
echo ""
echo "Training demo models..."
cd "$(dirname "$0")/backend"
python3 model_trainer.py

echo ""
echo "=== Setup Complete ==="
echo "Run: export GEMINI_API_KEY='your-key' && bash start.sh"
