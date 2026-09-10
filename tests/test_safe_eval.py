import math

import pytest

from harness.tools import ToolError, safe_eval


def test_basic_arithmetic():
    assert safe_eval("2 + 3") == 5
    assert safe_eval("10 / 4") == 2.5
    assert safe_eval("(1847.33 + 200.10) * 2") == pytest.approx(4094.86)
    assert safe_eval("-5 + 8") == 3


def test_float_precision():
    assert safe_eval("927.61 + 100.00") == pytest.approx(1027.61)


@pytest.mark.parametrize("expr", [
    "__import__('os')",            # no calls
    "os.system('ls')",            # no attribute access / names
    "1; import os",               # not a single expression
    "2 ** 10",                    # power not allowed
    "1 if True else 2",           # no conditionals
    "[1, 2, 3]",                  # no lists
    "abs(-4)",                    # no function calls
    "True + 1",                   # bools rejected
])
def test_rejects_dangerous_input(expr):
    with pytest.raises(ToolError):
        safe_eval(expr)
