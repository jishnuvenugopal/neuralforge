"""NVIDIA NIM model probe: one add_numbers tool-call round trip.

Usage: python3.12 probe.py <model_id>

Uses backend/settings.py + backend/llm.py exactly as the app does:
settings.provider_config("nvidia_nim"), dataclasses.replace(config, model=...),
llm.open_conversation with one add_numbers tool. The model must call the tool
with 1234 and 8765, receive the sum, and state 9999.

Prints one JSON line:
  pass, tool_call, args_ok, answer_ok, t_first_tool_s (send -> first turn with
  the tool call), t_total_s (full round trip), error ("" when none).
Timings are -1 when the step never happened.
"""

import dataclasses
import json
import sys
import time
from pathlib import Path

# This file lives in koder/issues/<issue>/, three levels below the repo root.
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "backend"))

import llm  # noqa: E402
import settings as nf_settings  # noqa: E402

A, B = 1234, 8765

TOOLS = [
    {
        "name": "add_numbers",
        "description": "Add two integers and return their sum.",
        "parameters": {
            "type": "object",
            "properties": {
                "a": {"type": "integer", "description": "first addend"},
                "b": {"type": "integer", "description": "second addend"},
            },
            "required": ["a", "b"],
        },
    }
]


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def main():
    model = sys.argv[1]
    out = {
        "model": model,
        "pass": False,
        "tool_call": False,
        "args_ok": False,
        "answer_ok": False,
        "t_first_tool_s": -1,
        "t_total_s": -1,
        "final_text": "",
        "error": "",
    }
    t0 = time.perf_counter()
    try:
        config = dataclasses.replace(nf_settings.provider_config("nvidia_nim"), model=model)
        conv = llm.open_conversation(
            config,
            "You are a precise assistant. Use the add_numbers tool for every arithmetic question.",
            TOOLS,
        )
        conv.add_user_text(
            f"Compute {A} + {B}. Call the add_numbers tool with a={A} and b={B} to get the sum, "
            "then state the final answer as a single number."
        )
        turn = conv.next_turn()
        out["t_first_tool_s"] = round(time.perf_counter() - t0, 2)

        call = next((c for c in turn.tool_calls if c.name == "add_numbers"), None)
        if call is None:
            out["error"] = "no add_numbers tool call in the first turn"
            out["final_text"] = " ".join(turn.texts)[:200]
        else:
            out["tool_call"] = True
            if call.error:
                out["error"] = f"tool arguments invalid: {call.error}"
            else:
                got = sorted(_int(call.args.get(k)) for k in ("a", "b"))
                out["args_ok"] = got == sorted([A, B])
                # Honest tool result: the sum of whatever the model passed.
                results = []
                for c in turn.tool_calls:
                    if c.name == "add_numbers" and not c.error:
                        results.append((c, {"sum": _int(c.args.get("a")) + _int(c.args.get("b"))}))
                    else:
                        results.append((c, {"error": c.error or f"unexpected tool {c.name}"}))
                conv.add_tool_results(results)
                turn2 = conv.next_turn()
                out["t_total_s"] = round(time.perf_counter() - t0, 2)
                text = " ".join(turn2.texts)
                out["final_text"] = text[:200]
                out["answer_ok"] = "9999" in text
                out["pass"] = out["args_ok"] and out["answer_ok"]
    except Exception as e:  # LLMError and anything else; report, don't crash
        out["t_total_s"] = round(time.perf_counter() - t0, 2)
        out["error"] = f"{type(e).__name__}: {e}"[:300]
    print(json.dumps(out))


if __name__ == "__main__":
    main()
