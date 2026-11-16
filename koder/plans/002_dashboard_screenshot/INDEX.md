# 002 — Dashboard screenshot from a real verified run

Status: **done** 2026-11-16 on branch `docs/screenshot`. Results below.

## Why

The README describes the dashboard but shows none of it. One image of a real
run, ending in a bit-exact verdict, shows in seconds what the project does:
request, generated RTL, SkyWater-130 synthesis and simulation checked against
the reference. Saving that run's RTL and verdict next to the image also makes
one result re-checkable. The README currently says no live run can be re-checked.

## Facts (checked 2026-11-15)

- Start: `NEURALFORGE_NO_BROWSER=1 bash start.sh` serves http://localhost:8000.
  The UI always starts in dark mode. The server was **not running** on 2026-11-15.
- `?mock=true` replays a canned sequence (`frontend/src/App.jsx:4-50`) whose
  numbers are made up: 463 cells, 9,184.3 µm². The real XOR run had 3,978 cells.
  Use mock only to frame the shot. **Never publish it as a result.**
- The real XOR preset on `nvidia/nemotron-3.5-super-vl-120b-a12b` passed 4/4 in
  169 s on 2026-10-20. It needs the NIM key already saved in
  `.neuralforge/settings.json` (git-ignored).
- `/api/settings` never returns the key, but it does return `key_hint` (the last
  4 characters) and `settings_path` (an absolute path in the home folder)
  (`backend/settings.py:156-186`). The Settings drawer displays both
  (`frontend/src/Settings.jsx:142-143, 289`). **The drawer must be closed in every shot.**
- Installed here: Brave and Safari (no Chrome), node, npx, ffmpeg. Playwright is
  not installed. `.claude/launch.json` has a `neuralforge` entry for :8000.

## Decision for the owner (ask at step 3)

Capture tool:
- **(a) `playwright-core` driving the installed Brave (recommended).** It is
  scripted, repeatable and sets an exact viewport. It downloads only the npm
  package, not a browser, and can record the run's WebSocket frames, which
  contain the RTL.
- **(b) macOS `screencapture -l` of a Safari window.** It downloads nothing, but
  it is manual and doesn't capture the RTL.
- **(c) Playwright with its own Chromium.** Same as (a) plus a browser download.

## Workflow

1. Run `open`. Create branch `docs/screenshot`.
2. Start the server and check `curl -s localhost:8000/health`. Confirm
   `/api/settings` holds no key value (only `has_key` and `key_hint`).
3. Ask the owner which capture tool to use. Ask before any download.
4. At a 1440×900 viewport in dark mode, with the Settings drawer closed, run
   the real **XOR MLP** preset from the dashboard and wait for the simulation
   verdict (4/4). Record the run's WebSocket frames, or otherwise get its RTL.
   If the run fails, retry once; if it fails again, stop and report. Do not
   substitute the mock.
5. Capture the finished dashboard (and, if it reads well, a second shot of the
   synthesis panel). Zoom in on each image to confirm it shows no key hint,
   home path or other personal detail.
6. Save the images under `docs/images/` (optimised, ideally under 400 KB each).
   Save the run under `docs/runs/<date>_xor_super-vl/`: the RTL, the verdict
   (pass count, total), synthesis stats and the code's sha256.
7. Embed the main image in `README.md` below the intro. Caption it with the
   date, model, preset and this run's own numbers. They will not match the
   Results table from October, so do not reuse those. Link the saved run, and
   update the Results bullet that says no run can be re-checked so it points to
   this one.
8. Optional: a sped-up GIF of the same real run made with ffmpeg, under 3 MB.
9. Ask the owner before pushing. After pushing, open the GitHub page and check
   that the image renders. Run `close`.

## Done when

- The README on GitHub shows the image of a real run, with a caption whose
  numbers match the files in `docs/runs/`.
- Anyone can re-run the gate on the saved RTL and get the same verdict and sha256.
- No key hint, home path or other personal detail is visible in any image.

## Results

Capture tool: (a) `playwright-core` 1.65.1 (npm, scratchpad only) driving the
installed Brave headless, 1440×900 viewport at 2× scale, dark mode. The script
recorded every WebSocket frame and refused to save any shot while the Settings
drawer was open or a protected value (settings path, home folder, key hints)
was inside the frame; tested both ways before the real run.

Published run (run 3), 2026-11-16 02:36:58 UTC, XOR MLP preset,
`nvidia/nemotron-3.5-super-vl-120b-a12b` on NVIDIA NIM:
- 4/4 bit-exact, module `mlp_xor_2_8_1`, 4 agent iterations, 306.3 s from clicking Run to the `complete` message.
- 4,111 cells, 0 flip-flops (combinational design), 30,063.8 µm², 11,392 wires,
  full ABC mapping.
- sha256 `5b07cf23951f4a31a6a45ed6392af0fcac0bacff0b80f6593641dd214f20aa9c`.
- Saved: `docs/runs/2026-11-16_xor_super-vl/` (`design.v`, `run.json`).
  `docs/runs/recheck.py` reproduces sha256, cells, area and 4/4; changing one
  weight (-126 → -125) gives a different sha256, 3/4 and exit 1.
- Images: `docs/images/dashboard_xor_2026-11-16.png` (1440×1320, 367 KB) and
  `docs/images/synthesis_xor_2026-11-16.png` (996×420, 83 KB). Both checked
  zoomed in: no key hint, drawer, home path or temp path.

Other runs this session (not published): run 1 was stopped by the capture
script's own guard on its first frame (too strict: it flagged the closed drawer's
off-screen text); run 2 passed 4/4 (3,998 cells, 109 s) but the 1440×900 viewport
cut off the verdict panel, and the browser had closed, so a third real run was
made with full-page capture. Mock replay never used.

Framing: the page is 6,086 px tall because the workspace stretches to the agent
log, so the main image is the top 1,320 px of the full page. It is cut just above
the Simulation tab's Transcript box, which prints the simulator's macOS temp
folder path. The optional GIF was skipped: its frames would need the same
per-frame check for that path.

## Prompt

```text
Run the `open` skill, then read koder/plans/002_dashboard_screenshot/INDEX.md
completely and carry out its Workflow on a new branch `docs/screenshot`.

Goal: the README shows a screenshot of a real NeuralForge run (XOR preset)
ending in its bit-exact simulation verdict, and that run's RTL and verdict are
saved under docs/runs/ so anyone can re-check it.

Rules: never use the ?mock=true replay as a result, because its numbers are
made up. Keep the Settings drawer closed in every shot, because it shows the
last 4 characters of the API key and a home-folder path. Zoom in on each image
before saving it to confirm nothing personal shows. Caption the image with
this run's own date, model and numbers.

Ask me which capture tool to use (the plan recommends playwright-core driving
the installed Brave), and ask before any download and before pushing.

Done means: the image renders on the GitHub README, its caption matches the
files in docs/runs/, and the plan's Results section is filled in. Finish with
the `close` skill.
```
