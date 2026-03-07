import { useCallback, useEffect, useReducer, useRef, useState } from "react";

const MOCK_SEQUENCE = [
  { delay: 300, msg: { type: "status", message: "Analyzing model architecture..." } },
  {
    delay: 1500,
    msg: {
      type: "agent_message",
      text: '## Hardware Bill of Materials\n\nI\'ll design a hardcoded XOR MLP with these blocks:\n\n```json\n{"model_summary": "XOR 2-8-1 MLP with hardcoded INT8 weights", "total_params": 33, "blocks": [{"name": "hidden_layer_mac", "category": "compute", "params": {"units": 8, "precision": "INT8"}, "est_area_mm2": 0.006, "purpose": "8 MAC units for hidden layer"}, {"name": "output_layer_mac", "category": "compute", "params": {"units": 1, "precision": "INT8"}, "est_area_mm2": 0.001, "purpose": "1 MAC unit for output layer"}], "total_est_area_mm2": 0.0070}\n```',
    },
  },
  { delay: 2500, msg: { type: "status", message: "Generating Verilog RTL..." } },
  {
    delay: 4000,
    msg: {
      type: "block_rtl",
      block_name: "xor_mlp",
      code: "`timescale 1ns/1ps\nmodule xor_mlp (\n    input wire clk,\n    input wire rst_n,\n    input wire signed [7:0] in_a,\n    input wire signed [7:0] in_b,\n    input wire valid_in,\n    output reg [7:0] result,\n    output reg valid_out\n);\n\n    // Hardcoded INT8 weights (from trained PyTorch model)\n    localparam signed [7:0] W_H00 =  8'sd85;\n    localparam signed [7:0] W_H01 = -8'sd42;\n    localparam signed [7:0] W_H10 =  8'sd73;\n    localparam signed [7:0] W_H11 = -8'sd91;\n    localparam signed [7:0] W_H20 = -8'sd64;\n    localparam signed [7:0] W_H21 =  8'sd38;\n    localparam signed [7:0] W_H30 =  8'sd55;\n    localparam signed [7:0] W_H31 =  8'sd67;\n    localparam signed [7:0] W_H40 = -8'sd88;\n    localparam signed [7:0] W_H41 =  8'sd92;\n    localparam signed [7:0] W_H50 =  8'sd47;\n    localparam signed [7:0] W_H51 =  8'sd79;\n    localparam signed [7:0] W_H60 = -8'sd71;\n    localparam signed [7:0] W_H61 = -8'sd58;\n    localparam signed [7:0] W_H70 =  8'sd96;\n    localparam signed [7:0] W_H71 =  8'sd24;\n\n    localparam signed [7:0] B_H0 = -8'sd12;\n    localparam signed [7:0] B_H1 =  8'sd5;\n    localparam signed [7:0] B_H2 =  8'sd20;\n    localparam signed [7:0] B_H3 = -8'sd8;\n    localparam signed [7:0] B_H4 =  8'sd11;\n    localparam signed [7:0] B_H5 = -8'sd19;\n    localparam signed [7:0] B_H6 =  8'sd7;\n    localparam signed [7:0] B_H7 = -8'sd4;\n\n    localparam signed [7:0] W_O0 =  8'sd100;\n    localparam signed [7:0] W_O1 = -8'sd95;\n    localparam signed [7:0] W_O2 = -8'sd88;\n    localparam signed [7:0] W_O3 =  8'sd76;\n    localparam signed [7:0] W_O4 =  8'sd82;\n    localparam signed [7:0] W_O5 = -8'sd67;\n    localparam signed [7:0] W_O6 =  8'sd91;\n    localparam signed [7:0] W_O7 = -8'sd73;\n    localparam signed [7:0] B_O = -8'sd3;\n\n    localparam IDLE    = 2'd0;\n    localparam COMPUTE = 2'd1;\n    localparam DONE    = 2'd2;\n\n    reg [1:0] state;\n    reg signed [15:0] h0, h1, h2, h3, h4, h5, h6, h7;\n    wire signed [15:0] r0, r1, r2, r3, r4, r5, r6, r7;\n    reg signed [23:0] out_acc;\n\n    assign r0 = (h0 > 0) ? h0 : 16'sd0;\n    assign r1 = (h1 > 0) ? h1 : 16'sd0;\n    assign r2 = (h2 > 0) ? h2 : 16'sd0;\n    assign r3 = (h3 > 0) ? h3 : 16'sd0;\n    assign r4 = (h4 > 0) ? h4 : 16'sd0;\n    assign r5 = (h5 > 0) ? h5 : 16'sd0;\n    assign r6 = (h6 > 0) ? h6 : 16'sd0;\n    assign r7 = (h7 > 0) ? h7 : 16'sd0;\n\n    always @(posedge clk or negedge rst_n) begin\n        if (!rst_n) begin\n            state     <= IDLE;\n            result    <= 8'd0;\n            valid_out <= 1'b0;\n        end else begin\n            case (state)\n                IDLE: begin\n                    valid_out <= 1'b0;\n                    if (valid_in) begin\n                        h0 <= in_a * W_H00 + in_b * W_H01 + B_H0;\n                        h1 <= in_a * W_H10 + in_b * W_H11 + B_H1;\n                        h2 <= in_a * W_H20 + in_b * W_H21 + B_H2;\n                        h3 <= in_a * W_H30 + in_b * W_H31 + B_H3;\n                        h4 <= in_a * W_H40 + in_b * W_H41 + B_H4;\n                        h5 <= in_a * W_H50 + in_b * W_H51 + B_H5;\n                        h6 <= in_a * W_H60 + in_b * W_H61 + B_H6;\n                        h7 <= in_a * W_H70 + in_b * W_H71 + B_H7;\n                        state <= COMPUTE;\n                    end\n                end\n                COMPUTE: begin\n                    out_acc <= r0 * W_O0 + r1 * W_O1 + r2 * W_O2 + r3 * W_O3 +\n                               r4 * W_O4 + r5 * W_O5 + r6 * W_O6 + r7 * W_O7 + B_O;\n                    state <= DONE;\n                end\n                DONE: begin\n                    result    <= (out_acc > 0) ? 8'd1 : 8'd0;\n                    valid_out <= 1'b1;\n                    state     <= IDLE;\n                end\n            endcase\n        end\n    end\n\nendmodule",
      iteration: 1,
    },
  },
  { delay: 4500, msg: { type: "status", message: "Synthesizing with Yosys + SkyWater 130nm..." } },
  {
    delay: 6000,
    msg: {
      type: "block_synth_result",
      block_name: "xor_mlp",
      stats: { total_cells: 463, flip_flops: 26, area_um2: 9184.3, wires: 198 },
      success: true,
      log_tail: "ABC RESULTS:            sky130 cells:         463\nABC RESULTS:        SkyWater area:     9184.30 um^2\n\n   Number of wires:                198\n   Number of wire bits:            604\n   Number of public wires:          16\n   Number of cells:                463\n     sky130_fd_sc_hd__a21o_2        16\n     sky130_fd_sc_hd__a21oi_2       18\n     sky130_fd_sc_hd__and2_2        22\n     sky130_fd_sc_hd__clkbuf_1       6\n     sky130_fd_sc_hd__dfxtp_2       26\n     sky130_fd_sc_hd__inv_2         34\n     sky130_fd_sc_hd__mux2_1        18\n     sky130_fd_sc_hd__nand2_2       58\n     sky130_fd_sc_hd__nor2_2        42\n     sky130_fd_sc_hd__o21ai_2       29\n     sky130_fd_sc_hd__or2_2         15\n     sky130_fd_sc_hd__xnor2_2       81\n     sky130_fd_sc_hd__xor2_2        98",
      svg: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 320"><rect width="640" height="320" fill="#f8fafc"/><text x="320" y="28" text-anchor="middle" font-family="monospace" font-size="14" fill="#0f172a">xor_mlp - Synthesized Netlist</text><rect x="48" y="72" width="132" height="58" rx="10" fill="#e0f2fe" stroke="#0284c7" stroke-width="1.5"/><text x="114" y="96" text-anchor="middle" font-family="monospace" font-size="10" fill="#0369a1">MAC hidden 0-3</text><text x="114" y="114" text-anchor="middle" font-family="monospace" font-size="8" fill="#475569">4 parallel INT8 MACs</text><rect x="48" y="164" width="132" height="58" rx="10" fill="#e0f2fe" stroke="#0284c7" stroke-width="1.5"/><text x="114" y="188" text-anchor="middle" font-family="monospace" font-size="10" fill="#0369a1">MAC hidden 4-7</text><text x="114" y="206" text-anchor="middle" font-family="monospace" font-size="8" fill="#475569">4 parallel INT8 MACs</text><rect x="254" y="92" width="132" height="48" rx="10" fill="#ecfeff" stroke="#0891b2" stroke-width="1.5"/><text x="320" y="119" text-anchor="middle" font-family="monospace" font-size="10" fill="#0e7490">ReLU bank x8</text><rect x="254" y="176" width="132" height="48" rx="10" fill="#fef3c7" stroke="#d97706" stroke-width="1.5"/><text x="320" y="203" text-anchor="middle" font-family="monospace" font-size="10" fill="#b45309">Control FSM</text><rect x="460" y="108" width="126" height="54" rx="10" fill="#dbeafe" stroke="#2563eb" stroke-width="1.5"/><text x="523" y="132" text-anchor="middle" font-family="monospace" font-size="10" fill="#1d4ed8">Output MAC</text><text x="523" y="150" text-anchor="middle" font-family="monospace" font-size="8" fill="#475569">8-term accumulate</text><rect x="460" y="188" width="126" height="42" rx="10" fill="#fee2e2" stroke="#dc2626" stroke-width="1.5"/><text x="523" y="214" text-anchor="middle" font-family="monospace" font-size="10" fill="#b91c1c">Step threshold</text><line x1="180" y1="101" x2="254" y2="116" stroke="#94a3b8" stroke-width="1.5"/><line x1="180" y1="193" x2="254" y2="116" stroke="#94a3b8" stroke-width="1.5"/><line x1="386" y1="116" x2="460" y2="135" stroke="#94a3b8" stroke-width="1.5"/><line x1="586" y1="135" x2="622" y2="135" stroke="#94a3b8" stroke-width="1.5"/><line x1="586" y1="209" x2="622" y2="209" stroke="#94a3b8" stroke-width="1.5"/><text x="622" y="138" font-family="monospace" font-size="8" fill="#475569">result[7:0]</text><text x="622" y="212" font-family="monospace" font-size="8" fill="#475569">valid_out</text><text x="22" y="104" font-family="monospace" font-size="8" fill="#475569">in_a</text><text x="22" y="196" font-family="monospace" font-size="8" fill="#475569">in_b</text><text x="22" y="250" font-family="monospace" font-size="8" fill="#475569">valid_in</text><line x1="40" y1="101" x2="48" y2="101" stroke="#94a3b8" stroke-width="1.5"/><line x1="40" y1="193" x2="48" y2="193" stroke="#94a3b8" stroke-width="1.5"/><line x1="40" y1="248" x2="48" y2="220" stroke="#94a3b8" stroke-width="1.5"/><text x="320" y="292" text-anchor="middle" font-family="monospace" font-size="10" fill="#64748b">463 cells | 26 FFs | 9184 um^2 | sky130_fd_sc_hd</text></svg>',
      iteration: 1,
    },
  },
  { delay: 6500, msg: { type: "status", message: "Running functional simulation..." } },
  {
    delay: 8000,
    msg: {
      type: "simulation_result",
      passed: true,
      pass_count: 4,
      total_count: 4,
      output: "VCD info: dumpfile xor_mlp_tb.vcd opened for output.\n\n=== XOR MLP Functional Test ===\nInput [0,0] -> 0  PASS\nInput [0,1] -> 1  PASS\nInput [1,0] -> 1  PASS\nInput [1,1] -> 0  PASS\n\n4/4 TESTS PASSED\nSimulation time: 800ns",
    },
  },
  { delay: 9000, msg: { type: "complete", iterations: 3 } },
];

const PRESETS = [
  {
    label: "XOR MLP",
    prompt: "Build a 2-input XOR gate using a 2-8-1 MLP with hardcoded INT8 weights",
    note: "Tiny, fast demo path",
  },
  {
    label: "IRIS Classifier",
    prompt: "Build an IRIS flower classifier neural network with 4 inputs, 8 hidden units, 3 outputs",
    note: "Real dataset inference block",
  },
  {
    label: "Attention Head",
    prompt: "Build a single-head scaled dot-product attention block with 8-dim embeddings, sequence length 4",
    note: "Showpiece architecture",
  },
];

const TABS = [
  { id: "code", label: "RTL" },
  { id: "synthesis", label: "Synthesis" },
  { id: "netlist", label: "Netlist" },
  { id: "simulation", label: "Simulation" },
];

const initialState = {
  messages: [],
  bom: null,
  verilogCode: "",
  moduleName: "",
  synthStats: null,
  netlistSvg: "",
  simulation: null,
  layoutPng: "",
  loading: false,
  activeTab: "code",
  error: null,
};

const surfaceClass =
  "rounded-xl border border-border bg-card shadow-[0_1px_2px_rgba(15,23,42,0.05),0_12px_32px_rgba(15,23,42,0.04)]";
const outlineButtonClass =
  "inline-flex items-center justify-center rounded-md border border-input bg-background px-3.5 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent hover:text-accent-foreground disabled:pointer-events-none disabled:opacity-50";
const ghostButtonClass =
  "inline-flex items-center justify-center rounded-md px-3.5 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground disabled:pointer-events-none disabled:opacity-50";
const primaryButtonClass =
  "inline-flex items-center justify-center rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground shadow-sm transition-colors hover:bg-primary/90 disabled:pointer-events-none disabled:opacity-50";

function reducer(state, action) {
  switch (action.type) {
    case "status":
      return {
        ...state,
        messages: [...state.messages, { type: "status", text: action.message, time: new Date() }],
        loading: true,
      };
    case "agent_message": {
      const bomMatch = action.text.match(/```json\s*([\s\S]*?)```/);
      let newBom = state.bom;
      if (bomMatch) {
        try {
          newBom = JSON.parse(bomMatch[1]);
        } catch {
          // Ignore invalid JSON blocks from the model.
        }
      }
      return {
        ...state,
        messages: [...state.messages, { type: "agent", text: action.text, time: new Date() }],
        bom: newBom || state.bom,
      };
    }
    case "hardware_bom":
      const bomPayload = action.bom || action;
      return {
        ...state,
        bom: bomPayload,
        messages: [
          ...state.messages,
          {
            type: "bom",
            text: `Hardware BOM: ${bomPayload.blocks?.length || 0} blocks, ~${
              bomPayload.total_est_area_mm2 != null ? bomPayload.total_est_area_mm2.toFixed(4) : "?"
            } mm^2`,
            time: new Date(),
          },
        ],
      };
    case "block_rtl":
      return {
        ...state,
        verilogCode: action.code,
        moduleName: action.block_name,
        activeTab: "code",
        messages: [
          ...state.messages,
          { type: "rtl", text: `Verilog generated: ${action.block_name}`, time: new Date() },
        ],
      };
    case "block_synth_result":
      return {
        ...state,
        synthStats: { ...action.stats, log_tail: action.log_tail },
        netlistSvg: action.svg || state.netlistSvg,
        activeTab: "synthesis",
        messages: [
          ...state.messages,
          {
            type: "synth",
            text: `Synthesis complete: ${action.stats?.total_cells ?? "?"} cells, ${
              action.stats?.area_um2 != null ? action.stats.area_um2.toFixed(1) : "?"
            } um^2`,
            time: new Date(),
          },
        ],
      };
    case "simulation_result":
      return {
        ...state,
        simulation: action,
        activeTab: "simulation",
        messages: [
          ...state.messages,
          {
            type: "sim",
            text: `Simulation: ${action.pass_count}/${action.total_count} tests passed`,
            time: new Date(),
          },
        ],
      };
    case "hardening_result":
      if (!action.success) {
        return {
          ...state,
          messages: [
            ...state.messages,
            {
              type: "layout",
              text: `Layout hardening unavailable: ${action.error || "LibreLane is not ready yet"}`,
              time: new Date(),
            },
          ],
        };
      }
      return {
        ...state,
        layoutPng: action.gds_png,
        messages: [...state.messages, { type: "layout", text: "Layout artifact generated", time: new Date() }],
      };
    case "complete":
      return {
        ...state,
        loading: false,
        messages: [
          ...state.messages,
          { type: "done", text: `Pipeline complete in ${action.iterations} iteration(s)`, time: new Date() },
        ],
      };
    case "error":
      return {
        ...state,
        loading: false,
        error: action.message,
        messages: [...state.messages, { type: "error", text: action.message, time: new Date() }],
      };
    case "set_tab":
      return { ...state, activeTab: action.tab };
    case "reset":
      return { ...initialState };
    default:
      return state;
  }
}

function useWebSocket(url, dispatch) {
  const wsRef = useRef(null);

  const connect = useCallback(() => {
    const ws = new WebSocket(url);
    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        dispatch(msg);
      } catch {
        // Ignore non-JSON events.
      }
    };
    ws.onerror = () => dispatch({ type: "error", message: "WebSocket connection failed" });
    ws.onclose = () => {};
    wsRef.current = ws;
  }, [dispatch, url]);

  const send = useCallback(
    (data) => {
      const doSend = () => {
        try {
          wsRef.current?.send(JSON.stringify(data));
        } catch {
          // Ignore send failures; websocket error path handles user feedback.
        }
      };

      if (
        !wsRef.current ||
        wsRef.current.readyState === WebSocket.CLOSED ||
        wsRef.current.readyState === WebSocket.CLOSING
      ) {
        connect();
        const checkReady = setInterval(() => {
          if (wsRef.current?.readyState === WebSocket.OPEN) {
            clearInterval(checkReady);
            doSend();
          }
        }, 100);
        setTimeout(() => clearInterval(checkReady), 5000);
      } else if (wsRef.current.readyState === WebSocket.OPEN) {
        doSend();
      } else {
        setTimeout(doSend, 1000);
      }
    },
    [connect]
  );

  useEffect(() => {
    return () => wsRef.current?.close();
  }, []);

  return { send };
}

function highlightVerilog(code) {
  if (!code) return "";
  const escaped = code
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  return escaped
    .replace(/(\/\/.*)/g, '<span style="color:#64748b;font-style:italic">$1</span>')
    .replace(/(".*?")/g, '<span style="color:#f59e0b">$1</span>')
    .replace(
      /\b(module|endmodule|input|output|inout|wire|reg|always|begin|end|assign|localparam|parameter|if|else|case|endcase|default|posedge|negedge|or|and|not|signed)\b/g,
      '<span style="color:#c084fc">$1</span>'
    )
    .replace(/(`timescale|`define|`ifdef|`endif)\b/g, '<span style="color:#38bdf8">$1</span>')
    .replace(/\b(\d+\'[sdSDbBhHoO][0-9a-fA-F_]+)\b/g, '<span style="color:#34d399">$1</span>')
    .replace(/\b(\d+)\b/g, '<span style="color:#34d399">$1</span>');
}

function cx(...classes) {
  return classes.filter(Boolean).join(" ");
}

function fmtTime(date) {
  return date.toLocaleTimeString("en-US", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatValue(value, digits = 0) {
  if (value == null || value === "") return "--";
  if (typeof value === "number") {
    return digits > 0 ? value.toFixed(digits) : value.toLocaleString();
  }
  return value;
}

function summarizeMessage(type, text) {
  if (type !== "agent" || !text) return text;
  return text.replace(/```json[\s\S]*?```/g, "[Hardware BOM JSON attached]").trim();
}

function messageMeta(type) {
  switch (type) {
    case "status":
      return {
        label: "Status",
        dot: "bg-amber-500",
        tone: "border-amber-200 bg-amber-50 text-amber-800",
      };
    case "bom":
      return {
        label: "BOM",
        dot: "bg-sky-500",
        tone: "border-sky-200 bg-sky-50 text-sky-800",
      };
    case "rtl":
      return {
        label: "RTL",
        dot: "bg-violet-500",
        tone: "border-violet-200 bg-violet-50 text-violet-800",
      };
    case "synth":
      return {
        label: "Synthesis",
        dot: "bg-cyan-500",
        tone: "border-cyan-200 bg-cyan-50 text-cyan-800",
      };
    case "sim":
      return {
        label: "Simulation",
        dot: "bg-emerald-500",
        tone: "border-emerald-200 bg-emerald-50 text-emerald-800",
      };
    case "layout":
      return {
        label: "Layout",
        dot: "bg-indigo-500",
        tone: "border-indigo-200 bg-indigo-50 text-indigo-800",
      };
    case "done":
      return {
        label: "Complete",
        dot: "bg-emerald-500",
        tone: "border-emerald-200 bg-emerald-50 text-emerald-800",
      };
    case "error":
      return {
        label: "Error",
        dot: "bg-red-500",
        tone: "border-red-200 bg-red-50 text-red-800",
      };
    case "agent":
      return {
        label: "Agent",
        dot: "bg-slate-500",
        tone: "border-border bg-muted text-foreground",
      };
    default:
      return {
        label: "Event",
        dot: "bg-slate-400",
        tone: "border-border bg-muted text-foreground",
      };
  }
}

function categoryTone(category) {
  switch (category) {
    case "compute":
      return "border-sky-200 bg-sky-50 text-sky-700";
    case "memory":
      return "border-emerald-200 bg-emerald-50 text-emerald-700";
    case "control":
      return "border-amber-200 bg-amber-50 text-amber-700";
    case "interface":
      return "border-violet-200 bg-violet-50 text-violet-700";
    default:
      return "border-border bg-muted text-muted-foreground";
  }
}

function Badge({ children, tone = "default", className = "" }) {
  const tones = {
    default: "border-transparent bg-secondary text-secondary-foreground",
    outline: "border-border bg-background text-foreground",
    muted: "border-transparent bg-muted text-muted-foreground",
    info: "border-sky-200 bg-sky-50 text-sky-700",
    success: "border-emerald-200 bg-emerald-50 text-emerald-700",
    warning: "border-amber-200 bg-amber-50 text-amber-700",
    destructive: "border-red-200 bg-red-50 text-red-700",
    violet: "border-violet-200 bg-violet-50 text-violet-700",
  };

  return (
    <span
      className={cx(
        "inline-flex items-center gap-2 rounded-md border px-2.5 py-1 text-xs font-medium",
        tones[tone] || tones.default,
        className
      )}
    >
      {children}
    </span>
  );
}

function ShellCard({ title, description, action, children, className = "", contentClassName = "" }) {
  return (
    <section className={cx(surfaceClass, "flex min-h-0 flex-col overflow-hidden", className)}>
      <div className="border-b border-border px-5 py-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="space-y-1">
            <h2 className="text-sm font-semibold tracking-tight text-foreground">{title}</h2>
            {description ? <p className="text-sm text-muted-foreground">{description}</p> : null}
          </div>
          {action}
        </div>
      </div>
      <div className={cx("min-h-0 flex-1", contentClassName)}>{children}</div>
    </section>
  );
}

function EmptyState({ title, description, extra = null }) {
  return (
    <div className="flex h-full items-center justify-center p-8">
      <div className="max-w-sm text-center">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full border border-border bg-muted shadow-sm">
          <div className="h-2.5 w-2.5 rounded-full bg-muted-foreground/60" />
        </div>
        <h3 className="text-sm font-semibold text-foreground">{title}</h3>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">{description}</p>
        {extra ? <div className="mt-4">{extra}</div> : null}
      </div>
    </div>
  );
}

function ControlPanel({ state, onSubmit, onReset, loading, isMock }) {
  const [value, setValue] = useState("");
  const promptRef = useRef(null);
  const latestActivity = state.messages.at(-1)?.text || "Ready for a new model prompt";
  const blockCount = state.bom?.blocks?.length || 0;
  const latestModule = state.moduleName || "Awaiting generation";
  const simSummary = state.simulation
    ? `${state.simulation.pass_count}/${state.simulation.total_count} passing`
    : "No tests run";

  const submit = (text) => {
    const nextValue = (text ?? value).trim();
    if (!nextValue || loading) return;
    onSubmit(nextValue);
  };

  const handleKeyDown = (event) => {
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      submit();
    }
  };

  return (
    <section className={cx(surfaceClass, "overflow-hidden")}>
      <div className="border-b border-border bg-muted/40 px-5 py-4 sm:px-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone="outline">NeuralForge</Badge>
              <Badge tone={loading ? "success" : "muted"}>{loading ? "Pipeline running" : "Ready"}</Badge>
              {isMock ? <Badge tone="warning">Mock mode</Badge> : null}
            </div>
            <div className="space-y-2">
              <h1 className="text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
                Trained model to hardware.
              </h1>
              <p className="max-w-3xl text-sm leading-6 text-muted-foreground sm:text-base">
                Drive the Gemini loop, inspect the hardware bill of materials, and review RTL, synthesis,
                netlist, and simulation outputs from a single dashboard.
              </p>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-3 lg:w-[420px] lg:grid-cols-1">
            <MetricTile label="Blocks in BOM" value={blockCount} hint="Generated hardware components" tone="sky" />
            <MetricTile label="Latest module" value={latestModule} hint="Current RTL artifact" tone="violet" />
            <MetricTile label="Simulation" value={simSummary} hint="Functional test status" tone="emerald" />
          </div>
        </div>
      </div>

      <div className="grid gap-5 px-5 py-5 sm:px-6 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div className="space-y-5">
          <div className="space-y-2">
            <label htmlFor="prompt" className="text-sm font-medium text-foreground">
              Model prompt
            </label>
            <textarea
              ref={promptRef}
              id="prompt"
              value={value}
              onChange={(event) => setValue(event.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Describe the ML model or accelerator you want synthesized."
              className="min-h-[132px] w-full rounded-xl border border-input bg-background px-4 py-3 text-sm leading-6 text-foreground shadow-sm outline-none transition focus:border-ring focus:ring-2 focus:ring-ring/30"
              disabled={loading}
            />
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-xs text-muted-foreground">
                Click an example to load it into the prompt, then press Cmd/Ctrl + Enter or Run pipeline.
              </p>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => submit()}
                  disabled={loading || !value.trim()}
                  className={primaryButtonClass}
                >
                  {loading ? (
                    <>
                      <span className="h-4 w-4 animate-spin rounded-full border-2 border-primary-foreground/30 border-t-primary-foreground" />
                      Running pipeline
                    </>
                  ) : (
                    "Run pipeline"
                  )}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setValue("");
                    onReset();
                  }}
                  className={outlineButtonClass}
                >
                  Reset view
                </button>
              </div>
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-3">
            {PRESETS.map((preset) => (
              <button
                key={preset.label}
                type="button"
                onClick={() => {
                  setValue(preset.prompt);
                  requestAnimationFrame(() => {
                    promptRef.current?.focus();
                    promptRef.current?.setSelectionRange(preset.prompt.length, preset.prompt.length);
                  });
                }}
                disabled={loading}
                className="rounded-xl border border-input bg-background p-4 text-left transition hover:border-foreground/20 hover:bg-accent disabled:pointer-events-none disabled:opacity-50"
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm font-medium text-foreground">{preset.label}</span>
                  <Badge tone="muted" className="px-2 py-0.5 text-[10px]">
                    {preset.note}
                  </Badge>
                </div>
                <p className="mt-3 text-sm leading-6 text-muted-foreground">{preset.prompt}</p>
              </button>
            ))}
          </div>
        </div>

        <div className="rounded-xl border border-border bg-muted/30 p-4">
          <div className="space-y-3">
            <p className="text-xs font-medium uppercase tracking-[0.24em] text-muted-foreground">Latest activity</p>
            <div className="rounded-lg border border-border bg-background p-4 shadow-sm">
              <p className="text-sm leading-6 text-foreground">{latestActivity}</p>
            </div>
            <div className="grid gap-3">
              <div className="rounded-lg border border-border bg-background p-4 shadow-sm">
                <p className="text-xs font-medium uppercase tracking-[0.24em] text-muted-foreground">Area estimate</p>
                <p className="mt-2 text-lg font-semibold text-foreground">
                  {state.bom?.total_est_area_mm2 != null ? `${state.bom.total_est_area_mm2.toFixed(4)} mm^2` : "--"}
                </p>
              </div>
              <div className="rounded-lg border border-border bg-background p-4 shadow-sm">
                <p className="text-xs font-medium uppercase tracking-[0.24em] text-muted-foreground">Cells synthesized</p>
                <p className="mt-2 text-lg font-semibold text-foreground">
                  {state.synthStats?.total_cells != null ? state.synthStats.total_cells.toLocaleString() : "--"}
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function AgentLog({ messages, loading }) {
  const logRef = useRef(null);

  useEffect(() => {
    const logNode = logRef.current;
    if (!logNode) return;
    logNode.scrollTo({
      top: logNode.scrollHeight,
      behavior: "smooth",
    });
  }, [messages]);

  return (
    <ShellCard
      title="Agent log"
      description="Streaming events from the design loop."
      action={<Badge tone={loading ? "success" : "muted"}>{loading ? "Running" : "Idle"}</Badge>}
      contentClassName="overflow-hidden"
    >
      <div ref={logRef} className="panel-scroll h-full overflow-y-auto p-5">
        {messages.length === 0 ? (
          <EmptyState
            title="No events yet"
            description="Submit a model prompt to populate the design log with decomposition, RTL generation, synthesis, and simulation events."
          />
        ) : (
          <div className="space-y-3">
            {messages.map((message, index) => {
              const meta = messageMeta(message.type);
              return (
                <div
                  key={`${message.type}-${index}`}
                  className="rounded-xl border border-border bg-background p-4 shadow-sm transition-colors"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={cx("h-2.5 w-2.5 rounded-full", meta.dot)} />
                    <Badge tone="outline" className={cx("px-2 py-0.5 text-[10px]", meta.tone)}>
                      {meta.label}
                    </Badge>
                    <span className="ml-auto font-mono text-xs text-muted-foreground">{fmtTime(message.time)}</span>
                  </div>
                  <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-muted-foreground">
                    {summarizeMessage(message.type, message.text)}
                  </p>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </ShellCard>
  );
}

function HardwareBOM({ bom }) {
  const blocks = bom?.blocks || [];

  return (
    <ShellCard
      title="Hardware bill of materials"
      description="Model decomposition and block-level estimates."
      action={
        bom?.total_est_area_mm2 != null ? <Badge tone="info">{bom.total_est_area_mm2.toFixed(4)} mm²</Badge> : null
      }
      contentClassName="overflow-hidden"
    >
      {!bom ? (
        <EmptyState
          title="No BOM yet"
          description="Once the agent analyzes the model, the design blocks, parameter counts, and area estimates will appear here."
        />
      ) : (
        <div className="h-full overflow-y-auto p-5">
          <div className="space-y-4">
            <div className="rounded-xl border border-border bg-background p-4 shadow-sm">
              <p className="text-sm leading-6 text-muted-foreground">
                {bom.model_summary || "Model summary unavailable."}
              </p>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <MetricTile label="Blocks" value={blocks.length} hint="Hardware components" tone="sky" compact />
                <MetricTile
                  label="Parameters"
                  value={bom.total_params || 0}
                  hint="Quantized model weights"
                  tone="violet"
                  compact
                />
                <MetricTile
                  label="Area estimate"
                  value={bom.total_est_area_mm2 != null ? `${bom.total_est_area_mm2.toFixed(4)} mm²` : "--"}
                  hint="Pre-synthesis estimate"
                  tone="amber"
                  compact
                  className="sm:col-span-2"
                  valueClassName="font-mono"
                />
              </div>
            </div>

            <div className="grid gap-3">
              {blocks.map((block, index) => (
                <div
                  key={`${block.name}-${index}`}
                  className="rounded-xl border border-border bg-background p-4 shadow-sm"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <h3 className="text-sm font-semibold text-foreground">{block.name}</h3>
                      <p className="mt-1 text-sm leading-6 text-muted-foreground">
                        {block.purpose || "No description provided."}
                      </p>
                    </div>
                    <Badge tone="outline" className={categoryTone(block.category)}>
                      {block.category || "block"}
                    </Badge>
                  </div>

                  {block.params && Object.keys(block.params).length > 0 ? (
                    <div className="mt-4 flex flex-wrap gap-2">
                      {Object.entries(block.params).map(([key, value]) => (
                        <span
                          key={`${block.name}-${key}`}
                          className="inline-flex items-center rounded-md bg-muted px-2.5 py-1 text-xs text-muted-foreground"
                        >
                          {key}: {String(value)}
                        </span>
                      ))}
                    </div>
                  ) : null}

                  {block.est_area_mm2 != null ? (
                    <div className="mt-4 flex items-center justify-between gap-3 border-t border-border pt-4">
                      <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
                        Area estimate
                      </p>
                      <p className="font-mono text-sm font-medium text-foreground">
                        {block.est_area_mm2.toFixed(4)} mm²
                      </p>
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </ShellCard>
  );
}

function CodePanel({ code, moduleName }) {
  const [copied, setCopied] = useState(false);

  const copy = () => {
    navigator.clipboard
      .writeText(code)
      .then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      })
      .catch(() => {});
  };

  if (!code) {
    return (
      <EmptyState
        title="No RTL generated"
        description="Generated Verilog will appear here once the agent produces synthesizable source."
      />
    );
  }

  return (
    <div className="flex h-full flex-col p-5">
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-semibold text-foreground">{moduleName || "generated_module"}.v</p>
          <p className="text-sm text-muted-foreground">{code.split("\n").length} lines of Verilog RTL</p>
        </div>
        <button type="button" onClick={copy} className={outlineButtonClass}>
          {copied ? "Copied" : "Copy code"}
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden rounded-xl border border-slate-800 bg-slate-950 shadow-inner">
        <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3 text-xs text-slate-400">
          <div className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full bg-rose-400" />
            <span className="h-2.5 w-2.5 rounded-full bg-amber-400" />
            <span className="h-2.5 w-2.5 rounded-full bg-emerald-400" />
          </div>
          <span className="font-mono">{moduleName || "verilog"}</span>
        </div>
        <div className="editor-scroll h-full overflow-auto p-4">
          <pre className="font-mono text-sm leading-6 text-slate-100">
            <code dangerouslySetInnerHTML={{ __html: highlightVerilog(code) }} />
          </pre>
        </div>
      </div>
    </div>
  );
}

function MetricTile({
  label,
  value,
  hint,
  tone = "slate",
  compact = false,
  className = "",
  valueClassName = "",
}) {
  const tones = {
    slate: "bg-muted/60 text-foreground",
    sky: "bg-sky-50 text-sky-900",
    violet: "bg-violet-50 text-violet-900",
    amber: "bg-amber-50 text-amber-900",
    emerald: "bg-emerald-50 text-emerald-900",
  };

  return (
    <div className={cx("rounded-xl border border-border p-4 shadow-sm", tones[tone] || tones.slate, className)}>
      <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">{label}</p>
      <p
        className={cx(
          "mt-2 font-semibold tracking-tight text-balance",
          compact ? "text-xl leading-8" : "text-2xl",
          valueClassName
        )}
      >
        {formatValue(value)}
      </p>
      {hint ? <p className="mt-1 text-sm leading-6 text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

function SynthesisPanel({ stats }) {
  const [logExpanded, setLogExpanded] = useState(false);

  if (!stats) {
    return (
      <EmptyState
        title="No synthesis results"
        description="Yosys metrics, sky130 mapping details, and synthesized logs will appear here after RTL compilation."
      />
    );
  }

  return (
    <div className="h-full overflow-y-auto p-5">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <MetricTile label="Cells" value={stats.total_cells || 0} hint="Mapped standard cells" tone="sky" />
        <MetricTile label="Flip-flops" value={stats.flip_flops || 0} hint="Sequential elements" tone="emerald" />
        <MetricTile label="Area" value={stats.area_um2 != null ? `${stats.area_um2.toFixed(1)} um^2` : "--"} hint="Sky130 area" tone="amber" />
        <MetricTile label="Wires" value={stats.wires || 0} hint="Connectivity count" tone="violet" />
      </div>

      <div className="mt-5 flex flex-wrap items-center gap-2">
        <Badge tone="info">sky130_fd_sc_hd</Badge>
        <Badge tone="muted">SkyWater 130nm PDK</Badge>
      </div>

      {stats.log_tail ? (
        <div className="mt-5 rounded-xl border border-border bg-background shadow-sm">
          <button
            type="button"
            onClick={() => setLogExpanded((open) => !open)}
            className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-medium text-foreground transition hover:bg-accent"
          >
            <span>Synthesis log</span>
            <span className="text-muted-foreground">{logExpanded ? "Hide" : "Show"}</span>
          </button>
          {logExpanded ? (
            <div className="border-t border-border bg-muted/30 p-4">
              <pre className="max-h-[320px] overflow-auto rounded-lg bg-slate-950 p-4 font-mono text-sm leading-6 text-slate-200">
                {stats.log_tail}
              </pre>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function NetlistPanel({ svg }) {
  if (!svg) {
    return (
      <EmptyState
        title="No netlist visualization"
        description="The synthesized schematic will appear here once netlistsvg output is available."
      />
    );
  }

  return (
    <div className="h-full overflow-y-auto p-5">
      <div className="rounded-xl border border-border bg-muted/30 p-4">
        <div
          className="overflow-auto rounded-lg border border-border bg-white p-4 shadow-sm"
          dangerouslySetInnerHTML={{ __html: svg }}
        />
      </div>
    </div>
  );
}

function SimulationPanel({ simulation }) {
  if (!simulation) {
    return (
      <EmptyState
        title="No simulation run yet"
        description="Functional pass/fail status and the testbench transcript will appear here after simulation completes."
      />
    );
  }

  return (
    <div className="h-full overflow-y-auto p-5">
      <div
        className={cx(
          "rounded-xl border p-5 shadow-sm",
          simulation.passed ? "border-emerald-200 bg-emerald-50" : "border-red-200 bg-red-50"
        )}
      >
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm font-medium text-muted-foreground">Functional simulation</p>
            <p className="mt-1 text-2xl font-semibold tracking-tight text-foreground">
              {simulation.passed ? "All tests passed" : "Simulation failed"}
            </p>
          </div>
          <Badge tone={simulation.passed ? "success" : "destructive"}>
            {simulation.pass_count}/{simulation.total_count} tests
          </Badge>
        </div>
      </div>

      <div className="mt-5 grid gap-3 md:grid-cols-2">
        <MetricTile label="Passing tests" value={simulation.pass_count || 0} hint="Assertions satisfied" tone="emerald" />
        <MetricTile label="Total tests" value={simulation.total_count || 0} hint="Executed cases" tone="sky" />
      </div>

      <div className="mt-5 rounded-xl border border-border bg-background p-4 shadow-sm">
        <p className="text-sm font-medium text-foreground">Transcript</p>
        <pre className="mt-4 max-h-[420px] overflow-auto rounded-lg bg-slate-950 p-4 font-mono text-sm leading-6 text-slate-200 whitespace-pre-wrap">
          {simulation.output}
        </pre>
      </div>
    </div>
  );
}

function TabBar({ activeTab, onTabChange }) {
  return (
    <div className="inline-flex w-full flex-wrap gap-1 rounded-lg bg-muted p-1">
      {TABS.map((tab) => (
        <button
          key={tab.id}
          type="button"
          onClick={() => onTabChange(tab.id)}
          className={cx(
            "inline-flex min-w-[88px] items-center justify-center rounded-md px-3 py-2 text-sm font-medium transition-colors",
            activeTab === tab.id
              ? "bg-background text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

function RightPanel({ state, dispatch }) {
  const { activeTab, verilogCode, moduleName, synthStats, netlistSvg, simulation } = state;

  return (
    <section className={cx(surfaceClass, "flex h-full min-h-[600px] flex-col overflow-hidden")}>
      <div className="border-b border-border p-5">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h2 className="text-sm font-semibold tracking-tight text-foreground">Design workspace</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Inspect the generated artifacts and the downstream hardware toolchain output.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {moduleName ? <Badge tone="outline">{moduleName}</Badge> : null}
            {synthStats?.total_cells != null ? <Badge tone="info">{synthStats.total_cells} cells</Badge> : null}
            {simulation ? (
              <Badge tone={simulation.passed ? "success" : "destructive"}>
                {simulation.pass_count}/{simulation.total_count} tests
              </Badge>
            ) : null}
          </div>
        </div>
        <div className="mt-4">
          <TabBar activeTab={activeTab} onTabChange={(tab) => dispatch({ type: "set_tab", tab })} />
        </div>
      </div>

      <div className="min-h-0 flex-1 bg-card">
        {activeTab === "code" && <CodePanel code={verilogCode} moduleName={moduleName} />}
        {activeTab === "synthesis" && <SynthesisPanel stats={synthStats} />}
        {activeTab === "netlist" && <NetlistPanel svg={netlistSvg} />}
        {activeTab === "simulation" && <SimulationPanel simulation={simulation} />}
      </div>
    </section>
  );
}

export default function App() {
  const [state, dispatch] = useReducer(reducer, initialState);
  const isMock = new URLSearchParams(window.location.search).get("mock") === "true";
  const wsHost = window.location.hostname === "localhost" ? "127.0.0.1" : window.location.hostname;
  const wsProtocol = window.location.protocol === "https:" ? "wss" : "ws";
  const wsUrl = `${wsProtocol}://${wsHost}:8000/ws/design`;
  const { send } = useWebSocket(wsUrl, dispatch);

  const handleSubmit = (prompt) => {
    dispatch({ type: "reset" });

    if (isMock) {
      MOCK_SEQUENCE.forEach(({ delay, msg }) => {
        setTimeout(() => dispatch(msg), delay);
      });
      return;
    }

    dispatch({ type: "status", message: "Connecting to backend..." });
    send({ prompt });
  };

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-72 bg-[radial-gradient(circle_at_top,rgba(15,23,42,0.07),transparent_60%)]" />
      <main className="relative mx-auto flex min-h-screen max-w-[1560px] flex-col gap-5 px-4 py-5 sm:px-6 lg:px-8">
        <ControlPanel
          state={state}
          onSubmit={handleSubmit}
          onReset={() => dispatch({ type: "reset" })}
          loading={state.loading}
          isMock={isMock}
        />

        <div className="grid flex-1 gap-5 xl:grid-cols-[360px_minmax(0,1fr)]">
          <div className="grid min-h-0 gap-5 xl:grid-rows-[minmax(0,1fr)_minmax(0,1fr)]">
            <AgentLog messages={state.messages} loading={state.loading} />
            <HardwareBOM bom={state.bom} />
          </div>
          <RightPanel state={state} dispatch={dispatch} />
        </div>
      </main>

      {state.error ? (
        <div className="fixed bottom-4 right-4 max-w-sm rounded-xl border border-red-200 bg-white p-4 shadow-xl">
          <div className="flex items-start gap-3">
            <span className="mt-0.5 h-2.5 w-2.5 rounded-full bg-red-500" />
            <div>
              <p className="text-sm font-semibold text-red-700">Pipeline error</p>
              <p className="mt-1 text-sm leading-6 text-red-600">{state.error}</p>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
