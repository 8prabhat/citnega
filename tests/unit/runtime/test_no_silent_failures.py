"""AST-walk enforcement: zero 'except Exception: pass' in core runtime and bootstrap (C2)."""

from __future__ import annotations

import ast
from pathlib import Path


def _find_bare_suppressed_exceptions(root: Path) -> list[str]:
    """
    Walk Python files under *root* and return human-readable locations for any
    ``except Exception: pass`` (or ``except Exception as ...: pass``) patterns.
    These represent silent failures that swallow real errors with no logging.
    """
    violations: list[str] = []
    for py_file in root.rglob("*.py"):
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            # Must catch Exception (or broad base)
            handler_type = node.type
            if handler_type is None:
                continue
            type_name = ""
            if isinstance(handler_type, ast.Name):
                type_name = handler_type.id
            elif isinstance(handler_type, ast.Attribute):
                type_name = handler_type.attr
            if type_name not in ("Exception", "BaseException"):
                continue
            # Body must be a single `pass`
            if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                rel = py_file.relative_to(root)
                violations.append(f"{rel}:{node.lineno}: bare 'except Exception: pass'")
    return violations


_PACKAGES_ROOT = Path(__file__).parent.parent.parent.parent / "packages"


def test_no_bare_pass_in_runtime() -> None:
    violations = _find_bare_suppressed_exceptions(_PACKAGES_ROOT / "runtime")
    assert violations == [], (
        "Found bare 'except Exception: pass' in packages/runtime — "
        "replace with structured logging:\n" + "\n".join(violations)
    )


def test_no_bare_pass_in_bootstrap() -> None:
    violations = _find_bare_suppressed_exceptions(_PACKAGES_ROOT / "bootstrap")
    assert violations == [], (
        "Found bare 'except Exception: pass' in packages/bootstrap — "
        "replace with structured logging:\n" + "\n".join(violations)
    )
