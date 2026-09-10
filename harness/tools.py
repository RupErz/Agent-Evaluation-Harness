"""The three tools the agent under test may call, plus a safe arithmetic evaluator.

Tools are deliberately dumb (data access + arithmetic) so the reasoning stays
with the model and is therefore observable in the trace.

`calculate` exists so the harness can assert on a *behavior* (did the agent use
the tool for arithmetic vs. do it in its head), not just on the final number.
"""
from __future__ import annotations

import ast
import operator
from typing import Any, Optional

from .config import MAX_TOOL_ROWS
from .fixture.db import FixtureDB


class ToolError(Exception):
    """A structured, recoverable tool error (returned to the model as is_error)."""

    def __init__(self, message: str, payload: Optional[dict] = None):
        super().__init__(message)
        self.payload = {"error": message, **(payload or {})}


# --- safe arithmetic evaluator --------------------------------------------
_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def safe_eval(expression: str) -> float:
    """Evaluate a restricted arithmetic expression via an AST walk with a node
    allowlist. NEVER uses eval(). Allowed: numbers, + - * /, parens, unary +/-.
    """
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as e:
        raise ToolError(f"Could not parse expression: {e}")

    def _eval(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                raise ToolError("Only numeric literals are allowed.")
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
            return _BIN_OPS[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
            return _UNARY_OPS[type(node.op)](_eval(node.operand))
        raise ToolError(
            f"Disallowed expression element: {type(node).__name__}. "
            "Only numbers and + - * / ( ) are permitted."
        )

    return round(_eval(tree), 6)


# --- tool schemas (Anthropic tool-use definitions) -------------------------
TOOL_SCHEMAS: list[dict] = [
    {
        "name": "list_transactions",
        "description": (
            "Return transactions from the finance database within an inclusive "
            "date range (YYYY-MM-DD). Optionally filter by category. Results are "
            "capped; the response reports how many rows were omitted."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "inclusive, YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "inclusive, YYYY-MM-DD"},
                "category": {
                    "type": ["string", "null"],
                    "description": "optional category filter",
                },
            },
            "required": ["start_date", "end_date"],
        },
    },
    {
        "name": "get_accounts",
        "description": (
            "Return all accounts with id, name, type, status, and current "
            "balance. A closed account may have a null (unavailable) balance."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "calculate",
        "description": (
            "Evaluate a restricted arithmetic expression (numbers and + - * / "
            "and parentheses only). Use this for all arithmetic rather than "
            "computing in your head."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"expression": {"type": "string"}},
            "required": ["expression"],
        },
    },
]

TOOL_NAMES = [t["name"] for t in TOOL_SCHEMAS]


class ToolBox:
    """Dispatches tool calls against a FixtureDB. `stale` supports the mutation
    test that returns wrong data from list_transactions.
    """

    def __init__(self, db: FixtureDB, max_rows: int = MAX_TOOL_ROWS, stale: bool = False):
        self.db = db
        self.max_rows = max_rows
        self.stale = stale

    def list_transactions(self, start_date: str, end_date: str,
                          category: Optional[str] = None) -> dict:
        if category is not None:
            valid = self.db.categories()
            if category not in valid:
                raise ToolError(
                    f"Unknown category '{category}'.",
                    {"valid_categories": valid},
                )
        rows = self.db.list_transactions(start_date, end_date, category)
        if self.stale:
            # Mutation: silently corrupt every amount.
            rows = [{**r, "amount": round(r["amount"] * 1.5 + 3.21, 2)} for r in rows]
        total = len(rows)
        shown = rows[: self.max_rows]
        return {
            "transactions": shown,
            "returned": len(shown),
            "total_matching": total,
            "omitted": max(0, total - len(shown)),
        }

    def get_accounts(self) -> dict:
        return {"accounts": self.db.accounts()}

    def calculate(self, expression: str) -> dict:
        return {"result": safe_eval(expression)}

    def dispatch(self, name: str, args: dict) -> Any:
        if name == "list_transactions":
            return self.list_transactions(
                args.get("start_date"), args.get("end_date"), args.get("category")
            )
        if name == "get_accounts":
            return self.get_accounts()
        if name == "calculate":
            return self.calculate(args.get("expression", ""))
        raise ToolError(f"Unknown tool '{name}'.")
