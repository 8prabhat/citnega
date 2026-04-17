"""calculate — safe arithmetic/math expression evaluator.

Uses Python's ast module to evaluate expressions without allowing arbitrary
code execution.  Supports: +, -, *, /, //, %, **, sqrt, abs, round, log,
sin, cos, tan, pi, e, and comparison operators.
"""

from __future__ import annotations

import ast
import math
import operator
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class CalculateInput(BaseModel):
    expression: str = Field(
        description=(
            "A mathematical expression to evaluate, e.g. '2 ** 10', '(100 * 1.18)', "
            "'sqrt(144)', 'sin(pi / 2)'. Use ** for exponentiation."
        )
    )


# Whitelist of safe operators and functions
_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

_SAFE_NAMES: dict[str, object] = {
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
    "inf": math.inf,
    "sqrt": math.sqrt,
    "abs": abs,
    "round": round,
    "floor": math.floor,
    "ceil": math.ceil,
    "log": math.log,
    "log2": math.log2,
    "log10": math.log10,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "atan2": math.atan2,
    "degrees": math.degrees,
    "radians": math.radians,
    "exp": math.exp,
    "factorial": math.factorial,
    "gcd": math.gcd,
    "hypot": math.hypot,
    "pow": math.pow,
    "min": min,
    "max": max,
    "sum": sum,
}


def _safe_eval(node: ast.AST) -> float | int:
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Unsupported constant type: {type(node.value)}")
    if isinstance(node, ast.Name):
        if node.id in _SAFE_NAMES:
            return _safe_names_val(node.id)  # type: ignore[return-value]
        raise ValueError(f"Unknown name: {node.id!r}")
    if isinstance(node, ast.BinOp):
        op_fn = _OPERATORS.get(type(node.op))
        if op_fn is None:
            raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
        return op_fn(_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp):
        op_fn = _OPERATORS.get(type(node.op))
        if op_fn is None:
            raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")
        return op_fn(_safe_eval(node.operand))  # type: ignore[call-arg]
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("Only simple function calls are allowed")
        fn = _SAFE_NAMES.get(node.func.id)
        if fn is None:
            raise ValueError(f"Unknown function: {node.func.id!r}")
        args = [_safe_eval(a) for a in node.args]
        return fn(*args)  # type: ignore[operator]
    raise ValueError(f"Unsupported expression node: {type(node).__name__}")


def _safe_names_val(name: str) -> object:
    return _SAFE_NAMES[name]


class CalculateTool(BaseCallable):
    """Safe math expression evaluator — no code execution, no imports."""

    name = "calculate"
    description = (
        "Evaluate a mathematical expression safely. "
        "Supports arithmetic, trigonometry, logarithms, sqrt, and constants (pi, e). "
        "Use this for any calculation rather than guessing."
    )
    callable_type = CallableType.TOOL
    input_schema = CalculateInput
    output_schema = ToolOutput
    policy = tool_policy(timeout_seconds=5.0, requires_approval=False, network_allowed=False)

    async def _execute(self, input: CalculateInput, context: CallContext) -> ToolOutput:
        expr = input.expression.strip()
        if not expr:
            return ToolOutput(result="Empty expression.")

        try:
            tree = ast.parse(expr, mode="eval")
            result = _safe_eval(tree)
        except (ValueError, ZeroDivisionError, OverflowError) as exc:
            return ToolOutput(result=f"Error: {exc}")
        except SyntaxError as exc:
            return ToolOutput(result=f"Syntax error in expression: {exc}")
        except Exception as exc:
            return ToolOutput(result=f"Calculation failed: {exc}")

        # Format nicely
        if isinstance(result, float) and result.is_integer() and abs(result) < 1e15:
            formatted = str(int(result))
        elif isinstance(result, float):
            formatted = f"{result:.10g}"
        else:
            formatted = str(result)

        return ToolOutput(result=f"{expr} = {formatted}")
