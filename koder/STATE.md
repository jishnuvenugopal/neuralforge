---
updated_at: 16 Nov 2026 | 08:45 AM IST
---
# NeuralForge — operator state

Project: an LLM agent turns a plain-English request for a small neural network into
SkyWater-130 Verilog with the trained INT8 weights baked in. Yosys synthesizes it and
Icarus checks every output bit-exactly against an integer reference. The model writes
the design; it never writes or grades the test. FastAPI backend + React dashboard,
both served at http://localhost:8000.

**Repo goal now:** make that claim checkable by anyone, not just this machine:
CI on a neutral runner (done), real runs others can re-verify (one so far), then measured pass rates.

Run: `NEURALFORGE_NO_BROWSER=1 bash start.sh` · Tests: `python3.12 -m unittest discover -s tests -v`
(75 tests, ~82 s, none skipped with Yosys 0.63 + Icarus 13.0). Use python3.12 for
anything importing backend/; plain python3 here lacks the packages.

## Past

- 2026-11-16: providers made generic (PR #3, merge `fac461a`, plan `003`): NIM (default),
  OpenAI-compatible, Anthropic-compatible; ZYT Foundry removed. Env: `NEURALFORGE_PROVIDER`
  + `NVIDIA_*` / `OPENAI_*` / `ANTHROPIC_*` (key, base URL, model); Settings still win.
  Each run sends provider + model in `run_info` and `complete` (no key/hint/URL); dashboard
  badge; README Results has a Provider · model column; saved XOR `run.json` names its model.
- 2026-11-16: README shows a real XOR run (PR #2, merge `746c733`): super-vl, 4/4
  bit-exact, 4,111 cells, 30,063.8 um^2 full ABC, 4 iterations, 306 s. RTL + sha256
  + verdict in `docs/runs/2026-11-16_xor_super-vl/`; `docs/runs/recheck.py` re-runs
  the gate on it (one-weight tamper → 3/4, exit 1). Captured with playwright-core
  driving Brave; 3 real NIM runs used (details in `plans/002`). Image cropped above
  the Transcript box, which shows the simulator's macOS temp path.
- 2026-11-16: CI merged (PR #1, merge commit `14d9699`). `.github/workflows/tests.yml`:
  `tests` job on ubuntu-24.04 with apt Yosys 0.33 + Icarus 12.0, fails on any skipped
  test; `frontend` job runs `npm ci` + build. Actions pinned to SHAs, read-only token,
  no secrets. README has the badge. Run URLs in `plans/001_ci` Results.
- 2026-11-16: the first CI run found a real bug. `_parse_stat` counted 0 flip-flops on
  Yosys 0.33 (rows are `cell count`, not `count area cell`). Fixed in `d9001b0` with
  `tests/test_stat_parser.py` covering both layouts. Tests unchanged otherwise.
- 2026-11-16: skip guard proven on the runner: without the tools the suite says
  `OK (skipped=11)` and exits 0; the "Fail on skipped tests" step fails it
  (throwaway `162fa12`, reverted `bb45792`, kept in history via merge commit).
- 2026-11-15: published the NIM work; README gained Results, Limitations, env vars;
  `pdk/` carries the Apache-2.0 text and NOTICE. Plans 001/002 written (761462e).
- 2026-10-20: super-vl is the spec default (01dfb55); NVIDIA_NIM_MODELS is
  probe-ordered (2b9e02f); Settings button in the header (7adbd63).
- 2026-10-19: NVIDIA NIM as default provider (e6eecfb), streamed OpenAI-compatible
  calls with empty-stream reporting (778b498); 8-model probe + live presets → `issues/001`.

## Present

- Provider `nvidia_nim`, model `nvidia/nemotron-3.5-super-vl-120b-a12b`, key saved in
  `.neuralforge/settings.json` (git-ignored). The old ZYT key is still in that file,
  unused; ZYT works as OpenAI-compatible with base URL `https://foundry.zyt.app/v1`. Server was **not running** on 2026-11-16.
- Evidence so far (details in `issues/001`, summarised in README Results):
  XOR 4/4 · Iris 150/150 · Attention 67/67 bit-exact on super-vl, one passing run each
  (2026-10-19/20). gpt-oss-20b failed attention. Their RTL was not kept; only the
  2026-11-16 XOR run in `docs/runs/` can be re-checked. October cell counts lack the
  mapping mode.
- CI covers Yosys 0.33 (runner) and 0.63 (this Mac). Runner-sensitive tests:
  exact 34 flip-flops (XOR), Iris needs full ABC > 45 s to hit the `-fast` path.
- README has the CI badge and the 2026-11-16 XOR screenshot.
- Remote: check `git status -sb`; the close commit may be local only.
- Capture script (`capture.js`) and frame extractor lived in the session scratchpad and
  were not kept; plan 002 describes them.

## Future

1. Not yet planned (pick one and write a plan): repeated live runs per preset and
   model (pass rate, time, cells), saving every run's RTL under `docs/runs/`; a
   mutation test of the gate (broken variants of the reference RTL, kill rate).
2. Consider keeping a capture script in the repo (scripts/) so screenshots and saved
   runs can be regenerated; it needs a privacy guard like the one in plan 002.
3. The dashboard's Simulation transcript prints the simulator's temp path; a UI
   change could hide it so full-page screenshots need no crop.

Owner decisions pending: GitHub topics (not set; suggested `verilog llm-agents asic
skywater-pdk yosys hardware-verification`); which of Future 1 to plan next.

Next action: choose the next evidence step (repeated runs or gate mutation test) and
write it as `koder/plans/004_*`. Any new result must name its provider and model.
