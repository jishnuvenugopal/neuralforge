"""Yosys `stat -liberty` parsing across the two output layouts. Pure Python.

Yosys 0.4x prints `count area cell`; older releases such as 0.33 (Ubuntu 24.04's
apt package, used in CI) print `cell count`. Both must give the same flip-flop
count, or the dashboard reports 0 flip-flops on older Yosys.
"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

import eda_tools  # noqa: E402

# Excerpt of real Yosys 0.63 output for the registered XOR reference design.
STAT_0_4X = """
=== xor_nn ===

        +----------Local Count, excluding submodules.
        |        +-Local Area, excluding submodules.
        |        |
    11338        - wires
       30        - public wires
     4065 3.08E+04 cells
        5   43.792   sky130_fd_sc_hd__a2111oi_0
      174  653.126   sky130_fd_sc_hd__clkinv_1
       34  850.816   sky130_fd_sc_hd__dfrtp_1
        2   40.038   sky130_fd_sc_hd__dfxtp_1
      317 3.17E+03   sky130_fd_sc_hd__maj3_1

   Chip area for module '\\xor_nn': 30848.336000
"""

# The same cells in the older `Number of` layout.
STAT_0_33 = """
=== xor_nn ===

   Number of wires:              11338
   Number of public wires:          30
   Number of cells:               4065
     sky130_fd_sc_hd__a2111oi_0      5
     sky130_fd_sc_hd__clkinv_1     174
     sky130_fd_sc_hd__dfrtp_1       34
     sky130_fd_sc_hd__dfxtp_1        2
     sky130_fd_sc_hd__maj3_1       317

   Chip area for module '\\xor_nn': 30848.336000
"""


class StatParserTest(unittest.TestCase):
    EXPECTED = {"total_cells": 4065, "flip_flops": 36, "area_um2": 30848.336, "wires": 11338}

    def test_yosys_0_4x_layout(self):
        self.assertEqual(eda_tools._parse_stat(STAT_0_4X), self.EXPECTED)

    def test_older_number_of_layout(self):
        self.assertEqual(eda_tools._parse_stat(STAT_0_33), self.EXPECTED)


if __name__ == "__main__":
    unittest.main()
