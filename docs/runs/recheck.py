"""Re-run NeuralForge's verification gate on a saved run.

    python3.12 docs/runs/recheck.py docs/runs/<run folder>

Reads `design.v` and `run.json` from the folder, checks the code's sha256,
synthesizes it with Yosys against SkyWater 130, and simulates it with Icarus
against the integer reference of the preset named in `run.json`. The testbench
is written by NeuralForge from the reference, never by the model. Exits 0 only
if the sha256 matches and the verdict matches the one recorded.
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import eda_tools  # noqa: E402
import verifier  # noqa: E402
from golden import load_network  # noqa: E402


def main(folder: str) -> int:
    with open(os.path.join(folder, "run.json")) as f:
        run = json.load(f)
    with open(os.path.join(folder, "design.v")) as f:
        code = f.read()

    digest = verifier.sha256(code)
    print(f"sha256      {digest}  ({'matches' if digest == run['sha256'] else 'DIFFERS from'} run.json)")

    synth = eda_tools.synthesize(code, run["module"])
    if not synth["success"]:
        print("synthesis   FAILED:", synth.get("error"))
        return 1
    stats = synth["stats"]
    print(f"synthesis   ok: {stats['total_cells']} cells, {stats['flip_flops']} flip-flops, "
          f"{stats['area_um2']:.1f} um^2, abc {stats['abc_mode']}")

    sim = eda_tools.simulate_reference(code, run["module"], load_network(run["preset"]))
    passed = bool(sim.get("success") and sim.get("passed"))
    print(f"simulation  {sim.get('pass_count', 0)}/{sim.get('total_count', 0)} "
          f"{'passed' if passed else 'FAILED'}: {sim.get('reason', '')}")

    expected = run["verdict"]
    same = (passed == expected["passed"]
            and sim.get("pass_count") == expected["pass_count"]
            and sim.get("total_count") == expected["total_count"])
    print(f"verdict     {'matches' if same else 'DIFFERS from'} run.json "
          f"({expected['pass_count']}/{expected['total_count']})")
    return 0 if same and digest == run["sha256"] else 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1]))
