# NeuralForge

NeuralForge is an AI chip architect demo that turns natural-language ML model requests into ASIC-oriented hardware artifacts.

It uses a Gemini agent loop to:
- analyze a model request
- emit a hardware bill of materials
- generate Verilog RTL with hardcoded INT8 weights
- run Yosys synthesis against SkyWater 130nm
- check the design against a bit-exact reference of the trained network in Icarus Verilog
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
│   ├── main.py          agent loop and WebSocket API
│   ├── eda_tools.py     Yosys / Icarus / LibreLane wrappers
│   ├── golden.py        bit-exact integer reference of the trained networks
│   ├── verifier.py      source scan, generated testbench, verdict, hash ledger
│   └── model_trainer.py trains and quantizes the demo models
├── frontend/
├── pdk/
├── tests/
├── setup.sh
└── start.sh
```

## Quick Start

```bash
git clone https://github.com/jishnuvenugopal/neuralforge.git
cd neuralforge
export GEMINI_API_KEY="your-key"
export GEMINI_MODEL="gemini-3.1-flash-lite"
bash start.sh
```

Frontend: `http://localhost:5173`  
Backend health: `http://localhost:8000/health`

To enable physical hardening after passing simulation:

```bash
export LIBRELANE_AUTO_HARDEN=1
```

## How a design is verified

The first version of NeuralForge trusted two things it should not have: text
the design could print, and a testbench written by the same model that wrote
the design. I attacked that gate and found four ways to pass it with a wrong
design:

1. **A design that prints the pass line.** The verdict was a regex over the
   simulator's output, so a design with `$display("4/4 TESTS PASSED")` passed.
2. **A testbench that never checks.** The model wrote both the design and the
   testbench, and the expected values came from the model.
3. **A constant design.** Synthesis only checked Yosys' exit code, so a design
   with its outputs tied to 0 passed with 0 cells and 0 µm².
4. **Swapped code.** Simulation took fresh code, so the design that was
   simulated (and then hardened) did not have to be the one that was synthesized.

The gate now works like this:

- **Expected outputs come from the trained network.** `golden.py` runs the
  quantized network in exact integer arithmetic (INT8 weights, 32-bit
  accumulators, biases rescaled to the accumulator scale). The model is given a
  fixed port contract and the exact arithmetic.
- **NeuralForge writes the testbench.** It drives every input (XOR: all 4;
  Iris: all 150 samples) and writes the raw outputs to a result file whose
  name and contents carry a per-run random nonce. Python compares every logit
  and class with the reference. What the simulator prints is shown, never scored.
- **The design cannot talk to the testbench.** Design code with system tasks
  (`$display`, `$fopen`, `$finish`, ...), `initial` blocks, `force`,
  hierarchical references or compiler directives other than `timescale` is
  rejected before synthesis.
- **Synthesis must produce real logic.** The design needs more than 0 cells, no
  latches, and no output that is constant or undriven.
- **Each verdict is tied to the exact code.** Synthesis records the sha256 of
  the code it passed; simulation runs only that code, and LibreLane only runs
  on code whose hash passed both.

The attention preset has no reference model, so it is synthesized and reported
as unverified; it is never hardened.

The same work fixed the weight hand-off: every constant now has a unique name
(`W1_r_c`, `B1_r`, ...; before, bias names collided with weight column 0), and
biases are given at the scale they are added at. Each run uses its own temporary
folder, and the flip-flop count includes flops with reset.

The exploits are regression tests. With Yosys and Icarus installed:

```bash
python3 -m unittest discover -s tests -v
```

The simulator tests skip themselves when the tools are missing.

## Notes

- Python 3.12 recommended. Create a virtual environment before installing dependencies.
- The visible demo path is BOM -> RTL -> synthesis -> simulation.
- LibreLane hardening is available as an optional advanced step.
