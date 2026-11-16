# 001 — Continuous integration for the test suite

Status: **planned** 2026-11-15 · run in its own session with the prompt at the bottom.

## Why

NeuralForge's central claim: a model-written design passes only if every output
matches an integer reference that the model never writes or grades. The 69 tests
encode that claim, including regression tests for the four exploits the first
gate let through. They have only ever run on one Mac. CI runs them on a machine
nobody here controls, on every push and pull request, and the README badge makes
the result visible to anyone reading the repo.

## Facts (checked 2026-11-15)

- Suite: `python3.12 -m unittest discover -s tests -v`: 69 tests, about 82 s,
  all pass and none skip on macOS with Yosys 0.63 and Icarus Verilog 13.0. It
  also passed in a fresh clone, but with the same already-equipped interpreter.
- Python packages: `backend/requirements.txt` (fastapi, uvicorn, openai,
  anthropic, numpy). torch and scikit-learn are needed only to retrain; the
  trained weights are committed in `backend/cache/`.
- The simulator tests skip themselves when the tools are missing:
  `tests/test_exploits_eda.py:23` (`HAVE_TOOLS`), with the guards at lines 72 and 119.
  A runner without Yosys would go green while testing nothing, so the job
  must fail on any skip.
- Synthesis tries full ABC mapping for 90 s, then retries with `abc -fast` for
  up to 300 s; simulation has 30 s (`backend/eda_tools.py:30-32`). The Yosys
  `stat` parser handles both the 0.4x table and the older "Number of" format
  (`backend/eda_tools.py:138`).
- Frontend: `npm run build` (Vite 6, React 19) in `frontend/`.

## To verify in the session

- The suite passes in a fresh venv that has only `backend/requirements.txt`.
- The runner's Yosys version. Ubuntu's apt package is older than 0.63, so read
  it with `yosys -V` rather than assuming it, and check that results still match.
- Whether any test depends on full versus `abc -fast` mapping. A slower runner
  may cross the 90 s limit.
- No test needs an API key (the provider tests should mock the network).
- `gh auth status` shows the `workflow` scope. Pushing `.github/workflows/`
  fails without it.

## Workflow

1. Run `open`. Create branch `ci/tests`; do not work on `main`.
2. Make a fresh venv in the scratchpad, install only `backend/requirements.txt`,
   and run the suite. If a package is missing, fix `requirements.txt`; do not
   change tests.
3. Write `.github/workflows/tests.yml`:
   - triggers: `push` to `main`, `pull_request`
   - `permissions: contents: read`; actions pinned to full commit SHAs;
     `timeout-minutes` on each job
   - job `tests` on `ubuntu-24.04`: checkout → setup-python 3.12 with pip cache
     → `sudo apt-get install -y yosys iverilog` → print `yosys -V` and
     `iverilog -V` → `pip install -r backend/requirements.txt` → run the suite
     with output saved to a log → fail if the log contains `skipped=`
   - job `frontend`: setup-node (LTS) → `npm ci` → `npm run build` in `frontend/`
4. Push the branch, open a PR, and read the run. If apt Yosys fails or gives
   different results, install a pinned YosysHQ OSS CAD Suite release on the
   runner instead, and write down why in the workflow and here.
5. Prove the skip guard: push a throwaway commit to the branch that removes the
   Yosys/Icarus install. The `tests` job must fail on the skip check. Revert it.
6. Add a workflow status badge at the top of `README.md`.
7. Ask the owner before merging. After the merge, confirm the run on `main` is green.
8. Record both run URLs below and run `close`.

## Done when

- Both jobs are green on `main` (run URL recorded here).
- A red run on the branch from step 5 shows the skip guard works (run URL recorded here).
- The README badge shows passing.
- The workflow holds no secrets, and nothing in it needs an API key.

## Risks

- A different Yosys may map to different cell counts. Pass or fail must not
  change. If a test asserts exact counts, report it instead of loosening it.
- Iris can take minutes to map. If CI time is a problem, record the durations
  before touching timeouts.

## Results

Local checks, 2026-11-16 (branch `ci/tests`):

- Fresh venv (python 3.12.12, only `backend/requirements.txt`; packages from
  PyPI/pip cache: fastapi 0.163.1, uvicorn 0.54.0, openai 3.51.0,
  anthropic 2.8.0, numpy 2.5.5): 69 tests OK in 81.4 s, none skipped. No
  change to `requirements.txt` needed.
- Same venv with `PATH=/usr/bin:/bin` (no Yosys/Icarus): `OK (skipped=11)`,
  exit 0. That is the false green; the workflow's skip check fails on it.
- No test needs an API key: provider tests use a temp settings dir and fake keys.
- `gh` token has the `workflow` scope.
- Actions pinned via `gh api`: checkout v7.0.1, setup-python v7.1.0, setup-node v7.1.0.
- Runner-sensitive assertions (report, do not loosen):
  `tests/test_exploits_eda.py:90` expects exactly 34 flip-flops for XOR;
  `:99` expects Iris to fall back to `abc -fast`, which needs full ABC to take
  more than 45 s (the test patches the 90 s limit to 45 s) on the runner.

CI runs: (fill in: green run on main, red skip-guard run, runner Yosys version, suite time)

## Prompt

```text
Run the `open` skill, then read koder/plans/001_ci/INDEX.md completely and
carry out its Workflow on a new branch `ci/tests`.

Goal: NeuralForge's 69 tests, including the verification-gate exploit tests,
run on GitHub Actions on every push and pull request, and the job fails if any
test is skipped. The simulator tests skip themselves when Yosys or Icarus is
missing, which would otherwise make CI green while testing nothing. A second
job builds the frontend.

Work from facts, not the plan's summaries: run the suite in a fresh venv that
has only backend/requirements.txt, read the runner's actual Yosys version, and
check `gh auth status` for the `workflow` scope before pushing.

Do not change tests or loosen timeouts to make CI pass. If something differs on
the runner, record it in the plan and tell me. Ask me before downloading
anything locally, before pushing, and before merging.

Done means: both jobs green on main, a deliberately red run on the branch that
proves the skip guard, a passing README badge, and both run URLs recorded in
the plan's Results section. Finish with the `close` skill.
```
