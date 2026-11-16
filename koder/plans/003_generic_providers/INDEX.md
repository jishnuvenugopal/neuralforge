# 003 — Generic model providers, and the model recorded with every result

Status: **done** 2026-11-16 · merged in PR #3 (`fac461a`); CI green on main (run 43796871210).

## Why

The owner asked for provider configuration that is generic rather than tied to
one gateway: keep NVIDIA NIM, drop the named ZYT Foundry provider, and let any
OpenAI-compatible (or Anthropic-compatible) endpoint be set from the environment
with a key, base URL and model. Results must state clearly which provider and
model produced them, in the README and in saved runs.

## Decisions

1. **Providers:** `nvidia_nim` (default), `openai_compatible`,
   `anthropic_compatible`. `zyt_foundry` is removed from the code. ZYT Foundry
   still works as an OpenAI-compatible endpoint with its base URL.
2. **Environment variables** (saved Settings still win over them):
   - `NEURALFORGE_PROVIDER` picks the provider when Settings has not saved one.
     Without it, setting only `OPENAI_*` would be read but never used.
   - NIM: `NVIDIA_API_KEY`, `NVIDIA_NIM_MODEL`, `NVIDIA_NIM_BASE_URL`.
   - OpenAI-compatible: `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`
     (the names the OpenAI SDK and most tools already use).
   - Anthropic-compatible: `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`, `ANTHROPIC_MODEL`.
   - Base URL order for editable providers: saved, then env, then default.
3. **Old settings files:** a saved `zyt_foundry` entry is left untouched in
   `settings.json` and ignored; `active_provider: zyt_foundry` falls back to the
   default. Its key is **not** copied into `openai_compatible`, whose default URL
   is api.openai.com, so the key would go to the wrong host.
4. **Recording the model:** the backend snapshots the provider config once at run
   start, sends it as a `run_info` WebSocket message (provider id, label, model) and
   repeats it in `complete`, so a saved run carries the model in structured fields.
   (`simulation_result` comes from the tool handler, which has no config.) Keys, key
   hints and base URLs are never included.
   Published `run.json` files get explicit `provider` and `model` fields. The README
   Results table gets a Model column.
5. **Out of scope:** saving every run to disk automatically (STATE Future item).

## Checks

- Tests: ZYT tests ported to NIM / OpenAI-compatible, not deleted; the env names
  cleared in `setUp` are derived from `PROVIDERS`; new tests for env-only setup and
  for a stale `zyt_foundry` settings file.
- `git grep -i zyt` hits only history (`koder/issues`, plans, STATE Past).
- Every variable in the README `export` block is read by `backend/`.

## Results

- `backend/settings.py`: ZYT removed; `openai_compatible` and `anthropic_compatible`
  read `OPENAI_*` / `ANTHROPIC_*`; `NEURALFORGE_PROVIDER` selects the provider; base
  URL is saved → env → default; `public_view` exposes `url_env` / `model_env` names.
- `backend/main.py`: `run_info` at run start, provider/model repeated in `complete`.
- Dashboard: provider · model badge in the Design workspace; Settings lists three
  providers and names the env variables for the selected one.
- `docs/runs/2026-11-16_xor_super-vl/run.json`: `provider`, `provider_label`, `model`
  added (taken from the run's own recorded status message); `recheck.py` prints them
  and still reproduces sha256 and 4/4.
- README: generic env block, Results table with a Provider · model column (October
  rows dated 19–20 Oct where the record has no per-preset date; XOR is 20 Oct per
  plan 002), and a "How the model is recorded" note.
- Tests: 75 pass (was 71). New: generic provider list, env-only OpenAI-compatible
  setup, saved settings beat env, unknown `NEURALFORGE_PROVIDER`, stale `zyt_foundry`
  settings file, and `run_info`/`complete` carrying the start-of-run model with no
  key, key hint or base URL.
- End to end, no external calls: a server on :8010 with an empty `NEURALFORGE_HOME`
  and only `NEURALFORGE_PROVIDER=openai_compatible` + `OPENAI_*` (test key, unreachable
  local URL) reported itself configured; a run showed the
  "OpenAI-compatible · test-model" badge, then the expected "Could not reach" error.
- The owner's saved ZYT key stays in `.neuralforge/settings.json`, unused. To keep
  using ZYT Foundry, choose OpenAI-compatible with base URL `https://foundry.zyt.app/v1`.
