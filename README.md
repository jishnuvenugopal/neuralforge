# NeuralForge

NeuralForge is an AI chip architect demo that turns natural-language ML model requests into ASIC-oriented hardware artifacts.

It uses a Gemini agent loop to:
- analyze a model request
- emit a hardware bill of materials
- generate Verilog RTL with hardcoded INT8 weights
- run Yosys synthesis against SkyWater 130nm
- run Icarus Verilog simulation
- optionally launch LibreLane hardening after a successful simulation

## Stack

- Backend: FastAPI + Gemini function calling
- Frontend: React + Vite
- EDA: Yosys, Icarus Verilog, netlistsvg, SkyWater 130nm liberty
- Optional physical flow: Nix + LibreLane

## Project Layout

```text
neuralforge/
├── backend/
├── frontend/
├── pdk/
├── setup.sh
└── start.sh
```

## Quick Start

```bash
cd /Users/jv/Downloads/neuralforge
export GEMINI_API_KEY="your-key"
export GEMINI_MODEL="gemini-3.1-flash-lite-preview"
bash start.sh
```

Frontend: `http://localhost:5173`  
Backend health: `http://localhost:8000/health`

To enable physical hardening after passing simulation:

```bash
export LIBRELANE_AUTO_HARDEN=1
```

## Notes

- Use `/opt/homebrew/bin/python3.12` on this machine, not the system Python.
- The visible demo path is BOM -> RTL -> synthesis -> simulation.
- LibreLane hardening is available as an optional advanced step.
