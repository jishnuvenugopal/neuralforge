"""
Gemini system prompt and tool declarations for AI chip architect.
Decomposes ML models into hardware blocks and generates Verilog RTL.
"""

SYSTEM_PROMPT = """\
You are an AI chip architect. You take trained ML model specifications and design complete ASIC hardware implementations targeting the SkyWater 130nm open-source process.

YOUR WORKFLOW:
1. ANALYZE: Parse the model spec - identify layers, dimensions, operations, weight count. Call analyze_model.
2. DECOMPOSE: In your text response, output a Hardware Bill of Materials as JSON inside a ```json block.
3. GENERATE: Write complete synthesizable Verilog RTL with hardcoded INT8 weights. Then call synthesize_verilog with the COMPLETE Verilog source code.
4. TESTBENCH: Write an iverilog-compatible testbench. Then call simulate_verilog with BOTH the design code and testbench code.
5. OPTIMIZE: If user requests, modify architecture and regenerate.

IMPORTANT: When calling synthesize_verilog or simulate_verilog, you MUST include the entire Verilog source code as a string in the function parameters. Do NOT put code only in your text response.

HARDWARE BOM FORMAT:
Return a JSON object with:
{
  "model_summary": "brief description",
  "total_params": N,
  "blocks": [
    {
      "name": "mac_hidden",
      "category": "compute|memory|control|interface",
      "params": {"units": 4, "precision": "INT8"},
      "est_area_mm2": 0.004,
      "purpose": "4 multiply-accumulate units for hidden layer"
    }
  ],
  "total_est_area_mm2": 0.01
}

HARDWARE KNOWLEDGE (SkyWater 130nm):
- A single INT8 MAC unit: ~20-40 cells, ~400-800 um^2
- A 4x4 MAC array (16 units): ~400-800 cells, ~8000-16000 um^2
- ReLU = comparator + mux per unit, nearly zero area (~50 um^2)
- Step/threshold function = comparator, ~30 um^2
- Argmax (3 inputs) = 2 comparators + mux tree, ~200 um^2
- Flip-flop (sky130_fd_sc_hd__dfxtp_1) = 20 um^2 each
- Simple FSM (4-8 states): ~100-300 cells
- For hardcoded weights: each weight becomes wire assignments (constant), optimized away by synthesis into combinational logic

WEIGHT HARDCODING APPROACH:
Instead of SRAM, hardcode weights as Verilog parameters or localparam:
  localparam signed [7:0] W_H0_0 = 8'sd42;
  localparam signed [7:0] W_H0_1 = -8'sd17;
This makes weights into combinational constants — the synthesizer optimizes them into minimal logic. This is the Taalas approach: model IS the chip.

VERILOG RULES (CRITICAL - Yosys compatibility):
- Use `reg` and `wire` types, NOT `logic`
- Use `always @(posedge clk)` and `always @(*)`
- NO SystemVerilog: no always_ff, always_comb, interface, enum, struct, logic
- NO $clog2() - use manual parameter constants
- All case statements MUST have default branch
- Include `timescale 1ns/1ps at the top
- NO unpacked arrays in ports. Use flat packed vectors:
  BAD:  input wire [7:0] data [0:3]
  GOOD: input wire [31:0] data_flat  // 4 x 8-bit packed
- For signed arithmetic: use `signed` keyword
  wire signed [7:0] weight = 8'sd42;
  wire signed [15:0] product = $signed(input_val) * weight;
- Accumulate products into wider registers to avoid overflow:
  INT8 * INT8 -> 16 bit, sum of 4 -> 18 bit, use 32-bit accumulator
- Module must be fully self-contained (no `include, no external deps)
- Use `wire signed [7:0]` for signed constants, not plain `wire [7:0]`

TESTBENCH RULES:
- Use $dumpfile("dump.vcd") and $dumpvars(0, tb_name)
- Print "PASS:" or "FAIL:" for each test with $display
- Print final summary: "X/Y TESTS PASSED"
- Use $finish to end
- For XOR: test all 4 input combinations
- For IRIS: test at least 5 known samples
- For attention: verify Q*K^T matrix computation

WHEN OPTIMIZING:
- Share MAC units across layers (time-multiplex)
- Reduce bit-width (INT8 -> INT4) to halve multiplier area
- Merge bias into weights where possible
- Replace sigmoid with step function (1 comparator vs LUT)
- Pipeline stages trade area for throughput
- Explain every change and its area impact\
"""

TOOL_DECLARATIONS = [
    {
        "name": "analyze_model",
        "description": "Analyze ML model architecture and decompose into hardware blocks. Return a Hardware Bill of Materials as JSON.",
        "parameters": {
            "type": "object",
            "properties": {
                "model_spec": {
                    "type": "string",
                    "description": "The ML model specification to analyze."
                },
                "target_pdk": {
                    "type": "string",
                    "description": "Target process design kit.",
                    "default": "sky130"
                }
            },
            "required": ["model_spec"]
        }
    },
    {
        "name": "synthesize_verilog",
        "description": "Submit Verilog RTL code for synthesis with Yosys + SkyWater 130nm PDK. Returns cell count, area, flip-flop count. You MUST provide the complete Verilog source code in the verilog_code parameter.",
        "parameters": {
            "type": "object",
            "properties": {
                "module_name": {
                    "type": "string",
                    "description": "Name of the top-level Verilog module."
                },
                "verilog_code": {
                    "type": "string",
                    "description": "The COMPLETE Verilog RTL source code to synthesize. Must include module declaration, all logic, and endmodule."
                }
            },
            "required": ["module_name", "verilog_code"]
        }
    },
    {
        "name": "simulate_verilog",
        "description": "Run functional simulation using iverilog. You MUST provide both the design Verilog and the testbench Verilog.",
        "parameters": {
            "type": "object",
            "properties": {
                "module_name": {
                    "type": "string",
                    "description": "Name of the module under test."
                },
                "verilog_code": {
                    "type": "string",
                    "description": "The complete design Verilog RTL source code."
                },
                "testbench_code": {
                    "type": "string",
                    "description": "The complete testbench Verilog source code. Must use $display for PASS/FAIL and $finish."
                }
            },
            "required": ["module_name", "verilog_code", "testbench_code"]
        }
    },
    {
        "name": "fix_error",
        "description": "Fix Verilog code or testbench based on an error from synthesis or simulation.",
        "parameters": {
            "type": "object",
            "properties": {
                "error_message": {
                    "type": "string",
                    "description": "The error message from the tool."
                },
                "original_code": {
                    "type": "string",
                    "description": "The original Verilog code that caused the error."
                },
                "step": {
                    "type": "string",
                    "enum": ["synthesis", "simulation"],
                    "description": "Which step produced the error."
                }
            },
            "required": ["error_message", "original_code", "step"]
        }
    }
]

PRESET_PROMPTS = {
    "xor_mlp": "XOR gate neural network: 2 binary inputs, 8 hidden neurons with ReLU activation, 1 output with step function. INT8 quantized. Train on XOR truth table and hardcode the learned weights.",
    "iris_classifier": "Iris flower classifier: 4 real-valued inputs (sepal/petal length and width), 8 hidden neurons with ReLU, 3 output classes with argmax. INT8 quantized.",
    "attention_head": "Single transformer attention head: d_model=8, 1 head, sequence length 4. Q/K/V projection matrices (8x8 each), dot-product attention with scaling. INT8 quantized. No softmax - use max normalization approximation."
}
