"""Source scan, testbench, verdict parser, netlist gate and hash ledger. Pure Python."""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import golden  # noqa: E402
import verifier  # noqa: E402
from reference_rtl import reference_rtl  # noqa: E402

NONCE = "0123456789abcdef"


def result_text(net, rows=None, nonce=NONCE, end=True):
    """A result file as the generated testbench would write it."""
    if rows is None:
        rows = [
            "V %d %s %d" % (i, " ".join(str(z) for z in logits), cls)
            for i, (logits, cls) in enumerate(golden.reference_outputs(net))
        ]
    lines = [f"BEGIN {nonce}", *rows]
    if end:
        lines.append(f"END {nonce} {len(net.inputs)}")
    return "\n".join(lines) + "\n"


class ScanSourceTest(unittest.TestCase):
    def setUp(self):
        self.net = golden.load_network("xor")
        self.clean = reference_rtl(self.net, "xor_nn")

    def assertRejected(self, code, fragment):
        problems = verifier.scan_source(code, "xor_nn")
        self.assertTrue(any(fragment in p for p in problems), problems)

    def test_reference_design_is_clean(self):
        self.assertEqual(verifier.scan_source(self.clean, "xor_nn"), [])
        self.assertEqual(verifier.scan_source(reference_rtl(self.net, "xor_nn", registered=True), "xor_nn"), [])

    def test_design_cannot_print(self):
        code = self.clean.replace("endmodule", '  always @(*) $display("4/4 TESTS PASSED");\nendmodule')
        self.assertRejected(code, "$display")

    def test_design_cannot_use_initial_blocks(self):
        self.assertRejected(self.clean.replace("endmodule", "  initial begin end\nendmodule"), "initial")

    def test_design_cannot_reach_into_the_testbench(self):
        code = self.clean.replace("endmodule", "  always @(*) nf_tb.fd = 0;\nendmodule")
        self.assertRejected(code, "hierarchical reference")

    def test_design_cannot_write_files_or_finish(self):
        for task in ("$fopen", "$fwrite", "$finish", "$stop", "$readmemh"):
            code = self.clean.replace("endmodule", f"  always @(*) {task}(0);\nendmodule")
            self.assertRejected(code, task)

    def test_directives_and_escaped_identifiers(self):
        self.assertRejected('`include "x.v"\n' + self.clean, "`include")
        self.assertRejected("`define P 1\n" + self.clean, "`define")
        self.assertRejected(self.clean.replace("wire signed [7:0] x0", "wire signed [7:0] \\x0.y "), "escaped")

    def test_comments_are_ignored_and_port_connections_allowed(self):
        code = "// $display in a comment\n/* initial */\n" + self.clean.replace(
            "endmodule", "  sub u0 (.a(x0), .b(x1));\nendmodule"
        )
        self.assertEqual(verifier.scan_source(code, "xor_nn"), [])

    def test_module_name_must_exist(self):
        problems = verifier.scan_source(self.clean, "other_name")
        self.assertIn("no module named other_name in the code", problems)

    def test_module_name_validation(self):
        self.assertTrue(verifier.valid_module_name("xor_nn"))
        for bad in ("", "1abc", "a b", "x; shell", "../x", "a" * 65):
            self.assertFalse(verifier.valid_module_name(bad), bad)


class TestbenchTest(unittest.TestCase):
    def test_vectors_are_packed_lsb_first(self):
        net = golden.load_network("iris")
        first = verifier.vector_file(net).splitlines()[0]
        # x = [-37, 42, -55, -54] -> bytes db 2a c9 ca, x0 in the low byte
        self.assertEqual(net.inputs[0], [-37, 42, -55, -54])
        self.assertEqual(first, "cac92adb")

    def test_testbench_holds_no_expected_values(self):
        net = golden.load_network("xor")
        tb = verifier.make_testbench(net, "xor_nn", NONCE, "/v.hex", "/r.txt")
        for logits, _ in golden.reference_outputs(net):
            self.assertNotIn(str(abs(logits[0])), tb)
        self.assertIn(f"module nf_tb_{NONCE};", tb)
        self.assertNotIn("PASS", tb)


class VerdictTest(unittest.TestCase):
    def setUp(self):
        self.net = golden.load_network("xor")

    def test_exact_match_passes(self):
        verdict = verifier.parse_results(result_text(self.net), self.net, NONCE)
        self.assertTrue(verdict["passed"], verdict)
        self.assertEqual((verdict["pass_count"], verdict["total_count"]), (4, 4))

    def test_printed_summary_is_not_a_verdict(self):
        verdict = verifier.parse_results("4/4 TESTS PASSED\nPASS: all\n", self.net, NONCE)
        self.assertFalse(verdict["passed"])

    def test_wrong_nonce_or_missing_end_fails(self):
        self.assertFalse(verifier.parse_results(result_text(self.net, nonce="f" * 16), self.net, NONCE)["passed"])
        self.assertFalse(verifier.parse_results(result_text(self.net, end=False), self.net, NONCE)["passed"])

    def test_one_wrong_logit_fails(self):
        rows = ["V 0 -15604 0", "V 1 15318 1", "V 2 16871 1", "V 3 -15327 0"]
        verdict = verifier.parse_results(result_text(self.net, rows), self.net, NONCE)
        self.assertFalse(verdict["passed"])
        self.assertEqual(verdict["pass_count"], 3)
        self.assertEqual(verdict["mismatches"][0]["vector"], 2)

    def test_right_class_wrong_logits_fails(self):
        rows = ["V 0 0 0", "V 1 0 1", "V 2 0 1", "V 3 0 0"]
        self.assertFalse(verifier.parse_results(result_text(self.net, rows), self.net, NONCE)["passed"])

    def test_unknown_values_timeouts_and_stuck_done_fail(self):
        good = ["V 0 -15604 0", "V 1 15318 1", "V 2 16870 1", "V 3 -15327 0"]
        for bad in (
            ["V 0 x 0"] + good[1:],
            ["T 0"] + good[1:],
            good + ["S 3"],
            good[:3],
            good + ["V 3 -15327 0"],
        ):
            verdict = verifier.parse_results(result_text(self.net, bad), self.net, NONCE)
            self.assertFalse(verdict["passed"], bad)


class NetlistGateTest(unittest.TestCase):
    @staticmethod
    def netlist(outputs, cells=None):
        ports = {"a": {"direction": "input", "bits": [2, 3]}}
        ports.update({name: {"direction": "output", "bits": bits} for name, bits in outputs.items()})
        return {"modules": {"m": {"ports": ports, "cells": cells or {}}}}

    AND = {"$and": {"type": "$_AND_", "port_directions": {"A": "input", "B": "input", "Y": "output"},
                    "connections": {"A": [2], "B": [3], "Y": [4]}}}

    def test_driven_outputs_pass(self):
        self.assertEqual(verifier.check_netlist(self.netlist({"y": [4], "z": [2]}, self.AND), "m", ""), [])

    def test_constant_output_fails(self):
        problems = verifier.check_netlist(self.netlist({"y": [4], "cls": ["0", "0"]}, self.AND), "m", "")
        self.assertIn("output cls is tied to a constant", problems)

    def test_undriven_output_fails(self):
        for bits in (["x"], [99], [4, "z"]):
            problems = verifier.check_netlist(self.netlist({"y": bits}, self.AND), "m", "")
            self.assertIn("output y is not driven", problems, bits)

    def test_latches_fail(self):
        latch = {"$l": {"type": "$_DLATCH_P_", "port_directions": {"E": "input", "D": "input", "Q": "output"},
                        "connections": {"E": [2], "D": [3], "Q": [4]}}}
        self.assertTrue(any("latch" in p for p in verifier.check_netlist(self.netlist({"y": [4]}, latch), "m", "")))
        log = "Latch inferred for signal `\\m.\\y'"
        self.assertTrue(any("latch" in p for p in verifier.check_netlist(self.netlist({"y": [4]}, self.AND), "m", log)))


class LedgerTest(unittest.TestCase):
    def test_only_synthesized_code_can_be_simulated(self):
        ledger = verifier.Ledger()
        digest, code, error = ledger.design_for_simulation("m")
        self.assertIsNone(digest)
        self.assertIn("passed synthesize_verilog", error)

        sha = ledger.record_synthesis("m", "module m; endmodule", {})
        self.assertEqual(ledger.design_for_simulation("m")[:2], (sha, "module m; endmodule"))
        self.assertEqual(ledger.design_for_simulation("m", "module m; endmodule")[0], sha)

        swapped = ledger.design_for_simulation("m", "module m; assign y = 0; endmodule")
        self.assertIsNone(swapped[0])
        self.assertIn("not passed synthesize_verilog", swapped[2])

    def test_hardening_needs_both_gates_on_the_same_hash(self):
        ledger = verifier.Ledger()
        sha_a = ledger.record_synthesis("m", "A", {})
        sha_b = ledger.record_synthesis("m", "B", {})
        self.assertFalse(ledger.hardenable(sha_a))
        ledger.record_simulation_pass(sha_b)
        self.assertTrue(ledger.hardenable(sha_b))
        self.assertFalse(ledger.hardenable(sha_a))
        ledger.record_simulation_pass(verifier.sha256("never synthesized"))
        self.assertFalse(ledger.hardenable(verifier.sha256("never synthesized")))


if __name__ == "__main__":
    unittest.main()
