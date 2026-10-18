"""
Bit-exact integer reference of the quantized networks.

The expected outputs of every simulation come from here, not from the LLM.
The arithmetic is the one the RTL must implement (see PORT CONTRACT below):

    h = ReLU(W1 * x + B1)        32-bit signed, no requantization
    z = W2 * h + B2              32-bit signed logits
    cls = (z[0] > 0)             one output  (XOR)
    cls = argmax(z)              several outputs, lowest index wins ties (Iris)

Weights are the cached INT8 values. Inputs are INT8 at `input_scale`. Biases
are requantized to the accumulator scale of their layer, so they are added to
products at the same scale:

    B1 = round(b1_float * s_x * s_w1)
    B2 = round(b2_float * s_x * s_w1 * s_w2)
"""

import json
import os
from dataclasses import dataclass, field

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")

INPUT_BITS = 8
LOGIT_BITS = 32
INT32_MIN, INT32_MAX = -(2 ** 31), 2 ** 31 - 1

XOR_INPUTS = [[0, 0], [0, 1], [1, 0], [1, 1]]
XOR_LABELS = [0, 1, 1, 0]

# Presets with a reference model. Anything else can be synthesized, but not verified.
REFERENCE_PRESETS = ("xor", "iris")


@dataclass
class Network:
    name: str
    layers: list            # [(W rows x cols, B per row)], integers
    input_scale: float
    inputs: list            # INT8 input vectors, one per test
    labels: list = field(default_factory=list)

    @property
    def n_inputs(self) -> int:
        return len(self.layers[0][0][0])

    @property
    def n_outputs(self) -> int:
        return len(self.layers[-1][0])

    @property
    def cls_bits(self) -> int:
        return max(1, (self.n_outputs - 1).bit_length())


def _as_float(entry: dict) -> list:
    scale = entry["scale"]
    values = entry["values"]
    if isinstance(values[0], list):
        return [[v / scale for v in row] for row in values]
    return [v / scale for v in values]


def quantized_network(name: str, weights: dict, input_scale: float, inputs: list, labels: list) -> Network:
    """Build the integer network from cached INT8 weights (keys `0.weight`, `0.bias`, `2.weight`, ...)."""
    weight_keys = sorted(
        (k for k in weights if k.endswith(".weight")),
        key=lambda k: int(k.split(".")[0]),
    )
    layers = []
    acc_scale = input_scale
    for key in weight_keys:
        prefix = key[: -len(".weight")]
        w = weights[key]
        acc_scale *= w["scale"]
        bias_float = _as_float(weights[f"{prefix}.bias"])
        W = [[int(v) for v in row] for row in w["values"]]
        B = [int(round(b * acc_scale)) for b in bias_float]
        layers.append((W, B))
    return Network(name=name, layers=layers, input_scale=input_scale, inputs=inputs, labels=labels)


def _check_int32(values, where: str):
    for v in values:
        if not INT32_MIN <= v <= INT32_MAX:
            raise OverflowError(f"{where}: {v} does not fit in {LOGIT_BITS} signed bits")


def forward(net: Network, x: list) -> tuple[list, int]:
    """Run one input vector through the integer network. Returns (logits, cls)."""
    act = list(x)
    for index, (W, B) in enumerate(net.layers):
        acc = [sum(w * a for w, a in zip(row, act)) + b for row, b in zip(W, B)]
        _check_int32(acc, f"{net.name} layer {index + 1}")
        last = index == len(net.layers) - 1
        act = acc if last else [max(v, 0) for v in acc]
    if net.n_outputs == 1:
        cls = 1 if act[0] > 0 else 0
    else:
        cls = max(range(len(act)), key=lambda i: (act[i], -i))
    return act, cls


def reference_outputs(net: Network) -> list[tuple[list, int]]:
    """Expected (logits, cls) for every test input of the network."""
    return [forward(net, x) for x in net.inputs]


def load_network(keyword: str | None) -> Network | None:
    """Load a preset's integer network from the cache, or None if it has no reference."""
    if keyword == "xor":
        with open(os.path.join(CACHE_DIR, "xor_weights.json")) as f:
            weights = json.load(f)
        return quantized_network("xor", weights, 1.0, XOR_INPUTS, XOR_LABELS)
    if keyword == "iris":
        with open(os.path.join(CACHE_DIR, "iris_weights.json")) as f:
            weights = json.load(f)
        with open(os.path.join(CACHE_DIR, "iris_inputs.json")) as f:
            data = json.load(f)
        return quantized_network("iris", weights, data["input_scale"], data["inputs"], data["labels"])
    return None


# ---------------------------------------------------------------------------
# Hand-off to the LLM
# ---------------------------------------------------------------------------

def _literal(value: int, bits: int) -> str:
    return f"-{bits}'sd{abs(value)}" if value < 0 else f"{bits}'sd{value}"


def network_params(net: Network) -> str:
    """Verilog localparams for the integer network: one unique name per constant."""
    lines = []
    for index, (W, B) in enumerate(net.layers, start=1):
        for r, row in enumerate(W):
            for c, value in enumerate(row):
                lines.append(f"localparam signed [7:0] W{index}_{r}_{c} = {_literal(value, 8)};")
        for r, value in enumerate(B):
            lines.append(f"localparam signed [31:0] B{index}_{r} = {_literal(value, 32)};")
    return "\n".join(lines)


def tensor_params(weights: dict) -> str:
    """Verilog localparams for presets without a reference (attention): `<TENSOR>_<row>_<col>`."""
    lines = []
    for name, entry in weights.items():
        base = name.replace(".", "_").upper()
        values = entry["values"]
        rows = values if isinstance(values[0], list) else [[v] for v in values]
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                lines.append(f"localparam signed [7:0] {base}_{r}_{c} = {_literal(int(value), 8)};")
    return "\n".join(lines)


def port_contract(net: Network) -> str:
    """The exact interface and arithmetic the generated testbench drives and checks."""
    n_in, n_out = net.n_inputs, net.n_outputs
    x_bits, z_bits, c_bits = n_in * INPUT_BITS, n_out * LOGIT_BITS, net.cls_bits
    hidden = len(net.layers[0][0])
    cls_rule = "cls = (z[0] > 0)" if n_out == 1 else "cls = index of the largest z (lowest index wins ties)"
    lines = [
        "PORT CONTRACT (NeuralForge generates the testbench from a bit-exact reference; your design must match it exactly):",
        "  input  wire clk",
        "  input  wire rst                          // active high",
        "  input  wire start",
        f"  input  wire [{x_bits - 1}:0] x_flat              // x_i = $signed(x_flat[8*i+7 : 8*i]), i = 0..{n_in - 1}",
        "  output wire done",
        f"  output wire [{z_bits - 1}:0] logits_flat        // z_j = logits_flat[32*j+31 : 32*j], signed, j = 0..{n_out - 1}",
        f"  output wire [{c_bits - 1}:0] cls",
        "ARITHMETIC (all 32-bit signed, no rescaling between layers):",
        f"  h_k = max(0, sum_i W1_k_i * x_i + B1_k)      k = 0..{hidden - 1}",
        f"  z_j = sum_k W2_j_k * h_k + B2_j",
        f"  {cls_rule}",
        "HANDSHAKE: the testbench holds x_flat steady, raises start, and waits up to 64 clock cycles for done = 1,",
        "then reads logits_flat and cls. done must fall within 16 cycles after start falls.",
        "A purely combinational design satisfies this with: assign done = start;",
    ]
    return "\n".join(lines)
