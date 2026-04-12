"""
CallableTester — runtime-tests a freshly generated callable artifact.

Approach
--------
1. Build a minimal mock ``CallContext`` (no DB, no live model).
2. Auto-generate mock inputs from the callable's ``input_schema`` fields:
   str → "test", int → 0, float → 0.0, bool → False, list → [], Any → None.
3. Call ``instance._execute(mock_input, mock_ctx)`` directly (bypasses policy/
   events so there are no side effects and no infrastructure deps).
4. Return ``CodeTestResult``:
     - ``passed``   True if _execute returned without raising.
     - ``error``    Exception traceback (empty string on pass).
     - ``output``   String representation of the returned output (pass only).
     - ``duration_ms``

The test intentionally does NOT check the *correctness* of the output, only
that the code runs without crashing.  The LLM regeneration path uses the error
message to fix bugs and retry.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import time
import traceback
from typing import Any


@dataclass
class CodeTestResult:
    passed: bool
    error: str = ""  # traceback on failure, "" on pass
    output: str = ""  # str(output) on pass
    duration_ms: int = 0

    def __bool__(self) -> bool:
        return self.passed


class CallableTester:
    """
    Tests a generated callable instance by running ``_execute`` with mock inputs.

    Usage::

        result = await CallableTester().test(instance, model_gateway=None)
        if not result.passed:
            print(result.error)
    """

    async def test(
        self,
        instance: Any,
        model_gateway: Any = None,
    ) -> CodeTestResult:
        """
        Run ``_execute`` on *instance* with auto-generated mock inputs.

        Args:
            instance:      An instantiated BaseCallable subclass.
            model_gateway: Optional gateway so agent._call_model works
                           (None = agent returns a "(model unavailable)" stub).

        Returns:
            CodeTestResult with passed=True or passed=False + error traceback.
        """
        start = time.monotonic()
        try:
            mock_input = self._build_mock_input(instance)
            mock_ctx = self._build_mock_context(model_gateway)
            output = await asyncio.wait_for(
                instance._execute(mock_input, mock_ctx),
                timeout=30.0,
            )
            return CodeTestResult(
                passed=True,
                output=str(output)[:400],
                duration_ms=int((time.monotonic() - start) * 1000),
            )
        except TimeoutError:
            return CodeTestResult(
                passed=False,
                error="_execute timed out after 30 s",
                duration_ms=int((time.monotonic() - start) * 1000),
            )
        except Exception:
            return CodeTestResult(
                passed=False,
                error=traceback.format_exc(),
                duration_ms=int((time.monotonic() - start) * 1000),
            )

    # ── helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_mock_input(instance: Any) -> Any:
        """
        Instantiate ``instance.input_schema`` with placeholder values for
        every field so the schema's validators are satisfied.
        """
        schema_cls = getattr(instance, "input_schema", None)
        if schema_cls is None:
            raise TypeError(f"{type(instance).__name__} has no input_schema")

        mock_values: dict[str, Any] = {}
        try:
            fields = schema_cls.model_fields
        except AttributeError:
            # Not a pydantic model — return empty instance attempt
            return schema_cls()

        for field_name, field_info in fields.items():
            ann = field_info.annotation
            mock_values[field_name] = _mock_value(ann, field_info)

        return schema_cls(**mock_values)

    @staticmethod
    def _build_mock_context(model_gateway: Any = None) -> Any:
        """Build a minimal CallContext that satisfies the _execute signature."""
        from citnega.packages.protocol.callables.context import CallContext
        from citnega.packages.protocol.models.sessions import SessionConfig

        return CallContext(
            session_id="test-session",
            run_id="test-run",
            turn_id="test-turn",
            depth=0,
            parent_callable=None,
            session_config=SessionConfig(
                session_id="test-session",
                name="test",
                framework="direct",
                default_model_id="test-model",
            ),
            model_gateway=model_gateway,
        )


# ── type-based mock value factory ─────────────────────────────────────────────


def _mock_value(annotation: Any, field_info: Any) -> Any:
    """Return a sensible placeholder value for a pydantic field annotation."""
    # Check if the field has a usable default or default_factory.
    # Pydantic uses a special PydanticUndefined sentinel for required fields;
    # anything that is *not* that sentinel and not Ellipsis is a real default.
    try:
        from pydantic_core import PydanticUndefinedType

        _SENTINEL = PydanticUndefinedType
    except ImportError:
        _SENTINEL = type(None)  # fallback — should never happen on pydantic v2

    try:
        default = field_info.default
        if default is not ... and not isinstance(default, _SENTINEL):  # type: ignore[arg-type]
            return default
    except Exception:
        pass

    try:
        if field_info.default_factory is not None:  # type: ignore[misc]
            return field_info.default_factory()  # type: ignore[misc]
    except Exception:
        pass

    # Resolve type
    origin = getattr(annotation, "__origin__", None)

    # list[X] or List[X]
    if origin is list:
        return []

    # dict[K,V] or Dict[K,V]
    if origin is dict:
        return {}

    # Optional[X] == Union[X, None]
    import types as _types

    if origin is _types.UnionType or (
        hasattr(annotation, "__args__") and type(None) in getattr(annotation, "__args__", ())
    ):
        # Return None for Optional fields
        return None

    # Primitive types
    _DEFAULTS: dict[Any, Any] = {
        str: "test_value",
        int: 0,
        float: 0.0,
        bool: False,
        bytes: b"",
    }
    if annotation in _DEFAULTS:
        return _DEFAULTS[annotation]

    # Pydantic sub-model: try default-constructing it
    try:
        if hasattr(annotation, "model_fields"):
            sub: dict[str, Any] = {}
            for fn, fi in annotation.model_fields.items():
                sub[fn] = _mock_value(fi.annotation, fi)
            return annotation(**sub)
    except Exception:
        pass

    # Final fallback
    return None
