"""
CodeValidator — AST-based pre-write validation for generated callables.

Checks:
  1. Source parses without SyntaxError.
  2. A ClassDef named ``class_name`` exists in the module.
  3. The class has the required class-level attribute assignments:
       name, description, callable_type, input_schema, output_schema, policy
  4. The class has an ``_execute`` method.

Validation is intentionally lenient about *values* — it only checks
that the attributes are *present* as class-level names.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

_REQUIRED_ATTRS = frozenset(
    {
        "name",
        "description",
        "callable_type",
        "input_schema",
        "output_schema",
        "policy",
    }
)


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.ok


class CodeValidator:
    """
    Validates generated source code before it is written to disk.

    Usage::

        result = CodeValidator().validate(source, "MyTool", "tool")
        if not result:
            for err in result.errors:
                print(err)
    """

    def validate(
        self,
        source: str,
        class_name: str,
        kind: str,
    ) -> ValidationResult:
        """
        Validate ``source`` code for a callable of the given ``kind``.

        Args:
            source:     Python source code string.
            class_name: Expected class name (PascalCase).
            kind:       "tool" | "agent" | "workflow" (informational only).

        Returns:
            ValidationResult with ok=True and no errors if valid.
        """
        errors: list[str] = []

        # 1. Syntax check
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            return ValidationResult(ok=False, errors=[f"SyntaxError: {exc}"])

        # 2. Find the target class
        target_class: ast.ClassDef | None = None
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                target_class = node
                break

        if target_class is None:
            return ValidationResult(
                ok=False,
                errors=[f"Class '{class_name}' not found in generated source."],
            )

        # 3. Check required class-level attributes
        class_level_names: set[str] = set()
        for stmt in target_class.body:
            # Simple assignment: name = "..."
            if isinstance(stmt, ast.Assign):
                for t in stmt.targets:
                    if isinstance(t, ast.Name):
                        class_level_names.add(t.id)
            # Annotated assignment: name: str = "..."
            elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                class_level_names.add(stmt.target.id)

        missing = _REQUIRED_ATTRS - class_level_names
        if missing:
            errors.append(f"Class '{class_name}' is missing required attributes: {sorted(missing)}")

        # 4. Check _execute method exists
        has_execute = any(
            isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and stmt.name == "_execute"
            for stmt in target_class.body
        )
        if not has_execute:
            errors.append(f"Class '{class_name}' is missing an '_execute' method.")

        return ValidationResult(ok=not errors, errors=errors)
