import os
import json
import re
import base64
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from google import genai
from google.genai import types

from eda_tools import (
    synthesize,
    simulate_reference,
    generate_netlist_svg,
    check_tools,
    prepare_librelane_design,
    run_librelane_flow,
)
from golden import load_network, network_params, port_contract, tensor_params
from prompts import SYSTEM_PROMPT, TOOL_DECLARATIONS, PRESET_PROMPTS
from verifier import Ledger

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")

app = FastAPI(title="AI Chip Architect")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")
LIBRELANE_AUTO_HARDEN = os.environ.get("LIBRELANE_AUTO_HARDEN", "").lower() in {
    "1",
    "true",
    "yes",
    "on",
}

# Lazy init — don't crash on import if no key yet
client = None

def get_client():
    global client
    if client is None:
        if not GEMINI_API_KEY:
            raise ValueError("Set GEMINI_API_KEY environment variable")
        client = genai.Client(api_key=GEMINI_API_KEY)
    return client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def ws_send(websocket: WebSocket, data: dict):
    """Send JSON message to WebSocket client, silently handle errors."""
    try:
        await websocket.send_json(data)
    except Exception:
        pass


async def maybe_run_librelane_hardening(websocket: WebSocket, module_name: str, verilog_code: str) -> dict:
    """Optionally run LibreLane hardening after simulation passes."""
    if not LIBRELANE_AUTO_HARDEN:
        return {"status": "skipped", "reason": "LIBRELANE_AUTO_HARDEN is disabled"}

    tools = check_tools()
    if not tools.get("nix-shell") or not tools.get("librelane_shell"):
        reason = "LibreLane auto-hardening is enabled, but Nix or LibreLane is not installed yet."
        await ws_send(websocket, {"type": "status", "message": reason})
        await ws_send(
            websocket,
            {
                "type": "hardening_result",
                "success": False,
                "gds_png": "",
                "error": reason,
            },
        )
        return {"status": "blocked", "reason": reason, "tools": tools}

    await ws_send(
        websocket,
        {
            "type": "status",
            "message": f"Starting LibreLane hardening for {module_name}...",
        },
    )

    prep_result = prepare_librelane_design(module_name=module_name, verilog_code=verilog_code)
    if not prep_result.get("success"):
        error_message = prep_result.get("error", "Failed to prepare LibreLane design workspace")
        await ws_send(
            websocket,
            {
                "type": "hardening_result",
                "success": False,
                "gds_png": "",
                "error": error_message,
            },
        )
        return {"status": "error", "error": error_message}

    flow_result = run_librelane_flow(
        design_dir=prep_result["design_dir"],
        config_json_path=prep_result["config_json_path"],
    )
    artifacts = flow_result.get("artifacts", {})

    await ws_send(
        websocket,
        {
            "type": "hardening_result",
            "success": flow_result.get("success", False),
            "gds_png": artifacts.get("png_base64", ""),
            "gds_path": artifacts.get("gds_path", ""),
            "def_path": artifacts.get("def_path", ""),
            "report_path": artifacts.get("report_path", ""),
            "log_tail": flow_result.get("log_tail", ""),
            "error": flow_result.get("error", ""),
        },
    )

    if flow_result.get("success"):
        await ws_send(
            websocket,
            {
                "type": "status",
                "message": f"LibreLane hardening finished for {module_name}.",
            },
        )
    else:
        await ws_send(
            websocket,
            {
                "type": "status",
                "message": f"LibreLane hardening failed for {module_name}: {flow_result.get('error', 'Unknown error')}",
            },
        )

    return flow_result


WEIGHT_FILE_MAP = {
    "xor": "xor_weights.json",
    "iris": "iris_weights.json",
    "attention": "attention_weights.json",
}


def detect_and_load_weights(prompt: str) -> tuple[str | None, dict | None]:
    """Detect which model preset is requested and load its cached weights."""
    prompt_lower = prompt.lower()
    for keyword, filename in WEIGHT_FILE_MAP.items():
        if keyword in prompt_lower:
            weight_path = os.path.join(CACHE_DIR, filename)
            if os.path.exists(weight_path):
                with open(weight_path, "r") as f:
                    return keyword, json.load(f)
    return None, None


def weight_summary(weights: dict) -> str:
    """Return a brief summary of weight dimensions and counts."""
    total_params = 0
    layers = []
    for name, entry in weights.items():
        values = entry["values"]
        if isinstance(values[0], list):
            rows, cols = len(values), len(values[0])
            layers.append(f"{name}: {rows}x{cols} matrix")
            total_params += rows * cols
        else:
            layers.append(f"{name}: {len(values)}-element vector")
            total_params += len(values)
    return f"{len(layers)} parameter groups, {total_params} total params. Layers: {'; '.join(layers)}"


def extract_json_from_text(text: str):
    """Extract JSON objects from text, looking for ```json blocks or raw JSON."""
    results = []

    # Try ```json fenced blocks first
    fenced = re.findall(r"```json\s*([\s\S]*?)```", text)
    for block in fenced:
        try:
            results.append(json.loads(block.strip()))
        except json.JSONDecodeError:
            pass

    if results:
        return results

    # Fallback: try to find raw JSON objects (top-level { ... })
    for match in re.finditer(r"\{[\s\S]*?\n\}", text):
        try:
            results.append(json.loads(match.group()))
        except json.JSONDecodeError:
            pass

    return results


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    tools = check_tools()
    return {
        "status": "ok",
        "api_key_set": bool(GEMINI_API_KEY),
        "librelane_auto_harden": LIBRELANE_AUTO_HARDEN,
        "tools": tools,
    }


@app.get("/presets")
async def presets():
    return PRESET_PROMPTS


# ---------------------------------------------------------------------------
# Function-call handler
# ---------------------------------------------------------------------------

async def handle_function_call(
    websocket: WebSocket,
    fn_name: str,
    fn_args: dict,
    iteration: int,
    weights_info: str = "",
    ledger: Ledger | None = None,
    net=None,
):
    """Handle a Gemini function call, run EDA tools, send results to client.

    `ledger` records which exact code passed synthesis and simulation; `net` is
    the golden reference for the preset (None when there is no reference).
    """
    if ledger is None:
        ledger = Ledger()

    if fn_name == "analyze_model":
        msg = (
            "Analysis received. Now output the Hardware BOM as JSON in a ```json block in your text response. "
            "Then call synthesize_verilog with the complete Verilog RTL source code."
        )
        if weights_info:
            msg += f"\n\nModel weight summary: {weights_info}"
        return {"status": "ok", "message": msg}

    elif fn_name == "synthesize_verilog":
        module_name = fn_args.get("module_name", "design")
        verilog_code = fn_args.get("verilog_code", "")

        if not verilog_code:
            return {"status": "error", "message": "No verilog_code provided in function call. You MUST pass the complete Verilog source as the verilog_code parameter."}

        # Send RTL to client
        await ws_send(websocket, {
            "type": "block_rtl",
            "block_name": module_name,
            "code": verilog_code,
            "iteration": iteration,
        })

        # Synthesize
        await ws_send(websocket, {
            "type": "status",
            "message": f"Synthesizing {module_name} with Yosys + SkyWater 130nm...",
        })

        synth_result = synthesize(verilog_code, module_name)
        digest = ""
        if synth_result["success"]:
            digest = ledger.record_synthesis(module_name, verilog_code, synth_result.get("stats", {}))

        # Generate netlist SVG
        svg_result = generate_netlist_svg(verilog_code, module_name) if synth_result["success"] else {}

        synth_msg = {
            "type": "block_synth_result",
            "block_name": module_name,
            "stats": synth_result.get("stats", {}),
            "success": synth_result.get("success", False),
            "error": synth_result.get("error", ""),
            "gate_problems": synth_result.get("gate_problems", []),
            "sha256": digest,
            "log_tail": synth_result.get("log_tail", ""),
            "svg": svg_result.get("svg", ""),
            "iteration": iteration,
        }
        await ws_send(websocket, synth_msg)

        if synth_result["success"]:
            return {
                "status": "success",
                "message": (
                    f"Synthesis gate passed (sha256 {digest[:12]}). Stats: {json.dumps(synth_result.get('stats', {}))}. "
                    f"Now call simulate_verilog with module_name={module_name}. NeuralForge writes the testbench "
                    "from the reference model and simulates exactly this code."
                ),
            }
        else:
            return {
                "status": "error",
                "message": f"Synthesis failed: {synth_result.get('error', synth_result.get('log_tail', '')[:500])}. Fix the Verilog and call synthesize_verilog again.",
            }

    elif fn_name == "simulate_verilog":
        module_name = fn_args.get("module_name", "design")

        if net is None:
            reason = (
                "No reference model exists for this design, so NeuralForge cannot verify it. "
                "Synthesis results stand; simulation and hardening are skipped."
            )
            await ws_send(websocket, {
                "type": "simulation_result",
                "passed": False,
                "verdict": "unverified",
                "pass_count": 0,
                "total_count": 0,
                "reason": reason,
                "output": reason,
                "iteration": iteration,
            })
            return {"status": "unverified", "message": reason + " Stop here and summarize the synthesis results."}

        digest, verilog_code, error = ledger.design_for_simulation(module_name, fn_args.get("verilog_code") or None)
        if error:
            return {"status": "error", "message": error}

        await ws_send(websocket, {
            "type": "status",
            "message": f"Simulating {module_name} against the {net.name} reference ({len(net.inputs)} vectors)...",
        })

        sim_result = simulate_reference(verilog_code, module_name, net)
        passed = bool(sim_result.get("success") and sim_result.get("passed"))
        reason = sim_result.get("reason") or sim_result.get("error", "")

        await ws_send(websocket, {
            "type": "simulation_result",
            "passed": passed,
            "verdict": "passed" if passed else "failed",
            "pass_count": sim_result.get("pass_count", 0),
            "total_count": sim_result.get("total_count", 0),
            "reason": reason,
            "mismatches": sim_result.get("mismatches", []),
            "sha256": digest,
            "testbench": sim_result.get("testbench", ""),
            "output": sim_result.get("output", ""),
            "iteration": iteration,
        })

        hardening_result = None
        if passed:
            ledger.record_simulation_pass(digest)
            if ledger.hardenable(digest):
                hardening_result = await maybe_run_librelane_hardening(websocket, module_name, verilog_code)

        return {
            "status": "success" if passed else "failed",
            "reason": reason,
            "pass_count": sim_result.get("pass_count", 0),
            "total_count": sim_result.get("total_count", 0),
            "mismatches": sim_result.get("mismatches", [])[:5],
            "compiler_output": "" if sim_result.get("success") else sim_result.get("output", "")[:1500],
            "hardening": hardening_result,
        }

    elif fn_name == "fix_error":
        return {
            "status": "ok",
            "message": "Please provide the fixed code using synthesize_verilog or simulate_verilog.",
        }

    else:
        return {"status": "error", "message": f"Unknown function: {fn_name}"}


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------

async def run_agent_loop(websocket: WebSocket, user_prompt: str):
    """Run the Gemini agent loop with function calling."""

    # --- Inject trained weights into prompt ---
    keyword, weights = detect_and_load_weights(user_prompt)
    net = load_network(keyword)
    ledger = Ledger()
    weights_info = ""
    if net is not None:
        weights_info = weight_summary(weights)
        user_prompt += (
            "\n\nHere are the trained network's constants to hardcode (INT8 weights; biases already "
            "rescaled to each layer's 32-bit accumulator):"
            f"\n```\n{network_params(net)}\n```"
            f"\n\nInputs are INT8 at scale {net.input_scale:g}. Weight summary: {weights_info}"
            f"\n\n{port_contract(net)}"
        )
    elif weights is not None:
        weights_info = weight_summary(weights)
        user_prompt += (
            f"\n\nHere are the INT8 weights to hardcode:\n```\n{tensor_params(weights)}\n```"
            f"\n\nWeight summary: {weights_info}"
            "\n\nThere is no reference model for this design: NeuralForge will synthesize it but cannot verify it."
        )

    messages = [{"role": "user", "parts": [{"text": user_prompt}]}]
    iteration = 0
    max_iterations = 15
    pending_tool = None
    tool_nudges = {
        "synthesize_verilog": 0,
        "simulate_verilog": 0,
        "fix_error_or_retry": 0,
    }

    while iteration < max_iterations:
        iteration += 1

        await ws_send(websocket, {
            "type": "status",
            "message": f"Thinking... (iteration {iteration})",
        })

        try:
            response = get_client().models.generate_content(
                model=MODEL_NAME,
                contents=messages,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    tools=[
                        types.Tool(
                            function_declarations=[
                                types.FunctionDeclaration(**td) for td in TOOL_DECLARATIONS
                            ]
                        )
                    ],
                    temperature=0.2,
                ),
            )
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "quota" in error_str.lower() or "rate" in error_str.lower():
                await ws_send(websocket, {
                    "type": "error",
                    "message": "Rate limited by Gemini API. Please wait a moment and try again, or switch to a different model.",
                })
            else:
                await ws_send(websocket, {
                    "type": "error",
                    "message": f"Gemini API error: {error_str}",
                })
            return

        # Process response parts — collect all function calls first
        function_calls = []

        for part in response.candidates[0].content.parts:
            # --- Text part ---
            if hasattr(part, "text") and part.text:
                await ws_send(websocket, {
                    "type": "agent_message",
                    "text": part.text,
                    "iteration": iteration,
                })

                # Try to detect a BOM JSON in the text and forward it
                json_blocks = extract_json_from_text(part.text)
                for jb in json_blocks:
                    # Heuristic: if the JSON has typical BOM-ish keys, send it
                    if isinstance(jb, dict) and (
                        "blocks" in jb
                        or "modules" in jb
                        or "components" in jb
                        or "hardware_bom" in jb
                        or "bom" in jb
                    ):
                        await ws_send(websocket, {
                            "type": "hardware_bom",
                            "bom": jb,
                            "iteration": iteration,
                        })

            # --- Function call part ---
            if hasattr(part, "function_call") and part.function_call:
                function_calls.append(part.function_call)

        if function_calls:
            # Append the model turn once
            messages.append({
                "role": "model",
                "parts": response.candidates[0].content.parts,
            })

            # Execute all function calls and batch responses
            fn_response_parts = []
            finish_after_tool_batch = False
            for fc in function_calls:
                fn_name = fc.name
                fn_args = dict(fc.args) if fc.args else {}

                await ws_send(websocket, {
                    "type": "status",
                    "message": f"Calling tool: {fn_name}...",
                })

                fn_result = await handle_function_call(
                    websocket, fn_name, fn_args, iteration,
                    weights_info=weights_info, ledger=ledger, net=net,
                )

                if fn_name == "analyze_model":
                    pending_tool = "synthesize_verilog"
                elif fn_name == "synthesize_verilog":
                    pending_tool = "simulate_verilog" if fn_result.get("status") == "success" else "synthesize_verilog"
                elif fn_name == "simulate_verilog":
                    done = fn_result.get("status") in ("success", "unverified")
                    pending_tool = None if done else "fix_error_or_retry"
                    if done:
                        finish_after_tool_batch = True
                elif fn_name == "fix_error":
                    pending_tool = "simulate_verilog" if fn_args.get("step") == "simulation" else "synthesize_verilog"

                fn_response_parts.append({
                    "function_response": {
                        "name": fn_name,
                        "response": fn_result,
                    }
                })

            messages.append({
                "role": "user",
                "parts": fn_response_parts,
            })

            if finish_after_tool_batch:
                break
        else:
            # Preserve the model turn before deciding whether to stop or nudge.
            messages.append({
                "role": "model",
                "parts": response.candidates[0].content.parts,
            })

            nudge_text = None
            if pending_tool == "synthesize_verilog" and tool_nudges["synthesize_verilog"] < 2:
                tool_nudges["synthesize_verilog"] += 1
                nudge_text = (
                    "You must continue the workflow by calling synthesize_verilog now. "
                    "Do not stop after the Hardware BOM. Provide the COMPLETE Verilog RTL "
                    "source code in the function parameters."
                )
            elif pending_tool == "simulate_verilog" and tool_nudges["simulate_verilog"] < 2:
                tool_nudges["simulate_verilog"] += 1
                nudge_text = (
                    "You must continue the workflow by calling simulate_verilog now "
                    "with the module_name of the design that passed synthesis. "
                    "NeuralForge writes the testbench itself."
                )
            elif pending_tool == "fix_error_or_retry" and tool_nudges["fix_error_or_retry"] < 2:
                tool_nudges["fix_error_or_retry"] += 1
                nudge_text = (
                    "The previous synthesis or simulation attempt did not succeed. "
                    "Fix the design and resubmit the corrected code with synthesize_verilog, "
                    "then call simulate_verilog again. Do not stop yet."
                )

            if nudge_text:
                await ws_send(websocket, {
                    "type": "status",
                    "message": "Model stopped early; nudging the next required tool call...",
                })
                messages.append({
                    "role": "user",
                    "parts": [{"text": nudge_text}],
                })
                continue

            # Agent finished -- no more tool calls
            break

    await ws_send(websocket, {"type": "complete", "iterations": iteration})


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@app.websocket("/ws/design")
async def design_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            prompt = data.get("prompt", "")

            await ws_send(websocket, {
                "type": "status",
                "message": "Starting analysis...",
            })

            await run_agent_loop(websocket, prompt)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await ws_send(websocket, {"type": "error", "message": str(e)})
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
