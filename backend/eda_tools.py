"""
EDA tool wrappers for Yosys, iverilog, netlistsvg, LibreLane, and GDS rendering.
Every function uses subprocess with timeouts and never throws -- always returns
a dict with a "success" bool.
"""

import subprocess
import tempfile
import os
import re
import json
import shlex
import base64
import secrets

from pathlib import Path as _Path

from golden import Network
from verifier import check_netlist, make_testbench, parse_results, scan_source, valid_module_name, vector_file

_PROJECT_ROOT = _Path(__file__).resolve().parent.parent
SKY130_LIB_PATH = str(_PROJECT_ROOT / "pdk" / "sky130.lib")
LIBRELANE_ROOT = _Path(os.environ.get("LIBRELANE_ROOT", str(_PROJECT_ROOT.parent / "librelane")))
LIBRELANE_SHELL_PATH = LIBRELANE_ROOT / "shell.nix"
LIBRELANE_DEFAULT_PDK_ROOT = _Path(os.environ.get("LIBRELANE_PDK_ROOT", str(_Path.home() / ".ciel")))
LIBRELANE_TIMEOUT_SEC = int(os.environ.get("LIBRELANE_TIMEOUT_SEC", "1800"))
NIX_PROFILE_BIN = _Path(os.environ.get("NIX_PROFILE_BIN", "/nix/var/nix/profiles/default/bin"))
LIBRELANE_DEFAULT_CLOCK_PERIOD_NS = int(os.environ.get("LIBRELANE_DEFAULT_CLOCK_PERIOD_NS", "10"))
LIBRELANE_DEFAULT_DIE_AREA = json.loads(os.environ.get("LIBRELANE_DEFAULT_DIE_AREA", "[0, 0, 600, 600]"))
SYNTH_TIMEOUT_SEC = int(os.environ.get("NEURALFORGE_SYNTH_TIMEOUT_SEC", "120"))
SIM_TIMEOUT_SEC = int(os.environ.get("NEURALFORGE_SIM_TIMEOUT_SEC", "30"))


def _resolve_command(command: str) -> str | None:
    """Resolve a command from PATH or the default Nix profile bin directory."""
    direct_path = _Path(command)
    if direct_path.is_absolute() and direct_path.exists():
        return str(direct_path)

    nix_profile_candidate = NIX_PROFILE_BIN / command
    if nix_profile_candidate.exists():
        return str(nix_profile_candidate)

    try:
        result = subprocess.run(
            ["which", command],
            capture_output=True,
            text=True,
            timeout=5,
        )
        resolved = result.stdout.strip()
        if result.returncode == 0 and resolved:
            return resolved
    except Exception:
        pass

    return None


def _has_command(command: str) -> bool:
    """Return True when a command is available on PATH."""
    return _resolve_command(command) is not None


def _tail_text(*chunks: str, lines: int = 40) -> str:
    """Return the tail of combined stdout/stderr for easier UI display."""
    combined = "\n".join(chunk for chunk in chunks if chunk).strip()
    if not combined:
        return ""
    return "\n".join(combined.splitlines()[-lines:])


def _find_latest_file(search_root: _Path, suffixes: tuple[str, ...]) -> str | None:
    """Find the most recently modified file matching one of the suffixes."""
    matches = []
    for path in search_root.rglob("*"):
        if path.is_file() and path.suffix.lower() in suffixes:
            matches.append(path)

    if not matches:
        return None

    matches.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return str(matches[0])


def _detect_clock_port(verilog_code: str) -> str | None:
    """Heuristically pick a clock port so simple generated modules harden cleanly."""
    input_names = []
    for line in verilog_code.splitlines():
        stripped = line.strip()
        if not stripped.startswith("input "):
            continue

        cleaned = stripped.rstrip(",;")
        cleaned = re.sub(r"\b(input|wire|reg|logic|signed)\b", "", cleaned)
        cleaned = re.sub(r"\[[^\]]+\]", "", cleaned)
        for name in cleaned.split(","):
            candidate = name.strip()
            if candidate:
                input_names.append(candidate)

    if not input_names:
        return None

    preferred_names = (
        "clk",
        "clock",
        "clk_i",
        "clock_i",
        "i_clk",
        "wb_clk_i",
        "ap_clk",
        "aclk",
    )
    for preferred in preferred_names:
        if preferred in input_names:
            return preferred

    for name in input_names:
        lowered = name.lower()
        if "clk" in lowered or "clock" in lowered:
            return name

    return None


def _invalid_name_result(module_name: str) -> dict:
    return {
        "success": False,
        "error": f"Invalid module name {module_name!r}: use letters, digits and underscores, starting with a letter.",
        "log_tail": "",
    }


def _parse_stat(stdout: str) -> dict:
    """Parse `stat -liberty` output (Yosys 0.4x table format and the older 'Number of' format)."""
    def last_int(*patterns):
        for pattern in patterns:
            matches = re.findall(pattern, stdout, re.MULTILINE)
            if matches:
                return int(matches[-1])
        return 0

    area_um2 = 0.0
    area_matches = re.findall(r"Chip area for module.*?:\s+([\d.]+)", stdout)
    if area_matches:
        area_um2 = float(area_matches[-1])

    total_cells = last_int(r"^\s*(\d+)\s+\S+\s+cells\s*$", r"Number of cells:\s+(\d+)")
    wires = last_int(r"^\s*(\d+)\s+(?:-\s+)?wires\s*$", r"Number of wires:\s+(\d+)")

    # Every sky130 flip-flop: dfxtp, dfrtp (reset), dfstp (set), dfbbp, edfxtp, sdfxtp, ...
    flip_flops = 0
    for count, cell in re.findall(r"^\s*(\d+)\s+(?:\S+\s+)?sky130_fd_sc_hd__(\w+)\s*$", stdout, re.MULTILINE):
        if re.match(r"(s?e?df)", cell):
            flip_flops += int(count)

    return {
        "total_cells": total_cells,
        "flip_flops": flip_flops,
        "area_um2": area_um2,
        "wires": wires,
    }


def synthesize(verilog_code: str, module_name: str) -> dict:
    """Run the synthesis gate: source scan, Yosys + SKY130 mapping, and netlist checks.

    `success` is True only when Yosys succeeds AND the design has logic cells,
    no latches, and no constant or undriven outputs.
    """
    if not valid_module_name(module_name):
        return _invalid_name_result(module_name)

    problems = scan_source(verilog_code, module_name)
    if problems:
        return {
            "success": False,
            "error": "Design rejected before synthesis: " + "; ".join(problems),
            "gate_problems": problems,
            "log_tail": "",
        }

    try:
        with tempfile.TemporaryDirectory(prefix=f"nf_synth_{module_name}_") as work:
            verilog_path = os.path.join(work, "design.v")
            generic_json_path = os.path.join(work, "generic.json")
            with open(verilog_path, "w") as f:
                f.write(verilog_code)

            # Full ABC mapping gives the honest area; on large designs (a fully
            # parallel Iris network) it can take minutes, so fall back to
            # `abc -fast` and say so in the stats.
            abc_mode = "full"
            for abc_flags in ("", "-fast "):
                yosys_script = "; ".join([
                    f"read_verilog {verilog_path}",
                    f"synth -flatten -top {module_name}",
                    f"write_json {generic_json_path}",
                    f"dfflibmap -liberty {SKY130_LIB_PATH}",
                    f"abc {abc_flags}-liberty {SKY130_LIB_PATH}",
                    f"stat -liberty {SKY130_LIB_PATH}",
                ])
                try:
                    result = subprocess.run(
                        ["yosys", "-p", yosys_script],
                        capture_output=True,
                        text=True,
                        timeout=SYNTH_TIMEOUT_SEC,
                    )
                    break
                except subprocess.TimeoutExpired:
                    if abc_flags:
                        raise
                    abc_mode = "fast"

            stdout = result.stdout
            log_tail = _tail_text(stdout, lines=30)

            if result.returncode != 0:
                return {
                    "success": False,
                    "error": result.stderr.strip() or _tail_text(stdout, lines=10) or "Yosys exited with non-zero return code",
                    "log_tail": log_tail,
                }

            stats = _parse_stat(stdout)
            stats["abc_mode"] = abc_mode
            with open(generic_json_path) as f:
                netlist = json.load(f)

        problems = check_netlist(netlist, module_name, stdout)
        if stats["total_cells"] == 0:
            problems.insert(0, "no logic cells after synthesis (the design is constant or empty)")

        if problems:
            return {
                "success": False,
                "error": "Synthesis gate failed: " + "; ".join(problems),
                "gate_problems": problems,
                "stats": stats,
                "log_tail": log_tail,
            }

        return {
            "success": True,
            "stats": stats,
            "log_tail": log_tail,
            "pdk_used": "sky130_fd_sc_hd",
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": f"Yosys synthesis timed out twice ({SYNTH_TIMEOUT_SEC} s each, full and fast ABC)",
            "log_tail": "",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "log_tail": "",
        }


def simulate_reference(verilog_code: str, module_name: str, net: Network) -> dict:
    """Simulate the design against the golden reference with a NeuralForge-written testbench.

    The verdict comes from the testbench's result file (checked against a
    per-run nonce) compared with the bit-exact reference. Simulator stdout is
    returned for display only.
    """
    if not valid_module_name(module_name):
        return _invalid_name_result(module_name)

    total = len(net.inputs)
    problems = scan_source(verilog_code, module_name)
    if problems:
        return {
            "success": False,
            "passed": False,
            "pass_count": 0,
            "total_count": total,
            "error": "Design rejected before simulation: " + "; ".join(problems),
            "output": "",
        }

    try:
        with tempfile.TemporaryDirectory(prefix=f"nf_sim_{module_name}_") as work:
            nonce = secrets.token_hex(8)
            verilog_path = os.path.join(work, "design.v")
            tb_path = os.path.join(work, "testbench.v")
            vector_path = os.path.join(work, "vectors.hex")
            result_path = os.path.join(work, f"result_{nonce}.txt")
            sim_path = os.path.join(work, "sim.vvp")

            testbench = make_testbench(net, module_name, nonce, vector_path, result_path)
            with open(verilog_path, "w") as f:
                f.write(verilog_code)
            with open(tb_path, "w") as f:
                f.write(testbench)
            with open(vector_path, "w") as f:
                f.write(vector_file(net))

            compile_result = subprocess.run(
                ["iverilog", "-g2005", "-s", f"nf_tb_{nonce}", "-o", sim_path, verilog_path, tb_path],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if compile_result.returncode != 0:
                return {
                    "success": False,
                    "passed": False,
                    "pass_count": 0,
                    "total_count": total,
                    "error": "Compilation failed",
                    "output": compile_result.stderr.strip(),
                }

            sim_result = subprocess.run(
                ["vvp", "-n", sim_path],
                cwd=work,
                capture_output=True,
                text=True,
                timeout=SIM_TIMEOUT_SEC,
            )

            result_text = ""
            if os.path.exists(result_path):
                with open(result_path) as f:
                    result_text = f.read()

        verdict = parse_results(result_text, net, nonce)
        if sim_result.returncode != 0:
            verdict["passed"] = False
            verdict["reason"] = f"vvp exited with code {sim_result.returncode}; " + verdict["reason"]

        return {
            "success": True,
            **verdict,
            "output": _tail_text(sim_result.stdout, sim_result.stderr, lines=40),
            "testbench": testbench,
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "passed": False,
            "pass_count": 0,
            "total_count": total,
            "error": f"Simulation timed out after {SIM_TIMEOUT_SEC} seconds",
            "output": "",
        }
    except Exception as e:
        return {
            "success": False,
            "passed": False,
            "pass_count": 0,
            "total_count": total,
            "error": str(e),
            "output": "",
        }


def generate_netlist_svg(verilog_code: str, module_name: str) -> dict:
    """Generate an SVG netlist diagram using Yosys + netlistsvg."""
    if not valid_module_name(module_name):
        return _invalid_name_result(module_name)

    try:
        with tempfile.TemporaryDirectory(prefix=f"nf_svg_{module_name}_") as work:
            verilog_path = os.path.join(work, "design.v")
            net_json_path = os.path.join(work, "net.json")
            svg_prefix = os.path.join(work, "netlist")
            svg_path = f"{svg_prefix}.svg"

            with open(verilog_path, "w") as f:
                f.write(verilog_code)

            # Run Yosys to produce JSON netlist
            yosys_script = "; ".join([
                f"read_verilog {verilog_path}",
                f"prep -top {module_name} -flatten",
                f"write_json {net_json_path}",
            ])

            yosys_result = subprocess.run(
                ["yosys", "-p", yosys_script],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if yosys_result.returncode != 0:
                return {
                    "success": False,
                    "error": f"Yosys failed: {yosys_result.stderr.strip()}",
                }

            # Try netlistsvg first
            svg_ok = False
            if _has_command("netlistsvg"):
                svg_result = subprocess.run(
                    ["netlistsvg", net_json_path, "-o", svg_path],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                svg_ok = svg_result.returncode == 0

            if not svg_ok:
                # Fallback: use Yosys show command to produce SVG
                fallback_script = "; ".join([
                    f"read_verilog {verilog_path}",
                    f"prep -top {module_name} -flatten",
                    f"show -format svg -prefix {svg_prefix}",
                ])

                fallback_result = subprocess.run(
                    ["yosys", "-p", fallback_script],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if fallback_result.returncode != 0:
                    return {
                        "success": False,
                        "error": f"netlistsvg and Yosys show both failed: {fallback_result.stderr.strip()}",
                    }

            # Read the SVG file
            if not os.path.exists(svg_path):
                return {
                    "success": False,
                    "error": "SVG file was not created",
                }

            with open(svg_path, "r") as f:
                svg_content = f.read()

        return {
            "success": True,
            "svg": svg_content,
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Netlist SVG generation timed out after 30 seconds",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


def prepare_librelane_design(
    module_name: str,
    verilog_code: str,
    design_config: dict | None = None,
    work_root: str | None = None,
) -> dict:
    """Materialize a temporary LibreLane design workspace from generated RTL."""
    try:
        if not valid_module_name(module_name):
            return {
                "success": False,
                "error": f"Invalid module name {module_name!r}",
            }

        if not verilog_code.strip():
            return {
                "success": False,
                "error": "verilog_code is empty",
            }

        root = _Path(work_root) if work_root else _Path(tempfile.mkdtemp(prefix="neuralforge_librelane_"))
        design_dir = root / module_name
        src_dir = design_dir / "src"
        runs_dir = design_dir / "runs"
        src_dir.mkdir(parents=True, exist_ok=True)
        runs_dir.mkdir(parents=True, exist_ok=True)

        verilog_path = src_dir / f"{module_name}.v"
        verilog_path.write_text(verilog_code)

        clock_port = _detect_clock_port(verilog_code)

        config = {
            "DESIGN_NAME": module_name,
            "VERILOG_FILES": ["dir::src/*.v"],
            # LibreLane no longer auto-shrinks PDN geometry for tiny designs,
            # so generated toy modules need a roomy absolute die by default.
            "FP_SIZING": "absolute",
            "DIE_AREA": LIBRELANE_DEFAULT_DIE_AREA,
            "FP_PDN_MULTILAYER": True,
        }
        if clock_port:
            config["CLOCK_PORT"] = clock_port
            config["CLOCK_PERIOD"] = LIBRELANE_DEFAULT_CLOCK_PERIOD_NS
        if design_config:
            config.update(design_config)

        config_json_path = design_dir / "config.json"
        config_json_path.write_text(json.dumps(config, indent=2))

        return {
            "success": True,
            "design_dir": str(design_dir),
            "config_json_path": str(config_json_path),
            "verilog_path": str(verilog_path),
            "config": config,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


def _collect_librelane_artifacts(design_dir: str) -> dict:
    """Collect the most useful LibreLane output artifacts after a run."""
    search_root = _Path(design_dir)
    artifacts = {
        "gds_path": _find_latest_file(search_root, (".gds",)),
        "def_path": _find_latest_file(search_root, (".def",)),
        "lef_path": _find_latest_file(search_root, (".lef",)),
        "log_path": _find_latest_file(search_root, (".log",)),
        "report_path": _find_latest_file(search_root, (".rpt", ".txt")),
    }

    gds_path = artifacts.get("gds_path")
    if gds_path:
        png_result = render_gds_to_png(gds_path)
        if png_result.get("success"):
            artifacts["png_path"] = png_result["png_path"]
            try:
                with open(png_result["png_path"], "rb") as handle:
                    artifacts["png_base64"] = base64.b64encode(handle.read()).decode("utf-8")
            except Exception:
                pass

    return artifacts


def run_librelane_flow(
    design_dir: str,
    config_json_path: str,
    pdk_root: str | None = None,
    flow_name: str | None = None,
    timeout_sec: int = LIBRELANE_TIMEOUT_SEC,
) -> dict:
    """Run LibreLane inside nix-shell and return logs plus discovered artifacts."""
    try:
        nix_shell_bin = _resolve_command("nix-shell")
        if not nix_shell_bin:
            return {
                "success": False,
                "error": "nix-shell is not available. Install Nix or expose /nix/var/nix/profiles/default/bin.",
            }

        shell_path = _Path(LIBRELANE_SHELL_PATH)
        if not shell_path.exists():
            return {
                "success": False,
                "error": f"LibreLane shell.nix not found at {shell_path}",
            }

        config_path = _Path(config_json_path)
        if not config_path.exists():
            return {
                "success": False,
                "error": f"LibreLane config not found at {config_json_path}",
            }

        design_root = _Path(design_dir)
        if not design_root.exists():
            return {
                "success": False,
                "error": f"LibreLane design directory not found at {design_dir}",
            }

        librelane_cmd = ["librelane"]
        if flow_name:
            librelane_cmd.extend(["--flow", flow_name])
        if pdk_root:
            librelane_cmd.extend(["--pdk-root", pdk_root])
        librelane_cmd.append(str(config_path))

        command = [
            nix_shell_bin,
            "--pure",
            str(shell_path),
            "--run",
            shlex.join(librelane_cmd),
        ]

        result = subprocess.run(
            command,
            cwd=str(design_root),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )

        log_tail = _tail_text(result.stdout, result.stderr)
        artifacts = _collect_librelane_artifacts(str(design_root))

        if result.returncode != 0:
            return {
                "success": False,
                "error": result.stderr.strip() or "LibreLane exited with a non-zero return code",
                "stdout": result.stdout,
                "stderr": result.stderr,
                "log_tail": log_tail,
                "command": command,
                "artifacts": artifacts,
                "design_dir": str(design_root),
                "config_json_path": str(config_path),
                "pdk_root": pdk_root or str(LIBRELANE_DEFAULT_PDK_ROOT),
            }

        return {
            "success": True,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "log_tail": log_tail,
            "command": command,
            "artifacts": artifacts,
            "design_dir": str(design_root),
            "config_json_path": str(config_path),
            "pdk_root": pdk_root or str(LIBRELANE_DEFAULT_PDK_ROOT),
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": f"LibreLane flow timed out after {timeout_sec} seconds",
            "log_tail": "",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "log_tail": "",
        }


def render_gds_to_png(gds_path: str, output_path: str = None) -> dict:
    """Render a GDS file to PNG via gdstk and cairosvg."""
    try:
        import gdstk
        import cairosvg
    except ImportError as e:
        return {
            "success": False,
            "error": f"Missing dependency: {e}",
        }

    try:
        if output_path is None:
            output_path = os.path.splitext(gds_path)[0] + ".png"

        lib = gdstk.read_gds(gds_path)
        top = lib.top_level()[0]

        svg_path = gds_path.replace(".gds", ".svg")
        top.write_svg(svg_path, scaling=10, background="#0a0a0f")

        cairosvg.svg2png(url=svg_path, write_to=output_path, output_width=1000)

        return {
            "success": True,
            "png_path": output_path,
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


def check_tools() -> dict:
    """Check availability of EDA tools."""
    tools = {}

    for tool in ["yosys", "iverilog", "netlistsvg", "nix-shell"]:
        tools[tool] = _has_command(tool)

    tools["librelane_repo"] = LIBRELANE_ROOT.exists()
    tools["librelane_shell"] = LIBRELANE_SHELL_PATH.exists()
    tools["librelane_pdk_root"] = LIBRELANE_DEFAULT_PDK_ROOT.exists()

    try:
        import gdstk  # noqa: F401
        tools["gdstk"] = True
    except ImportError:
        tools["gdstk"] = False

    return tools
