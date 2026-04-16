"""Unit tests for dynamic callable contract verification."""

from __future__ import annotations

from pydantic import BaseModel
import pytest

from citnega.packages.protocol.callables.types import CallablePolicy, CallableType
from citnega.packages.workspace.contract_verifier import (
    ContractVerificationError,
    verify_callable_contract,
)


class _Input(BaseModel):
    text: str = ""


class _Output(BaseModel):
    response: str = ""


class _ValidCallable:
    name = "valid_tool"
    description = "valid"
    callable_type = CallableType.TOOL
    input_schema = _Input
    output_schema = _Output
    policy = CallablePolicy(timeout_seconds=10.0)

    async def _execute(self, input_obj, context):
        return _Output(response="ok")


def test_verify_callable_contract_passes_for_valid_callable() -> None:
    verify_callable_contract(_ValidCallable())


def test_verify_callable_contract_rejects_missing_schema() -> None:
    class _Invalid:
        name = "invalid_tool"
        description = "invalid"
        callable_type = CallableType.TOOL
        input_schema = _Input
        output_schema = object
        policy = CallablePolicy()

        async def _execute(self, input_obj, context):
            return _Output(response="ok")

    with pytest.raises(ContractVerificationError, match="output_schema"):
        verify_callable_contract(_Invalid())


def test_verify_callable_contract_rejects_non_snake_case_name() -> None:
    class _InvalidName:
        name = "InvalidName"
        description = "invalid"
        callable_type = CallableType.TOOL
        input_schema = _Input
        output_schema = _Output
        policy = CallablePolicy()

        async def _execute(self, input_obj, context):
            return _Output(response="ok")

    with pytest.raises(ContractVerificationError, match="snake_case"):
        verify_callable_contract(_InvalidName())
