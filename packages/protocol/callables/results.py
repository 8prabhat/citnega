"""InvokeResult, StreamChunk and StreamChunkKind."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.types import CallableType

if TYPE_CHECKING:
    from citnega.packages.shared.errors import CitnegaError


class StreamChunkKind(str, Enum):
    TOKEN       = "token"
    TOOL_UPDATE = "tool_update"
    RESULT      = "result"
    TERMINAL    = "terminal"


class StreamChunk(BaseModel):
    schema_version: int = 1
    kind:           StreamChunkKind
    content:        str | None = None
    result:         "InvokeResult | None" = None
    metadata:       dict[str, object] = Field(default_factory=dict)

    @classmethod
    def token(cls, text: str) -> "StreamChunk":
        return cls(kind=StreamChunkKind.TOKEN, content=text)

    @classmethod
    def from_result(cls, result: "InvokeResult") -> "StreamChunk":
        return cls(kind=StreamChunkKind.RESULT, result=result)

    @classmethod
    def terminal(cls) -> "StreamChunk":
        return cls(kind=StreamChunkKind.TERMINAL)


class InvokeResult(BaseModel):
    """
    Typed outcome of a callable invocation.

    Errors are captured *inside* the result — IInvocable.invoke() never raises.
    """

    schema_version:  int = 1
    callable_name:   str
    callable_type:   CallableType
    output:          BaseModel | None = None
    error:           "CitnegaError | None" = None
    duration_ms:     int
    sub_invocations: list["InvokeResult"] = Field(default_factory=list)
    token_usage:     dict[str, int] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}

    @property
    def success(self) -> bool:
        return self.error is None

    @classmethod
    def ok(
        cls,
        name: str,
        callable_type: CallableType,
        output: BaseModel,
        duration_ms: int,
        token_usage: dict[str, int] | None = None,
    ) -> "InvokeResult":
        return cls(
            callable_name=name,
            callable_type=callable_type,
            output=output,
            duration_ms=duration_ms,
            token_usage=token_usage or {},
        )

    @classmethod
    def from_error(
        cls,
        name: str,
        callable_type: CallableType,
        error: "CitnegaError",
        duration_ms: int,
    ) -> "InvokeResult":
        return cls(
            callable_name=name,
            callable_type=callable_type,
            error=error,
            duration_ms=duration_ms,
        )


# Resolve forward references so Pydantic can validate CitnegaError at runtime.
def _rebuild() -> None:
    from citnega.packages.shared.errors import CitnegaError  # noqa: PLC0415
    InvokeResult.model_rebuild()
    StreamChunk.model_rebuild()


_rebuild()
