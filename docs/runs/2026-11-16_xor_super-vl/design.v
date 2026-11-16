`timescale 1ns/1ps
`default_nettype none

module mlp_xor_2_8_1 (
    input  wire clk,
    input  wire rst,
    input  wire start,
    input  wire [15:0] x_flat,
    output wire done,
    output wire [31:0] logits_flat,
    output wire [0:0] cls
);

    // Extract INT8 inputs
    wire signed [7:0] x0 = $signed(x_flat[7:0]);
    wire signed [7:0] x1 = $signed(x_flat[15:8]);

    // ------------------------------------------------------------
    // Layer 1 weights (8x2) - INT8
    // ------------------------------------------------------------
    localparam signed [7:0] W1_0_0 = -8'sd126;
    localparam signed [7:0] W1_0_1 =  8'sd126;
    localparam signed [7:0] W1_1_0 = -8'sd86;
    localparam signed [7:0] W1_1_1 = -8'sd86;
    localparam signed [7:0] W1_2_0 = -8'sd12;
    localparam signed [7:0] W1_2_1 =  8'sd8;
    localparam signed [7:0] W1_3_0 =  8'sd127;
    localparam signed [7:0] W1_3_1 =  8'sd89;
    localparam signed [7:0] W1_4_0 =  8'sd113;
    localparam signed [7:0] W1_4_1 = -8'sd113;
    localparam signed [7:0] W1_5_0 = -8'sd84;
    localparam signed [7:0] W1_5_1 = -8'sd84;
    localparam signed [7:0] W1_6_0 = -8'sd29;
    localparam signed [7:0] W1_6_1 = -8'sd20;
    localparam signed [7:0] W1_7_0 =  8'sd101;
    localparam signed [7:0] W1_7_1 = -8'sd101;

    // ------------------------------------------------------------
    // Layer 1 biases (8) - INT32 (already rescaled)
    // ------------------------------------------------------------
    localparam signed [31:0] B1_0 =  32'sd0;
    localparam signed [31:0] B1_1 =  32'sd86;
    localparam signed [31:0] B1_2 = -32'sd20;
    localparam signed [31:0] B1_3 = -32'sd89;
    localparam signed [31:0] B1_4 =  32'sd0;
    localparam signed [31:0] B1_5 =  32'sd85;
    localparam signed [31:0] B1_6 = -32'sd6;
    localparam signed [31:0] B1_7 =  32'sd0;

    // ------------------------------------------------------------
    // Layer 2 weights (1x8) - INT8
    // ------------------------------------------------------------
    localparam signed [7:0] W2_0_0 =  8'sd122;
    localparam signed [7:0] W2_0_1 = -8'sd89;
    localparam signed [7:0] W2_0_2 =  8'sd10;
    localparam signed [7:0] W2_0_3 = -8'sd121;
    localparam signed [7:0] W2_0_4 =  8'sd127;
    localparam signed [7:0] W2_0_5 = -8'sd94;
    localparam signed [7:0] W2_0_6 = -8'sd4;
    localparam signed [7:0] W2_0_7 =  8'sd71;

    // ------------------------------------------------------------
    // Layer 2 bias (1) - INT32
    // ------------------------------------------------------------
    localparam signed [31:0] B2_0 = 32'sd40;

    // ------------------------------------------------------------
    // Hidden layer pre-activations: z1_k = sum_i W1_k_i * x_i + B1_k
    // Each product: INT8 * INT8 -> 16 bits signed
    // ------------------------------------------------------------
    wire signed [15:0] prod_0_0 = $signed(x0) * W1_0_0;
    wire signed [15:0] prod_0_1 = $signed(x1) * W1_0_1;
    wire signed [15:0] prod_1_0 = $signed(x0) * W1_1_0;
    wire signed [15:0] prod_1_1 = $signed(x1) * W1_1_1;
    wire signed [15:0] prod_2_0 = $signed(x0) * W1_2_0;
    wire signed [15:0] prod_2_1 = $signed(x1) * W1_2_1;
    wire signed [15:0] prod_3_0 = $signed(x0) * W1_3_0;
    wire signed [15:0] prod_3_1 = $signed(x1) * W1_3_1;
    wire signed [15:0] prod_4_0 = $signed(x0) * W1_4_0;
    wire signed [15:0] prod_4_1 = $signed(x1) * W1_4_1;
    wire signed [15:0] prod_5_0 = $signed(x0) * W1_5_0;
    wire signed [15:0] prod_5_1 = $signed(x1) * W1_5_1;
    wire signed [15:0] prod_6_0 = $signed(x0) * W1_6_0;
    wire signed [15:0] prod_6_1 = $signed(x1) * W1_6_1;
    wire signed [15:0] prod_7_0 = $signed(x0) * W1_7_0;
    wire signed [15:0] prod_7_1 = $signed(x1) * W1_7_1;

    wire signed [31:0] z1_0 = B1_0 + prod_0_0 + prod_0_1;
    wire signed [31:0] z1_1 = B1_1 + prod_1_0 + prod_1_1;
    wire signed [31:0] z1_2 = B1_2 + prod_2_0 + prod_2_1;
    wire signed [31:0] z1_3 = B1_3 + prod_3_0 + prod_3_1;
    wire signed [31:0] z1_4 = B1_4 + prod_4_0 + prod_4_1;
    wire signed [31:0] z1_5 = B1_5 + prod_5_0 + prod_5_1;
    wire signed [31:0] z1_6 = B1_6 + prod_6_0 + prod_6_1;
    wire signed [31:0] z1_7 = B1_7 + prod_7_0 + prod_7_1;

    // ------------------------------------------------------------
    // ReLU: h_k = max(0, z1_k)
    // ------------------------------------------------------------
    wire signed [31:0] h0 = (z1_0 > 32'sd0) ? z1_0 : 32'sd0;
    wire signed [31:0] h1 = (z1_1 > 32'sd0) ? z1_1 : 32'sd0;
    wire signed [31:0] h2 = (z1_2 > 32'sd0) ? z1_2 : 32'sd0;
    wire signed [31:0] h3 = (z1_3 > 32'sd0) ? z1_3 : 32'sd0;
    wire signed [31:0] h4 = (z1_4 > 32'sd0) ? z1_4 : 32'sd0;
    wire signed [31:0] h5 = (z1_5 > 32'sd0) ? z1_5 : 32'sd0;
    wire signed [31:0] h6 = (z1_6 > 32'sd0) ? z1_6 : 32'sd0;
    wire signed [31:0] h7 = (z1_7 > 32'sd0) ? z1_7 : 32'sd0;

    // ------------------------------------------------------------
    // Output layer: z2_0 = sum_k W2_0_k * h_k + B2_0
    // h_k is INT32, W2 is INT8 -> product fits in 32 bits
    // ------------------------------------------------------------
    wire signed [31:0] prod_2_0_0 = $signed(h0) * W2_0_0;
    wire signed [31:0] prod_2_0_1 = $signed(h1) * W2_0_1;
    wire signed [31:0] prod_2_0_2 = $signed(h2) * W2_0_2;
    wire signed [31:0] prod_2_0_3 = $signed(h3) * W2_0_3;
    wire signed [31:0] prod_2_0_4 = $signed(h4) * W2_0_4;
    wire signed [31:0] prod_2_0_5 = $signed(h5) * W2_0_5;
    wire signed [31:0] prod_2_0_6 = $signed(h6) * W2_0_6;
    wire signed [31:0] prod_2_0_7 = $signed(h7) * W2_0_7;

    wire signed [31:0] z2_0 = B2_0 + prod_2_0_0 + prod_2_0_1 + prod_2_0_2 +
                              prod_2_0_3 + prod_2_0_4 + prod_2_0_5 +
                              prod_2_0_6 + prod_2_0_7;

    // ------------------------------------------------------------
    // Outputs
    // ------------------------------------------------------------
    assign logits_flat = z2_0;
    assign cls         = (z2_0 > 32'sd0) ? 1'b1 : 1'b0;
    assign done        = start;

endmodule
`default_nettype wire