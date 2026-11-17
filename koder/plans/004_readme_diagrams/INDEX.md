# 004 — README diagrams

Status: **both passes committed** 2026-11-16 · branch `docs/diagrams` (first
pass `95ebef9`; PR #4 open, not merged)

## Result

Four SVGs added and wired into the README (overview under the intro, run flow
in a new "How it works" section, architecture above "Project layout", trust
boundary at the top of "How a design is verified"). The long env-var table is
folded into a `<details>` block. Checked by rendering each SVG with
`rsvg-convert` at 1200 and 830 px and by measuring every text line against its
box with the macOS system fonts (SF Pro, SF Mono): no line within 12 units of
its box edge. Not yet seen on github.com itself.

### Second pass: the agent side, and a README reworked for first-read clarity

The first four images explain the hardware pipeline and the gate. The agent
side (the loop, what the model is given, the provider layer) and the evidence
behind a verdict were only readable in the code. Four more SVGs cover them, and
the README is reordered so the pictures come before the configuration detail.

- README: an "At a glance" table under the intro; a "Techniques and where they
  live" table (technique, file, the test that checks it); a jump line; new
  sections "The agent loop" (with "What the model sees"), "Evidence" (diagram,
  "Tests and CI", then the existing Results one level down) and "Configuration"
  (the provider table and environment variables, moved down unchanged); a
  "Provider layer" subsection under Architecture. No text was dropped; the
  test-running paragraph moved from "How a design is verified" to "Evidence".
- Two stale docstrings that still said "Gemini" (`backend/prompts.py`,
  `handle_function_call` in `backend/main.py`) now say what the code does. The
  system prompt and tool declarations are untouched, so the model sees the
  same text as in the saved run.
- Docs only, no behaviour change: the suite still passes (75 tests, none
  skipped, Yosys and Icarus installed). Not yet seen on github.com itself.

## Why

The README explains the project in prose and one screenshot. A reader has to
read four sections to see the shape of it: what runs where, what happens in a
run, and why the verdict can be trusted. Four images can carry that at a glance.

## Decisions

- Hand-written SVG in `docs/images/`. GitHub renders it in the README, it stays
  sharp at any width, and it diffs as text. No Mermaid, no generated PNGs.
- Each SVG draws its own dark background (the dashboard's palette), so it reads
  the same in GitHub's light and dark themes. System fonts only; no CSS
  variables, `foreignObject` or external fonts. Text is at least 14 units in a
  1200-wide viewBox, about 10 px at GitHub's README width.
- Facts come from the code, not the README prose:
  - flow and limits: `backend/main.py` (`run_agent_loop`, up to 15 model turns,
    up to 2 nudges per pending tool);
  - gate checks: `backend/verifier.py` (`scan_source`, `make_testbench`,
    `parse_results`, `check_netlist`, `Ledger`) and `backend/eda_tools.py`
    (`synthesize`, `simulate_reference`).
- No result numbers in the diagrams. The Results table stays the one place for
  them, with provider, model and date. Vector counts (4, 150, 67) are part of
  the presets, so they may appear.
- GDS is shown as optional; the published results cover synthesis and
  simulation only.
- Second pass, same rules, plus:
  - The sequence diagram takes its facts from `run_agent_loop` and
    `handle_function_call`, not from `run_flow.svg`: the loop stops right after
    a passing (or unverified) `simulate_verilog`, with no closing model turn;
    nudged turns count toward the 15; `analyze_model` returns only an
    instruction, and the BOM is read from fenced JSON in the model's text. It
    shows lanes and WebSocket event names and leaves the gate checks to
    `run_flow.svg`.
  - The evidence diagram shows the chain (tests, CI, real runs), not results:
    no pass counts, cell counts or times, and no test count either (the
    workflow's own comment says 69 while the suite has 75, which is why).
  - Tables and prose claim only what the code does: tool arguments are
    JSON-parsed, not schema-validated; the BOM is parsed from text, not
    graded; the history is an append-only list. The loop's turn cap and nudges
    are marked as having no unit test.

## Images

| File | Shows | README section |
|---|---|---|
| `docs/images/overview.svg` | request → model → synthesis gate → reference gate → verified RTL; the three presets | top, under the intro |
| `docs/images/run_flow.svg` | one run step by step, with the retry loop, the no-preset branch and optional hardening | How it works |
| `docs/images/architecture.svg` | browser, FastAPI server, modules, model provider, EDA tools | Architecture (next to Project layout) |
| `docs/images/trust_boundary.svg` | what the model writes vs what NeuralForge writes; the four exploits and what closes each | How a design is verified |
| `docs/images/agent_loop.svg` | one clean run as messages between dashboard, agent loop, model and gate; the three ways a step goes wrong | The agent loop |
| `docs/images/prompt_context.svg` | what is in the conversation before turn 1, what each turn adds, what a tool result carries, what is never sent | The agent loop → What the model sees |
| `docs/images/provider_layer.svg` | the three calls the loop makes, the two protocol implementations in `llm.py`, the three provider kinds, where settings come from | Architecture → Provider layer |
| `docs/images/evidence.svg` | the test files and what each covers, the two CI jobs and the fail-on-skip step, live runs and the re-checkable saved run | Evidence |

## Checks

- `python3.12 koder/plans/004_readme_diagrams/check_svg.py docs/images/*.svg`
  measures every text line in the widest of SF Pro, Helvetica and Arial (SF
  Mono and Menlo for code) and fails on a line within 12 units of its box, on
  overlapping text, and on text crossed by a line. It needs Pillow (not in
  `backend/requirements.txt`) and reads macOS font paths.
  The four second-pass SVGs pass. On the first four it reports two things that
  are not faults: the rotated retry label in `run_flow.svg` (rotation is not
  modelled) and `+ module name` in `trust_boundary.svg` at exactly 12.
- Render each SVG with `rsvg-convert -w 830` and inspect for clipped or
  overlapping text.
- Every image path in the README exists; alt text describes the content.
- Docs only: the test suite is not affected.
