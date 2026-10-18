"""Bit-exact reference and the weight hand-off. Pure Python; no EDA tools needed."""

import ast
import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import golden  # noqa: E402


def param_names(text: str) -> list[str]:
    return re.findall(r"localparam\s+signed\s+\[\d+:0\]\s+(\w+)\s*=", text)


class XorReferenceTest(unittest.TestCase):
    def setUp(self):
        self.net = golden.load_network("xor")

    def test_logits_match_the_audit(self):
        outputs = golden.reference_outputs(self.net)
        self.assertEqual([z[0] for z, _ in outputs], [-15604, 15318, 16870, -15327])
        self.assertEqual([cls for _, cls in outputs], [0, 1, 1, 0])

    def test_output_bias_is_rescaled_to_the_accumulator(self):
        # b2 = 127 / 4140.37 rescaled by s_w1 * s_w2 = 42.41 * 30.59 gives 40, not the raw 127.
        self.assertEqual(self.net.layers[1][1], [40])

    def test_hidden_bias_is_rescaled(self):
        with open(os.path.join(golden.CACHE_DIR, "xor_weights.json")) as f:
            w = json.load(f)
        b1 = w["0.bias"]["values"]
        expected = [round(b / w["0.bias"]["scale"] * w["0.weight"]["scale"]) for b in b1]
        self.assertEqual(self.net.layers[0][1], expected)


class IrisReferenceTest(unittest.TestCase):
    def setUp(self):
        self.net = golden.load_network("iris")

    def test_all_150_samples_with_int32_logits(self):
        outputs = golden.reference_outputs(self.net)
        self.assertEqual(len(outputs), 150)
        for logits, cls in outputs:
            self.assertEqual(len(logits), 3)
            self.assertIn(cls, (0, 1, 2))
            for z in logits:
                self.assertTrue(golden.INT32_MIN <= z <= golden.INT32_MAX)

    def test_integer_network_still_classifies_iris(self):
        outputs = golden.reference_outputs(self.net)
        correct = sum(cls == label for (_, cls), label in zip(outputs, self.net.labels))
        self.assertGreaterEqual(correct / 150, 0.95)

    def test_argmax_ties_go_to_the_lowest_index(self):
        net = golden.Network("tie", [([[1], [1], [1]], [0, 0, 0])], 1.0, [[5]])
        self.assertEqual(golden.forward(net, [5]), ([5, 5, 5], 0))

    def test_overflow_is_an_error_not_a_wrap(self):
        net = golden.Network("big", [([[127]], [2 ** 31 - 1])], 1.0, [[1]])
        with self.assertRaises(OverflowError):
            golden.forward(net, [1])


class WeightHandOffTest(unittest.TestCase):
    def test_network_params_have_unique_names(self):
        for keyword, expected in (("xor", 16 + 8 + 8 + 1), ("iris", 32 + 8 + 24 + 3)):
            names = param_names(golden.network_params(golden.load_network(keyword)))
            self.assertEqual(len(names), expected, keyword)
            self.assertEqual(len(set(names)), len(names), keyword)

    def test_biases_are_32_bit(self):
        text = golden.network_params(golden.load_network("iris"))
        self.assertIn("localparam signed [31:0] B2_2 = -32'sd213653;", text)
        self.assertNotRegex(text, r"\[7:0\]\s+B\d")

    def test_attention_params_have_unique_names(self):
        with open(os.path.join(golden.CACHE_DIR, "attention_weights.json")) as f:
            weights = json.load(f)
        names = param_names(golden.tensor_params(weights))
        self.assertEqual(len(names), 3 * 64)
        self.assertEqual(len(set(names)), len(names))

    def test_attention_has_no_reference(self):
        self.assertIsNone(golden.load_network("attention"))
        self.assertIsNone(golden.load_network(None))

    def test_main_does_not_import_torch(self):
        with open(os.path.join(ROOT, "backend", "main.py")) as f:
            tree = ast.parse(f.read())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module)
        self.assertNotIn("model_trainer", imported)
        self.assertNotIn("torch", imported)


if __name__ == "__main__":
    unittest.main()
