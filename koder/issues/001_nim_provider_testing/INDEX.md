# 001 — NVIDIA NIM provider testing (model probe + live presets)

Opened: 2026-10-19 · Status: **done** — recommendation enacted: super-vl is the spec
default (01dfb55) and leads NVIDIA_NIM_MODELS (2b9e02f); results committed 2026-10-20.

## Goal

Pick a default NIM model for NeuralForge: verify the tool-calling round trip on the
shortlist, then run the XOR / Iris / Attention presets live on the dashboard server and
confirm bit-exact simulation. Nothing committed; results recorded here.

## Method

- `probe.py` (copied here): `settings.provider_config("nvidia_nim")` →
  `dataclasses.replace(config, model=…)` → `llm.open_conversation` with one
  `add_numbers` tool; model must call it with 1234 and 8765, receive the honest sum,
  and state 9999. Measures t→first tool call and total.
  Run: `python3.12 probe.py <model_id>` (2 runs per model; failures re-checked once).
- `run_preset.py` (copied here): drives the real dashboard flow —
  `ws://127.0.0.1:8000/ws/design`, message `{"prompt": <preset>}` — and reports
  synthesis + simulation verdicts; `bit_exact` = passed with pass_count == total_count
  == the reference's vector count (4 / 150 / 67). v2 records a frame timeline.
  Run: `python3.12 run_preset.py <preset_key> [limit_s]`.

## Probe results (2026-10-19, NIM latency high all day)

| Model | Verdict | t→1st tool (s, run1/run2) | Total (s) |
|---|---|---|---|
| openai/gpt-oss-20b | PASS 2/2 | 1.4 / 2.4 | 2.3 / 3.5 |
| nvidia/nemotron-3.5-super-vl-120b-a12b | PASS 2/2 | 1.3 / 10.5 | 2.1 / 11.9 |
| nvidia/nemotron-3-ultra-550b-a55b | PASS 2/2 | 23.1 / 7.4 | 24.9 / 12.6 |
| nvidia/nemotron-3.5-lightning-30b-a3b | PASS 2/2 | 18.4 / 118.8 | 93.6 / 184.5 |
| z-ai/glm-5.3 | PASS 2/2 | 108.6 / 84.6 | 186.2 / 149.6 |
| z-ai/glm-5.3-flash | PASS 2/2 | 138.0 / 102.9 | 278.9 / 201.2 |
| deepseek-ai/deepseek-v4.1-flash | FAIL | 298.6 (1 run) | 592.8; 2 runs zero output >10 min |
| moonshotai/kimi-k2.6 | FAIL | — | ID rejected by endpoint in ~0.4 s, 3/3 runs |

Notes:
- `moonshotai/kimi-k2.6` IS in the live `/models` listing (81 models) — listed but not
  servable. It was the hardcoded spec default (`backend/settings.py`,
  PROVIDERS["nvidia_nim"]["model"]) until 2026-10-20, when fresh installs were moved
  onto super-vl (01dfb55).
- Recommendation: `nvidia/nemotron-3.5-super-vl-120b-a12b` (120B-A12B at 2–12 s round
  trips). Fallbacks: `openai/gpt-oss-20b` (fastest, 20B), `nemotron-3-ultra-550b`
  (strongest, 12–25 s).

## Live presets (model: nvidia/nemotron-3.5-super-vl-120b-a12b)

| Preset | Result | Detail |
|---|---|---|
| xor_mlp | **BIT-EXACT PASS** | 4/4 vectors, 1 synthesis (3978 cells), 4 iterations, 168.7 s, sha256 2c0b05f2b2893362 |
| iris_classifier | **BIT-EXACT PASS** | 150/150 vectors, 1 synthesis (21120 cells), 3 iterations, 647.4 s, sha256 80ae993b203e0828. Turn times 196 s + 354 s — the earlier "stalls" were just the 540 s driver cap, not a model failure |
| attention_head | **BIT-EXACT PASS** | 67/67 vectors, 1 synthesis (491948 cells, 2.77 mm²), 3 iterations, 1316.4 s, sha256 78d51223be9430e3. Turn times 648 s + 411 s; clean run, no nudges. (An earlier 1740 s attempt had its first synthesis fail and was cut off mid-fix — re-run passed outright.) |

Fallback comparison on attention (isolated :8001 instance, own NEURALFORGE_HOME):
`openai/gpt-oss-20b` FAILED — 2 Verilog submissions with syntax errors, one garbled tool
name (`synthesize_verilog<|channel|>json`, harmony channel leakage in the tool call),
output bloating to 46666 chars, 0/2 syntheses ok, cap hit at 2700 s. Preset turns were
NOT faster than super-vl either (iteration 1: 718 s) — NIM's per-token throughput
dominates preset turn time, so probe speed does not predict preset speed. gpt-oss-20b
stays a probe-speed footnote, not a default candidate.

**Verdict: `nvidia/nemotron-3.5-super-vl-120b-a12b` — all three presets bit-exact,
first-try synthesis on each passing run. Keep as NIM default (already active in
.neuralforge/settings.json).**

Driver v2/v3 add a frame timeline, synth error/log_tail capture, and a port argument
(`run_preset.py <preset> [limit_s] [port]`).

## Appendix

- Server died between sessions once (nothing on :8000 despite earlier health OK);
  restarted with `NEURALFORGE_NO_BROWSER=1 bash start.sh`. If presets "instantly
  fail", check health first: `curl -s http://127.0.0.1:8000/health`.
- Scratch dir during the session: `/tmp/nf-nim-probe/` (ephemeral; scripts copied here).
