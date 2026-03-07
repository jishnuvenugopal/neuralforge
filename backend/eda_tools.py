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

from pathlib import Path as _Path
_PROJECT_ROOT = _Path(__file__).resolve().parent.parent
SKY130_LIB_PATH = str(_PROJECT_ROOT / "pdk" / "sky130.lib")
LIBRELANE_ROOT = _Path(os.environ.get("LIBRELANE_ROOT", str(_PROJECT_ROOT.parent / "librelane")))
LIBRELANE_SHELL_PATH = LIBRELANE_ROOT / "shell.nix"
LIBRELANE_DEFAULT_PDK_ROOT = _Path(os.environ.get("LIBRELANE_PDK_ROOT", str(_Path.home() / ".ciel")))
LIBRELANE_TIMEOUT_SEC = int(os.environ.get("LIBRELANE_TIMEOUT_SEC", "1800"))
NIX_PROFILE_BIN = _Path(os.environ.get("NIX_PROFILE_BIN", "/nix/var/nix/profiles/default/bin"))
LIBRELANE_DEFAULT_CLOCK_PERIOD_NS = int(os.environ.get("LIBRELANE_DEFAULT_CLOCK_PERIOD_NS", "10"))
LIBRELANE_DEFAULT_DIE_AREA = json.loads(os.environ.get("LIBRELANE_DEFAULT_DIE_AREA", "[0, 0, 600, 600]"))


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


def synthesize(verilog_code: str, module_name: str) -> dict:
    """Run Yosys synthesis with SKY130 PDK and return area/cell/FF stats."""
    try:
        verilog_path = f"/tmp/{module_name}.v"
        stats_json_path = f"/tmp/{module_name}_stats.json"

        with open(verilog_path, "w") as f:
            f.write(verilog_code)

        yosys_script = "; ".join([
            f"read_verilog {verilog_path}",
            f"synth -top {module_name}",
            f"dfflibmap -liberty {SKY130_LIB_PATH}",
            f"abc -liberty {SKY130_LIB_PATH}",
            f"stat -liberty {SKY130_LIB_PATH}",
            f"write_json {stats_json_path}",
        ])

        result = subprocess.run(
            ["yosys", "-p", yosys_script],
            capture_output=True,
            text=True,
            timeout=60,
        )

        stdout = result.stdout
        stderr = result.stderr
        log_lines = stdout.strip().split("\n")
        log_tail = "\n".join(log_lines[-30:])

        if result.returncode != 0:
            return {
                "success": False,
                "error": stderr.strip() or "Yosys exited with non-zero return code",
                "log_tail": log_tail,
            }

        # Parse area
        area_um2 = 0.0
        area_match = re.search(r"Chip area for module.*?:\s+([\d.]+)", stdout)
        if area_match:
            area_um2 = float(area_match.group(1))

        # Parse total cells: line like "   18  195.187 cells"
        # In Yosys stat -liberty output, the summary line ends with "cells"
        total_cells = 0
        cells_match = re.search(r"^\s*(\d+)\s+[\d.]+\s+cells\s*$", stdout, re.MULTILINE)
        if cells_match:
            total_cells = int(cells_match.group(1))
        else:
            # Fallback: "Number of cells:" line
            cells_match2 = re.search(r"Number of cells:\s+(\d+)", stdout)
            if cells_match2:
                total_cells = int(cells_match2.group(1))

        # Count flip-flops: lines containing "dfxtp"
        flip_flops = 0
        for line in log_lines:
            if "sky130_fd_sc_hd__dfxtp" in line:
                ff_match = re.match(r"^\s*(\d+)\s+", line)
                if ff_match:
                    flip_flops += int(ff_match.group(1))

        # Parse wires
        wires = 0
        wires_match = re.search(r"Number of wires:\s+(\d+)", stdout)
        if wires_match:
            wires = int(wires_match.group(1))

        return {
            "success": True,
            "stats": {
                "total_cells": total_cells,
                "flip_flops": flip_flops,
                "area_um2": area_um2,
                "wires": wires,
            },
            "log_tail": log_tail,
            "pdk_used": "sky130_fd_sc_hd",
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Yosys synthesis timed out after 60 seconds",
            "log_tail": "",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "log_tail": "",
        }


def simulate(verilog_code: str, testbench_code: str, module_name: str) -> dict:
    """Compile and run a Verilog testbench with iverilog/vvp."""
    try:
        verilog_path = f"/tmp/{module_name}.v"
        tb_path = f"/tmp/{module_name}_tb.v"
        sim_path = f"/tmp/{module_name}_sim"

        with open(verilog_path, "w") as f:
            f.write(verilog_code)
        with open(tb_path, "w") as f:
            f.write(testbench_code)

        # Compile
        compile_result = subprocess.run(
            ["iverilog", "-o", sim_path, verilog_path, tb_path],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if compile_result.returncode != 0:
            return {
                "success": False,
                "error": "Compilation failed",
                "output": compile_result.stderr.strip(),
            }

        # Run simulation
        sim_result = subprocess.run(
            ["vvp", sim_path],
            capture_output=True,
            text=True,
            timeout=30,
        )

        stdout = sim_result.stdout

        summary_match = re.search(r"(\d+)\s*/\s*(\d+)\s+TESTS?\s+PASSED", stdout, re.IGNORECASE)
        if summary_match:
            pass_count = int(summary_match.group(1))
            total_count = int(summary_match.group(2))
            fail_count = max(total_count - pass_count, 0)
        else:
            pass_count = len(re.findall(r"\bPASS(?:ED)?\b", stdout, re.IGNORECASE))
            fail_count = len(re.findall(r"\bFAIL(?:ED)?\b", stdout, re.IGNORECASE))
            total_count = pass_count + fail_count

        passed = fail_count == 0 and pass_count > 0

        return {
            "success": True,
            "passed": passed,
            "pass_count": pass_count,
            "total_count": total_count,
            "output": stdout,
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Simulation timed out after 30 seconds",
            "output": "",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "output": "",
        }


def generate_netlist_svg(verilog_code: str, module_name: str) -> dict:
    """Generate an SVG netlist diagram using Yosys + netlistsvg."""
    try:
        verilog_path = f"/tmp/{module_name}.v"
        net_json_path = f"/tmp/{module_name}_net.json"
        svg_path = f"/tmp/{module_name}_netlist.svg"

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
        svg_result = subprocess.run(
            ["netlistsvg", net_json_path, "-o", svg_path],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if svg_result.returncode != 0:
            # Fallback: use Yosys show command to produce SVG
            fallback_script = "; ".join([
                f"read_verilog {verilog_path}",
                f"prep -top {module_name} -flatten",
                f"show -format svg -prefix /tmp/{module_name}_netlist",
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
                "error": f"SVG file was not created at {svg_path}",
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
        if not module_name:
            return {
                "success": False,
                "error": "module_name is required",
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
