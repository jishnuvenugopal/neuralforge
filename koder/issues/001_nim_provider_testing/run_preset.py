"""Run one NeuralForge preset live against the running dashboard server.

Usage: python3.12 run_preset.py <xor_mlp|iris_classifier|attention_head> [timeout_s]

Connects to ws://127.0.0.1:8000/ws/design — the same endpoint and message
shape the dashboard uses ({"prompt": ...}) — then collects every server
message until "complete" or "error". Prints one JSON line with: synthesis
results, simulation verdicts, bit_exact (passed with pass_count ==
total_count == the reference's vector count), a per-type frame count, and a
timeline of interesting frames so stalls can be located precisely.
"""

import asyncio
import json
import sys
import time
import urllib.request
from pathlib import Path

# This file lives in koder/issues/<issue>/, three levels below the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

import websockets  # noqa: E402
from prompts import PRESET_PROMPTS  # noqa: E402

# Test-vector counts from the reference models (prompts.py verification section).
EXPECTED_VECTORS = {"xor_mlp": 4, "iris_classifier": 150, "attention_head": 67}


def _brief(kind, msg):
    """One short timeline line for a frame."""
    if kind == "status":
        return msg.get("message", "")[:110]
    if kind == "agent_message":
        return f"agent_message ({len(msg.get('text') or '')} chars)"
    if kind == "block_rtl":
        return f"block_rtl {msg.get('block_name')} ({len(msg.get('code') or '')} chars)"
    if kind == "block_synth_result":
        return f"synth {msg.get('block_name')} success={msg.get('success')}"
    if kind == "simulation_result":
        return f"sim {msg.get('verdict')} {msg.get('pass_count')}/{msg.get('total_count')}"
    if kind == "hardware_bom":
        return "hardware_bom"
    return kind


async def main():
    key = sys.argv[1]
    limit = float(sys.argv[2]) if len(sys.argv) > 2 else 1800.0
    port = sys.argv[3] if len(sys.argv) > 3 else "8000"
    prompt = PRESET_PROMPTS[key]

    health = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=10))
    summary = {
        "preset": key,
        "provider": health["provider"]["label"],
        "model": health["provider"]["model"],
        "expected_vectors": EXPECTED_VECTORS[key],
        "synth": [],
        "sims": [],
        "errors": [],
        "frame_counts": {},
        "timeline": [],
        "last_frame_at_s": 0.0,
        "complete": False,
        "iterations": 0,
        "bit_exact": False,
        "duration_s": 0.0,
    }

    t0 = time.perf_counter()
    async with websockets.connect(
        f"ws://127.0.0.1:{port}/ws/design", max_size=2**26, open_timeout=30
    ) as ws:
        await ws.send(json.dumps({"prompt": prompt}))
        while time.perf_counter() - t0 < limit:
            try:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=15.0))
            except asyncio.TimeoutError:
                continue  # quiet while the LLM thinks or EDA tools run; wait on
            kind = msg.get("type", "?")
            elapsed = round(time.perf_counter() - t0, 1)
            summary["frame_counts"][kind] = summary["frame_counts"].get(kind, 0) + 1
            summary["last_frame_at_s"] = elapsed
            # Timeline: everything except the noisiest generic statuses.
            if kind == "status":
                text = msg.get("message", "")
                if "iteration" in text or "Calling tool" in text:
                    summary["timeline"].append([elapsed, _brief(kind, msg)])
            else:
                summary["timeline"].append([elapsed, _brief(kind, msg)])
            summary["timeline"] = summary["timeline"][-60:]

            if kind == "block_synth_result":
                summary["synth"].append({
                    "module": msg.get("block_name"),
                    "success": msg.get("success"),
                    "stats": msg.get("stats"),
                    "sha256": (msg.get("sha256") or "")[:16],
                    "error": (msg.get("error") or "")[:300],
                    "log_tail": (msg.get("log_tail") or "")[-400:],
                })
            elif kind == "simulation_result":
                summary["sims"].append({
                    "verdict": msg.get("verdict"),
                    "passed": msg.get("passed"),
                    "pass_count": msg.get("pass_count"),
                    "total_count": msg.get("total_count"),
                    "sha256": (msg.get("sha256") or "")[:16],
                    "reason": (msg.get("reason") or "")[:200],
                })
            elif kind == "error":
                summary["errors"].append((msg.get("message") or "")[:300])
            elif kind == "complete":
                summary["complete"] = True
                summary["iterations"] = msg.get("iterations", 0)
                break
    summary["duration_s"] = round(time.perf_counter() - t0, 1)
    if not summary["complete"]:
        summary["errors"].append(f"run hit the {limit:.0f}s time limit before completing")

    expected = EXPECTED_VECTORS[key]
    summary["bit_exact"] = any(
        s["passed"] and s["pass_count"] == s["total_count"] == expected for s in summary["sims"]
    )
    if not summary["sims"]:
        summary["errors"].append("no simulation_result message received")
    print(json.dumps(summary))


asyncio.run(main())
