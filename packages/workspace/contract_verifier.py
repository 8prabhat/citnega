"""Runtime contract verification for dynamically onboarded callables."""

from __future__ import annotations

from collections.abc import Callable
import inspect
import re

from pydantic import BaseModel

from citnega.packages.protocol.callables.types import CallablePolicy, CallableType

_SNAKE_CASE_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class ContractVerificationError(ValueError):
    """Raised when a callable fails onboarding contract checks."""


class ContractVerifier:
    """Verifies runtime metadata contract for dynamically loaded callables."""

    def verify(self, callable_obj: object) -> None:
        errors = self.collect_errors(callable_obj)
        if errors:
            raise ContractVerificationError("; ".join(errors))

    def collect_errors(self, callable_obj: object) -> list[str]:
        errors: list[str] = []
        name = getattr(callable_obj, "name", None)
        description = getattr(callable_obj, "description", None)
        callable_type = getattr(callable_obj, "callable_type", None)
        input_schema = getattr(callable_obj, "input_schema", None)
        output_schema = getattr(callable_obj, "output_schema", None)
        policy = getattr(callable_obj, "policy", None)

        if not isinstance(name, str) or not name.strip():
            errors.append("missing non-empty callable.name")
        elif not _SNAKE_CASE_RE.fullmatch(name):
            errors.append(f"callable.name must be snake_case: {name!r}")

        if not isinstance(description, str) or not description.strip():
            errors.append("missing non-empty callable.description")

        if not isinstance(callable_type, CallableType):
            errors.append("callable_type must be a CallableType")

        if not _is_pydantic_model_type(input_schema):
            errors.append("input_schema must be a BaseModel subclass")

        if not _is_pydantic_model_type(output_schema):
            errors.append("output_schema must be a BaseModel subclass")

        if not isinstance(policy, CallablePolicy):
            errors.append("policy must be a CallablePolicy instance")
        elif policy.timeout_seconds <= 0:
            errors.append("policy.timeout_seconds must be > 0")

        if not _has_execute(callable_obj):
            errors.append("callable must define an _execute method")

        return errors


def verify_callable_contract(callable_obj: object) -> None:
    """Convenience wrapper used at registration boundaries."""
    ContractVerifier().verify(callable_obj)


def _is_pydantic_model_type(candidate: object) -> bool:
    return isinstance(candidate, type) and issubclass(candidate, BaseModel)


def _has_execute(callable_obj: object) -> bool:
    execute = getattr(callable_obj, "_execute", None)
    if execute is None:
        return False
    if isinstance(execute, Callable):
        return True
    return inspect.ismethod(execute) or inspect.isfunction(execute)
