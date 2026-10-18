"""
Correct RTL for a golden network, written by hand-rolled codegen. The tests use
it as the honest design that must pass, and mutate it to build the exploits.
"""

from golden import Network, network_params


def reference_rtl(net: Network, module_name: str, registered: bool = False) -> str:
    n_in, n_out, c_bits = net.n_inputs, net.n_outputs, net.cls_bits
    (W1, _), (W2, _) = net.layers
    lines = [
        "`timescale 1ns/1ps",
        f"module {module_name} (",
        "  input  wire clk,",
        "  input  wire rst,",
        "  input  wire start,",
        f"  input  wire [{n_in * 8 - 1}:0] x_flat,",
        "  output wire done,",
        f"  output wire [{n_out * 32 - 1}:0] logits_flat,",
        f"  output wire [{c_bits - 1}:0] cls",
        ");",
    ]
    lines += ["  " + line for line in network_params(net).splitlines()]
    for i in range(n_in):
        lines.append(f"  wire signed [7:0] x{i} = x_flat[{8 * i + 7}:{8 * i}];")
    for k in range(len(W1)):
        terms = " + ".join(f"W1_{k}_{i} * x{i}" for i in range(n_in))
        lines.append(f"  wire signed [31:0] a{k} = {terms} + B1_{k};")
        lines.append(f"  wire signed [31:0] h{k} = (a{k} > 0) ? a{k} : 32'sd0;")
    for j in range(n_out):
        terms = " + ".join(f"W2_{j}_{k} * h{k}" for k in range(len(W1)))
        lines.append(f"  wire signed [31:0] z{j} = {terms} + B2_{j};")

    if n_out == 1:
        lines.append(f"  wire [{c_bits - 1}:0] cls_c = (z0 > 0) ? 1'b1 : 1'b0;")
    else:
        lines.append("  wire signed [31:0] best0 = z0;")
        lines.append(f"  wire [{c_bits - 1}:0] idx0 = {c_bits}'d0;")
        for j in range(1, n_out):
            lines.append(f"  wire take{j} = z{j} > best{j - 1};")
            lines.append(f"  wire signed [31:0] best{j} = take{j} ? z{j} : best{j - 1};")
            lines.append(f"  wire [{c_bits - 1}:0] idx{j} = take{j} ? {c_bits}'d{j} : idx{j - 1};")
        lines.append(f"  wire [{c_bits - 1}:0] cls_c = idx{n_out - 1};")

    packed = "{" + ", ".join(f"z{j}" for j in reversed(range(n_out))) + "}"
    if registered:
        lines += [
            "  reg done_r;",
            f"  reg [{n_out * 32 - 1}:0] logits_r;",
            f"  reg [{c_bits - 1}:0] cls_r;",
            "  always @(posedge clk or posedge rst) begin",
            "    if (rst) begin",
            "      done_r <= 1'b0;",
            "      logits_r <= 0;",
            "      cls_r <= 0;",
            "    end else begin",
            "      done_r <= start;",
            f"      logits_r <= {packed};",
            "      cls_r <= cls_c;",
            "    end",
            "  end",
            "  assign done = done_r;",
            "  assign logits_flat = logits_r;",
            "  assign cls = cls_r;",
        ]
    else:
        lines += [
            "  assign done = start;",
            f"  assign logits_flat = {packed};",
            "  assign cls = cls_c;",
        ]
    lines.append("endmodule")
    return "\n".join(lines) + "\n"
