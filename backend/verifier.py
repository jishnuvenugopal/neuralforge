"""
Pure-Python parts of the verification gate (no subprocesses here):

- scan_source: rejects design code that could talk to the simulator or the
  testbench (system tasks, initial blocks, hierarchical references, ...).
- make_testbench / vector_file: the testbench NeuralForge writes itself from
  the golden reference. The LLM never supplies one.
- parse_results: the verdict. It reads the structured result file the
  testbench writes (with a per-run nonce) and compares every output to the
  reference. Simulator stdout is never read for the verdict.
- check_netlist: the synthesis gate beyond Yosys' exit code (no constant or
  undriven outputs, no latches).
- Ledger: ties each verdict to the sha256 of the exact code it checked.
"""

import hashlib
import re

from golden import INPUT_BITS, LOGIT_BITS, Network, reference_outputs

MODULE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")

MAX_WAIT_CYCLES = 64
MAX_DROP_CYCLES = 16

_ALLOWED_SYSTEM_FUNCTIONS = {"signed", "unsigned", "clog2"}
_ALLOWED_DIRECTIVES = {"timescale", "default_nettype"}
_FORBIDDEN_KEYWORDS = ("initial", "force", "release", "deassign", "defparam", "fork", "specify")


def sha256(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def valid_module_name(name: str) -> bool:
    return bool(name) and bool(MODULE_NAME_RE.match(name))


def _strip_comments(code: str) -> str:
    code = re.sub(r"/\*.*?\*/", " ", code, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", " ", code)


def scan_source(code: str, module_name: str) -> list[str]:
    """Return the reasons this design source is not allowed (empty list = clean)."""
    problems = []
    text = _strip_comments(code)

    for match in re.finditer(r"(?<![\w$])\$(\w*)", text):
        if match.group(1) not in _ALLOWED_SYSTEM_FUNCTIONS:
            problems.append(f"system task or function ${match.group(1)} is not allowed in the design")

    for match in re.finditer(r"`(\w*)", text):
        if match.group(1) not in _ALLOWED_DIRECTIVES:
            problems.append(f"compiler directive `{match.group(1)} is not allowed in the design")

    for keyword in _FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{keyword}\b", text):
            problems.append(f"'{keyword}' is not allowed in the design (use the reset for initial values)")

    if re.search(r"\\\S", text):
        problems.append("escaped identifiers are not allowed in the design")

    hier = re.search(r"(?<![\w$.'])([A-Za-z_][\w$]*)\s*\.\s*[A-Za-z_]", text)
    if hier:
        problems.append(f"hierarchical reference '{hier.group(0)}' is not allowed in the design")

    if not re.search(rf"\bmodule\s+{re.escape(module_name)}\b", text):
        problems.append(f"no module named {module_name} in the code")

    return sorted(set(problems))


# ---------------------------------------------------------------------------
# Testbench
# ---------------------------------------------------------------------------

def vector_file(net: Network) -> str:
    """$readmemh contents: one packed x_flat per line, x_i at bits [8i+7:8i]."""
    digits = (net.n_inputs * INPUT_BITS + 3) // 4
    lines = []
    for x in net.inputs:
        packed = 0
        for i, value in enumerate(x):
            packed |= (value & 0xFF) << (INPUT_BITS * i)
        lines.append(f"{packed:0{digits}x}")
    return "\n".join(lines) + "\n"


def make_testbench(net: Network, module_name: str, nonce: str, vector_path: str, result_path: str) -> str:
    """Testbench that drives every reference input and writes raw outputs to `result_path`."""
    n = len(net.inputs)
    x_bits = net.n_inputs * INPUT_BITS
    z_bits = net.n_outputs * LOGIT_BITS
    c_bits = net.cls_bits
    logit_writes = "\n".join(
        f'        $fwrite(fd, " %0d", $signed(logits_flat[{LOGIT_BITS * j + LOGIT_BITS - 1}:{LOGIT_BITS * j}]));'
        for j in range(net.n_outputs)
    )
    return f"""`timescale 1ns/1ps
module nf_tb_{nonce};
  reg clk = 1'b0;
  reg rst = 1'b1;
  reg start = 1'b0;
  reg [{x_bits - 1}:0] x_flat = {x_bits}'d0;
  wire done;
  wire [{z_bits - 1}:0] logits_flat;
  wire [{c_bits - 1}:0] cls;
  reg [{x_bits - 1}:0] vectors [0:{n - 1}];
  integer fd, i, waited;

  {module_name} dut (
    .clk(clk), .rst(rst), .start(start), .x_flat(x_flat),
    .done(done), .logits_flat(logits_flat), .cls(cls)
  );

  always #5 clk = ~clk;

  initial begin
    $readmemh("{vector_path}", vectors);
    fd = $fopen("{result_path}", "w");
    $fwrite(fd, "BEGIN {nonce}\\n");
    repeat (2) @(negedge clk);
    rst = 1'b0;
    for (i = 0; i < {n}; i = i + 1) begin
      @(negedge clk);
      x_flat = vectors[i];
      start = 1'b1;
      #1;
      waited = 0;
      while (done !== 1'b1 && waited < {MAX_WAIT_CYCLES}) begin
        @(negedge clk);
        start = 1'b0;
        #1;
        waited = waited + 1;
      end
      if (done === 1'b1) begin
        $fwrite(fd, "V %0d", i);
{logit_writes}
        $fwrite(fd, " %0d\\n", cls);
      end else begin
        $fwrite(fd, "T %0d\\n", i);
      end
      @(negedge clk);
      start = 1'b0;
      #1;
      waited = 0;
      while (done !== 1'b0 && waited < {MAX_DROP_CYCLES}) begin
        @(negedge clk);
        #1;
        waited = waited + 1;
      end
      if (done !== 1'b0) $fwrite(fd, "S %0d\\n", i);
    end
    $fwrite(fd, "END {nonce} {n}\\n");
    $fclose(fd);
    $finish;
  end
endmodule
"""


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------

def parse_results(text: str, net: Network, nonce: str) -> dict:
    """Compare the testbench's result file with the reference. Never looks at stdout."""
    expected = reference_outputs(net)
    total = len(expected)

    def verdict(reason: str, pass_count: int = 0, mismatches=None) -> dict:
        return {
            "passed": False,
            "pass_count": pass_count,
            "total_count": total,
            "reason": reason,
            "mismatches": mismatches or [],
        }

    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    if not lines or lines[0] != f"BEGIN {nonce}":
        return verdict("result file missing or not written by this run's testbench")
    if lines[-1] != f"END {nonce} {total}":
        return verdict("testbench did not finish (no END record)")

    got = {}
    stuck = set()
    for line in lines[1:-1]:
        fields = line.split()
        kind = fields[0]
        try:
            index = int(fields[1])
        except (IndexError, ValueError):
            return verdict(f"malformed result line: {line!r}")
        if not 0 <= index < total:
            return verdict(f"result line for unknown vector: {line!r}")
        if kind == "S":
            stuck.add(index)
            continue
        if index in got:
            return verdict(f"duplicate result for vector {index}")
        if kind == "T":
            got[index] = None
        elif kind == "V":
            got[index] = fields[2:]
        else:
            return verdict(f"malformed result line: {line!r}")

    pass_count = 0
    mismatches = []
    for index, (logits, cls) in enumerate(expected):
        want = [str(v) for v in logits] + [str(cls)]
        have = got.get(index, "missing")
        if have == want and index not in stuck:
            pass_count += 1
            continue
        if have == "missing":
            detail = "no result"
        elif have is None:
            detail = f"done not raised within {MAX_WAIT_CYCLES} cycles"
        elif index in stuck and have == want:
            detail = f"done still high {MAX_DROP_CYCLES} cycles after start fell"
        else:
            detail = f"got {' '.join(have)}, expected {' '.join(want)}"
        mismatches.append({"vector": index, "input": net.inputs[index], "detail": detail})

    if pass_count == total:
        return {
            "passed": True,
            "pass_count": pass_count,
            "total_count": total,
            "reason": f"all {total} vectors match the bit-exact reference",
            "mismatches": [],
        }
    return verdict(f"{total - pass_count} of {total} vectors differ from the reference", pass_count, mismatches[:10])


# ---------------------------------------------------------------------------
# Synthesis gate
# ---------------------------------------------------------------------------

def check_netlist(netlist: dict, module_name: str, synth_log: str) -> list[str]:
    """Problems in a flattened generic Yosys JSON netlist that the exit code does not catch."""
    problems = []
    module = netlist.get("modules", {}).get(module_name)
    if module is None:
        return [f"module {module_name} not found in the synthesized netlist"]

    cells = module.get("cells", {})
    if "Latch inferred" in synth_log or any(
        "DLATCH" in cell.get("type", "").upper() or cell.get("type") in ("$dlatch", "$adlatch", "$dlatchsr")
        for cell in cells.values()
    ):
        problems.append("latches inferred; every signal must be assigned in every branch or registered")

    driven = set()
    for port in module.get("ports", {}).values():
        if port.get("direction") == "input":
            driven.update(bit for bit in port.get("bits", []) if isinstance(bit, int))
    for cell in cells.values():
        directions = cell.get("port_directions", {})
        for pin, bits in cell.get("connections", {}).items():
            if directions.get(pin) == "output":
                driven.update(bit for bit in bits if isinstance(bit, int))

    for name, port in module.get("ports", {}).items():
        if port.get("direction") != "output":
            continue
        bits = port.get("bits", [])
        if bits and all(bit in ("0", "1") for bit in bits):
            problems.append(f"output {name} is tied to a constant")
        elif any(bit in ("x", "z") or (isinstance(bit, int) and bit not in driven) for bit in bits):
            problems.append(f"output {name} is not driven")

    return problems


# ---------------------------------------------------------------------------
# Hash binding
# ---------------------------------------------------------------------------

class Ledger:
    """Per-session record of which exact code passed which gate."""

    def __init__(self):
        self.synthesized = {}       # sha -> {"module_name", "code", "stats"}
        self.simulated = set()      # sha of code whose simulation matched the reference
        self.latest = {}            # module_name -> sha of the last code that passed synthesis

    def record_synthesis(self, module_name: str, code: str, stats: dict) -> str:
        digest = sha256(code)
        self.synthesized[digest] = {"module_name": module_name, "code": code, "stats": stats}
        self.latest[module_name] = digest
        return digest

    def design_for_simulation(self, module_name: str, code: str | None = None) -> tuple[str | None, str | None, str]:
        """Return (sha, code, error). Only code that passed synthesis unchanged can be simulated."""
        if code:
            digest = sha256(code)
            entry = self.synthesized.get(digest)
            if entry is None or entry["module_name"] != module_name:
                return None, None, (
                    "This exact code has not passed synthesize_verilog. "
                    "Submit it to synthesize_verilog first; only synthesized code can be simulated."
                )
            return digest, entry["code"], ""
        digest = self.latest.get(module_name)
        if digest is None:
            return None, None, f"No design named {module_name} has passed synthesize_verilog yet."
        return digest, self.synthesized[digest]["code"], ""

    def record_simulation_pass(self, digest: str):
        if digest in self.synthesized:
            self.simulated.add(digest)

    def hardenable(self, digest: str) -> bool:
        return digest in self.synthesized and digest in self.simulated
