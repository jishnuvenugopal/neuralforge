---
updated_at: 16 Nov 2026 | 07:49 AM IST
---
# NeuralForge — operator state

Project: an LLM agent turns a plain-English request for a small neural network into
SkyWater-130 Verilog with the trained INT8 weights baked in. Yosys synthesizes it and
Icarus checks every output bit-exactly against an integer reference. The model writes
the design; it never writes or grades the test. FastAPI backend + React dashboard,
both served at http://localhost:8000.

**Repo goal now:** make that claim checkable by anyone, not just this machine:
CI on a neutral runner (done), real runs others can re-verify, then measured pass rates.

Run: `NEURALFORGE_NO_BROWSER=1 bash start.sh` · Tests: `python3.12 -m unittest discover -s tests -v`
(71 tests, ~82 s, none skipped with Yosys 0.63 + Icarus 13.0). Use python3.12 for
anything importing backend/; plain python3 here lacks the packages.

## Past

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
  `.neuralforge/settings.json` (git-ignored). Server was **not running** on 2026-11-16.
- Evidence so far (details in `issues/001`, summarised in README Results):
  XOR 4/4 · Iris 150/150 · Attention 67/67 bit-exact on super-vl, one passing run each
  (2026-10-19/20). gpt-oss-20b failed attention. Generated RTL from those runs was not
  kept, so none of them can be re-checked yet. Cell counts lack the mapping mode.
- CI covers Yosys 0.33 (runner) and 0.63 (this Mac). Runner-sensitive tests:
  exact 34 flip-flops (XOR), Iris needs full ABC > 45 s to hit the `-fast` path.
- The README has no image yet.
- Remote: check `git status -sb`; the close commit may be local only.

## Future

1. `koder/plans/002_dashboard_screenshot/INDEX.md`: a screenshot of a real XOR run,
   never the mock (its numbers are made up), with that run's RTL and verdict saved
   under `docs/runs/`. The Settings drawer must stay out of frame (key hint, home path).
   Owner must pick the capture tool (plan recommends playwright-core + Brave) and
   approve the npm download before step 4.
2. Not yet planned: repeated live runs per preset and model (pass rate, time,
   cells); a mutation test of the gate (broken variants of the reference RTL, kill
   rate); keeping every run's RTL.

Owner decisions pending: capture tool for plan 002; GitHub topics (not set; suggested
`verilog llm-agents asic skywater-pdk yosys hardware-verification`).

Next action: run plan 002's Workflow on branch `docs/screenshot`, asking for the
capture tool first.
