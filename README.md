# NeuralForge

An LLM agent turns a plain-English request for a small neural network into
Verilog with the trained INT8 weights baked in. Yosys synthesizes it to
SkyWater 130 nm cells, and Icarus Verilog checks every output bit-exactly
against an integer reference of the network. The model writes the design;
it never writes or grades the test.

Pipeline: request → hardware bill of materials → RTL → synthesis gate →
reference simulation → optional LibreLane hardening to GDS.

## Quick start

```bash
git clone https://github.com/jishnuvenugopal/neuralforge.git
cd neuralforge
bash setup.sh      # once: Python packages, UI build, checks Yosys / Icarus
bash start.sh      # serves everything at http://neuralforge.localhost:8000
```

The app opens in your browser. It always starts in dark mode; the header has a
light-mode switch for the current visit. On first launch the **Settings** drawer opens by itself:

- **Model provider:** paste an API key and press *Save and test*. Keys are
  stored only on your machine in `.neuralforge/settings.json` (git-ignored, mode 600).
- **Setup guide:** shows which tools are installed and the command for anything missing.

`http://localhost:8000` works too. `bash start.sh --dev` runs the UI with hot
reload on port 5173.

### Model providers

| Provider | Wire protocol | Model | Notes |
|---|---|---|---|
| **ZYT Foundry** (default) | OpenAI-compatible | `gpt-6-astra` by default; any of gpt-5.5 … gpt-6.1-sol | Base URL `https://foundry.zyt.app/v1` |
| OpenAI-compatible | `/v1/chat/completions` with tools | any | Your base URL, key and model |
| Anthropic-compatible | Messages API with tool use | any (default `claude-opus-5-5`) | Your base URL, key and model |

Pick the model from the dropdown in the header or in Settings. *Load models*
asks the provider's `/models` endpoint for its current list.

Environment variables seed the defaults; values saved in Settings win:

```bash
export ZYT_FOUNDRY_API_KEY="..."            # optional; the Settings drawer is the usual way
export ZYT_FOUNDRY_BASE_URL="https://foundry.zyt.app/v1"
export ZYT_FOUNDRY_MODEL="gpt-6-astra"
export LIBRELANE_AUTO_HARDEN=1              # optional: run LibreLane after a verified simulation
```

### Requirements

Python 3.10+, Node.js (once, to build the UI), Yosys and Icarus Verilog
(`brew install yosys icarus-verilog`, or `sudo apt install yosys iverilog`).
`netlistsvg` and Nix + LibreLane are optional. The Setup guide in the app checks all of these.

## Presets

Each preset has a bit-exact reference, so every run is checked, not just synthesized:

| Preset | Network | Test vectors |
|---|---|---|
| XOR MLP | 2-8-1 MLP, ReLU, INT8 weights, 32-bit accumulators | all 4 inputs |
| Iris classifier | 4-8-3 MLP trained on Iris | all 150 samples (integer net: 148/150 correct) |
| Attention head | d = 8, 4 tokens, Q/K/V projections, scaled scores, hard attention | 67 token sets (3 edge cases + 64 seeded) |

The attention spec is NeuralForge's own exact integer definition (softmax is
replaced by hard attention, so the result is bit-exact):
`P = (W·x) >>> 8` for Q, K and V; `S = (Q·Kᵀ) >>> 3`; each query takes the V
row of its highest-scoring key (lowest index on ties). See `AttentionReference`
in `backend/golden.py`.

A free-form request that matches no preset is synthesized but reported as
**not verified**, and is never hardened.

## Project layout

```text
neuralforge/
├── backend/
│   ├── main.py          agent loop, REST + WebSocket API, serves the UI
│   ├── llm.py           OpenAI- and Anthropic-compatible tool-calling conversation
│   ├── settings.py      provider settings (local file, keys never returned to the browser)
│   ├── prereqs.py       machine checks for the Setup guide
│   ├── eda_tools.py     Yosys / Icarus / LibreLane wrappers
│   ├── golden.py        bit-exact integer references (XOR, Iris, attention)
│   ├── verifier.py      source scan, generated testbench, verdict, hash ledger
│   └── model_trainer.py trains and quantizes the demo models
├── frontend/            React + Vite UI (built into frontend/dist)
├── pdk/                 SkyWater 130 nm liberty
├── tests/
├── setup.sh
└── start.sh
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

- **Expected outputs come from the reference, not the model.** `golden.py` runs
  each preset in exact integer arithmetic (for the MLPs: INT8 weights, 32-bit
  accumulators, biases rescaled to the accumulator scale). The model is given a
  fixed port contract and the exact arithmetic.
- **NeuralForge writes the testbench.** It drives every input (XOR: all 4;
  Iris: all 150 samples; attention: 67 token sets) and writes the raw outputs to a result file whose
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

- **Synthesis time.** Area comes from full ABC mapping. A fully parallel design
  can take minutes to map (the 32-bit Iris network does), so after 90 s the gate
  retries with `abc -fast` and labels the stats `abc_mode: fast`. Fast mapping
  overstates area (77 % larger on XOR).
- `?mock=true` replays a canned run without calling any model.

## License

MIT
