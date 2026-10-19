"""
Checks for the tools NeuralForge needs on this machine, with install commands.
Shown in the settings panel's setup guide.
"""

import importlib.util
import platform
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SKY130_LIB = PROJECT_ROOT / "pdk" / "sky130.lib"


def _version(command: list[str]) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=5)
    except Exception:
        return ""
    text = (result.stdout or result.stderr).strip()
    return text.splitlines()[0][:80] if text else ""


def _install(mac: str, linux: str) -> dict:
    return {"macos": mac, "linux": linux}


def check() -> dict:
    items = []

    def tool(name, binary, purpose, required, install, version_args=None):
        path = shutil.which(binary)
        items.append({
            "name": name,
            "ok": bool(path),
            "required": required,
            "purpose": purpose,
            "detail": _version([binary, *version_args]) if path and version_args else (path or ""),
            "install": install,
        })

    py_ok = sys.version_info >= (3, 10)
    items.append({
        "name": "Python 3.10+",
        "ok": py_ok,
        "required": True,
        "purpose": "Runs the backend",
        "detail": platform.python_version(),
        "install": _install("brew install python@3.12", "sudo apt install python3 python3-pip"),
    })

    missing = [m for m in ("fastapi", "uvicorn", "openai", "anthropic", "numpy") if importlib.util.find_spec(m) is None]
    items.append({
        "name": "Python packages",
        "ok": not missing,
        "required": True,
        "purpose": "FastAPI server and the OpenAI / Anthropic SDKs",
        "detail": "missing: " + ", ".join(missing) if missing else "all installed",
        "install": _install(
            "python3 -m pip install -r backend/requirements.txt",
            "python3 -m pip install -r backend/requirements.txt",
        ),
    })

    tool("Yosys", "yosys", "Synthesis to SkyWater 130 nm cells", True,
         _install("brew install yosys", "sudo apt install yosys"), ["-V"])
    tool("Icarus Verilog", "iverilog", "Simulation against the reference", True,
         _install("brew install icarus-verilog", "sudo apt install iverilog"), ["-V"])

    items.append({
        "name": "SkyWater 130 nm liberty",
        "ok": SKY130_LIB.exists(),
        "required": True,
        "purpose": "Cell library for area and cell counts",
        "detail": str(SKY130_LIB.relative_to(PROJECT_ROOT)) if SKY130_LIB.exists() else "pdk/sky130.lib missing",
        "install": _install("git checkout -- pdk/sky130.lib", "git checkout -- pdk/sky130.lib"),
    })

    tool("netlistsvg", "netlistsvg", "Prettier netlist diagrams (Yosys draws one without it)", False,
         _install("npm install -g netlistsvg", "npm install -g netlistsvg"))
    tool("Nix + LibreLane", "nix-shell", "Optional physical hardening to GDS", False,
         _install("See https://librelane.readthedocs.io", "See https://librelane.readthedocs.io"))

    ready = all(item["ok"] for item in items if item["required"])
    return {
        "ready": ready,
        "platform": "macos" if platform.system() == "Darwin" else "linux",
        "items": items,
    }
