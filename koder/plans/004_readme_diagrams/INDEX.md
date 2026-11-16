# 004 — README diagrams

Status: **drawn, not committed** 2026-11-16 · branch `docs/diagrams`

## Result

Four SVGs added and wired into the README (overview under the intro, run flow
in a new "How it works" section, architecture above "Project layout", trust
boundary at the top of "How a design is verified"). The long env-var table is
folded into a `<details>` block. Checked by rendering each SVG with
`rsvg-convert` at 1200 and 830 px and by measuring every text line against its
box with the macOS system fonts (SF Pro, SF Mono): no line within 12 units of
its box edge. Not yet seen on github.com itself.

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

## Images

| File | Shows | README section |
|---|---|---|
| `docs/images/overview.svg` | request → model → synthesis gate → reference gate → verified RTL; the three presets | top, under the intro |
| `docs/images/run_flow.svg` | one run step by step, with the retry loop, the no-preset branch and optional hardening | How it works |
| `docs/images/architecture.svg` | browser, FastAPI server, modules, model provider, EDA tools | Architecture (next to Project layout) |
| `docs/images/trust_boundary.svg` | what the model writes vs what NeuralForge writes; the four exploits and what closes each | How a design is verified |

## Checks

- Render each SVG with `rsvg-convert -w 830` and inspect for clipped or
  overlapping text.
- Every image path in the README exists; alt text describes the content.
- Docs only: the test suite is not affected.
