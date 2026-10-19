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


def attention_rtl(ref, module_name: str) -> str:
    """Combinational RTL for golden.AttentionReference."""
    T, D = ref.TOKENS, ref.DIM
    lines = [
        "`timescale 1ns/1ps",
        f"module {module_name} (",
        "  input  wire clk,",
        "  input  wire rst,",
        "  input  wire start,",
        f"  input  wire [{T * D * 8 - 1}:0] x_flat,",
        "  output wire done,",
        f"  output wire [{T * D * 32 - 1}:0] logits_flat,",
        f"  output wire [{2 * T - 1}:0] cls",
        ");",
    ]
    lines += ["  " + line for line in ref.params_text().splitlines()]
    for t in range(T):
        for i in range(D):
            n = D * t + i
            lines.append(f"  wire signed [7:0] x{t}_{i} = x_flat[{8 * n + 7}:{8 * n}];")
    for p in "QKV":
        for t in range(T):
            for j in range(D):
                terms = " + ".join(f"W{p}_{j}_{i} * x{t}_{i}" for i in range(D))
                lines.append(f"  wire signed [31:0] {p.lower()}a{t}_{j} = {terms};")
                lines.append(f"  wire signed [31:0] {p.lower()}{t}_{j} = {p.lower()}a{t}_{j} >>> {ref.PROJ_SHIFT};")
    outs, sels = [], []
    for t in range(T):
        for u in range(T):
            terms = " + ".join(f"q{t}_{j} * k{u}_{j}" for j in range(D))
            lines.append(f"  wire signed [31:0] sa{t}_{u} = {terms};")
            lines.append(f"  wire signed [31:0] s{t}_{u} = sa{t}_{u} >>> {ref.SCORE_SHIFT};")
        lines.append(f"  wire signed [31:0] best{t}_0 = s{t}_0;")
        lines.append(f"  wire [1:0] sel{t}_0 = 2'd0;")
        for u in range(1, T):
            lines.append(f"  wire take{t}_{u} = s{t}_{u} > best{t}_{u - 1};")
            lines.append(f"  wire signed [31:0] best{t}_{u} = take{t}_{u} ? s{t}_{u} : best{t}_{u - 1};")
            lines.append(f"  wire [1:0] sel{t}_{u} = take{t}_{u} ? 2'd{u} : sel{t}_{u - 1};")
        sel = f"sel{t}_{T - 1}"
        sels.append(sel)
        for j in range(D):
            mux = " : ".join(f"({sel} == 2'd{u}) ? v{u}_{j}" for u in range(T - 1)) + f" : v{T - 1}_{j}"
            lines.append(f"  wire signed [31:0] o{t}_{j} = {mux};")
            outs.append(f"o{t}_{j}")
    lines += [
        "  assign done = start;",
        "  assign logits_flat = {" + ", ".join(reversed(outs)) + "};",
        "  assign cls = {" + ", ".join(reversed(sels)) + "};",
        "endmodule",
    ]
    return "\n".join(lines) + "\n"
