# NeuralForge — operator state

Project: NeuralForge — LLM agent that designs SkyWater-130nm Verilog RTL from
ML presets (FastAPI backend + React dashboard, both served at http://127.0.0.1:8000).
Run: `NEURALFORGE_NO_BROWSER=1 bash start.sh` · Tests: `python3.12 -m unittest tests.test_providers`
(Use python3.12 for anything importing backend/; plain python3 lacks anthropic under xargs.)

## Past

- 2026-10-20: intended work committed — super-vl in the model list (aaa1786),
  labelled Settings button in the header (7adbd63), koder scaffold + this file.
- 2026-10-20 (later): both Future items done — spec default is now super-vl (01dfb55,
  test + README updated) and NVIDIA_NIM_MODELS is probe-ordered with lightning-30b
  added (2b9e02f); fresh installs no longer start on the broken kimi ID. 69 tests OK.
- NVIDIA NIM wired as default provider (e6eecfb); streamed OpenAI-compatible calls +
  empty-stream reporting (778b498); Safari-safe serving on :8000 (aa7b596); dark-mode
  default (aa8aabb); model selectors (aad8222).
- NIM key saved and connection-tested from Settings (`.neuralforge/settings.json`,
  gitignored); live `/models` returns 81 models.
- 2026-10-19 session: 8-model NIM tool-calling probe + live preset runs → `issues/001`.

## Present

- Active provider `nvidia_nim`, active model `nvidia/nemotron-3.5-super-vl-120b-a12b`
  (saved in `.neuralforge/settings.json`); server healthy on :8000 as of 2026-10-20.
- Probe verdicts (2 runs/model; scripts copied to `issues/001`):
  - PASS: `openai/gpt-oss-20b` 2.3–3.5 s · `nvidia/nemotron-3.5-super-vl-120b-a12b` 2.1–11.9 s ·
    `nvidia/nemotron-3-ultra-550b-a55b` 12.6–24.9 s · `nvidia/nemotron-3.5-lightning-30b-a3b` 93.6–184.5 s
    (high variance) · `z-ai/glm-5.3` 149.6–186.2 s · `z-ai/glm-5.3-flash` 201.2–278.9 s
  - FAIL: `deepseek-ai/deepseek-v4.1-flash` (2/3 runs: zero output >10 min) ·
    `moonshotai/kimi-k2.6` (listed by /models but the inference endpoint rejects the ID;
    was the spec default until 01dfb55, now last in NVIDIA_NIM_MODELS).
- Live presets on super-vl (via `/ws/design`) — ALL BIT-EXACT:
  XOR 4/4 in 168.7 s (sha256 2c0b05f2b2893362) · Iris 150/150 in 647.4 s
  (sha256 80ae993b203e0828) · Attention 67/67 in 1316.4 s (sha256 78d51223be9430e3,
  491948 cells). Turns run 200–650 s each on NIM today.
  Fallback check: gpt-oss-20b failed attention outright (syntax errors, garbled tool
  name, 0/2 syntheses) — probe speed does not predict preset quality. See issues/001.

## Future

- Server left running on :8000 (scratch :8001 shut down); it has died between
  sessions before — check `/health` first if presets instantly fail.
