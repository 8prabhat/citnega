"""safe_eval — restricted Python boolean expression evaluator for plan conditions."""

from __future__ import annotations

import ast


_ALLOWED_NODE_TYPES = frozenset({
    ast.Expression,
    ast.BoolOp, ast.BinOp, ast.UnaryOp, ast.Compare,
    ast.Constant, ast.Name, ast.Attribute,
    ast.Subscript, ast.Index,
    ast.And, ast.Or, ast.Not,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.In, ast.NotIn, ast.Is, ast.IsNot,
    ast.Load,
})


def safe_eval(expression: str, context: dict) -> bool:
    """
    Evaluate a boolean expression against a context dict.

    Only a safe subset of AST nodes is allowed — no function calls,
    imports, assignments, or comprehensions. Returns False on any
    evaluation error rather than raising.

    Raises ValueError if the expression is syntactically invalid or
    contains disallowed node types.
    """
    if not expression or not expression.strip():
        return True

    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Invalid condition expression: {exc}") from exc

    for node in ast.walk(tree):
        if type(node) not in _ALLOWED_NODE_TYPES:
            raise ValueError(
                f"Disallowed expression node type: {type(node).__name__!r} "
                f"in expression: {expression!r}"
            )

    try:
        return bool(
            eval(  # noqa: S307
                compile(tree, "<condition>", "eval"),
                {"__builtins__": {}},
                context,
            )
        )
    except Exception:
        return False
