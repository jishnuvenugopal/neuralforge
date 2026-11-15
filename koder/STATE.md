---
updated_at: 15 Nov 2026 | 08:04 PM +08
---
# NeuralForge — operator state

Project: an LLM agent turns a plain-English request for a small neural network into
SkyWater-130 Verilog with the trained INT8 weights baked in. Yosys synthesizes it and
Icarus checks every output bit-exactly against an integer reference. The model writes
the design; it never writes or grades the test. FastAPI backend + React dashboard,
both served at http://localhost:8000.

**Repo goal now:** make that claim checkable by anyone, not just this machine:
CI on a neutral runner, real runs others can re-verify, then measured pass rates.

Run: `NEURALFORGE_NO_BROWSER=1 bash start.sh` · Tests: `python3.12 -m unittest discover -s tests -v`
(69 tests, ~82 s, none skipped with Yosys 0.63 + Icarus 13.0). Use python3.12 for
anything importing backend/; plain python3 here lacks the packages.

## Past

- 2026-11-15: published the NIM work. Checked before pushing: neither saved key is
  in any commit, a fresh clone passes 69/69, and the remote tip matched. Hard-coded
  home paths in the issue-001 scripts were folded into a63dba1 before the first
  push, so no published commit carries them (later commits re-hashed: 01dfb55,
  2b9e02f, 7821346).
- 2026-11-15: README gained Results (one passing live run per preset, with what
  that does not show), Limitations, every env var the code reads, `koder/` in the
  layout, and a test command matching setup.sh's interpreter (fb8ebe6). `pdk/` now
  carries the upstream Apache-2.0 text and a NOTICE for `sky130.lib`. GitHub
  description rewritten to state the gate (gh repo edit).
- 2026-11-15: plans written for CI (`plans/001_ci`) and a real-run screenshot
  (`plans/002_dashboard_screenshot`), each with a prompt for its own session (761462e).
- 2026-10-20: super-vl is the spec default (01dfb55); NVIDIA_NIM_MODELS is
  probe-ordered (2b9e02f); Settings button in the header (7adbd63).
- 2026-10-19: NVIDIA NIM as default provider (e6eecfb), streamed OpenAI-compatible
  calls with empty-stream reporting (778b498); 8-model probe + live presets → `issues/001`.

## Present

- Provider `nvidia_nim`, model `nvidia/nemotron-3.5-super-vl-120b-a12b`, key saved in
  `.neuralforge/settings.json` (git-ignored). Server was **not running** on 2026-11-15.
- Evidence so far (details in `issues/001`, summarised in README Results):
  XOR 4/4 · Iris 150/150 · Attention 67/67 bit-exact on super-vl, one passing run each
  (2026-10-19/20). gpt-oss-20b failed attention. Generated RTL from those runs was not
  kept, so none of them can be re-checked yet. Cell counts lack the mapping mode.
- Nothing has run outside this Mac: no CI yet. The README has no image yet.
- Last push: fb8ebe6. Anything newer is local unless pushed since; check `git status -sb`.

## Future

1. `koder/plans/001_ci/INDEX.md`: GitHub Actions for the suite, failing on any
   skip (the simulator tests skip without Yosys), plus a frontend build. Run its
   prompt in a new session.
2. `koder/plans/002_dashboard_screenshot/INDEX.md`: a screenshot of a real XOR
   run, never the mock (its numbers are made up), with that run's RTL and verdict
   saved under `docs/runs/` so one result is re-checkable. The Settings drawer must
   stay out of frame, because it shows a key hint and a home path.
3. Not yet planned: repeated live runs per preset and model (pass rate, time,
   cells); a mutation test of the gate (broken variants of the reference RTL, kill
   rate); keeping every run's RTL.

Owner decisions pending: GitHub topics (not set; suggested `verilog llm-agents asic
skywater-pdk yosys hardware-verification`); capture tool for plan 002.

Next action: start a new session with the prompt in `koder/plans/001_ci/INDEX.md`.
