"""InvokeResult, StreamChunk and StreamChunkKind."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.shared.errors import CitnegaError

if TYPE_CHECKING:
    pass


class StreamChunkKind(StrEnum):
    TOKEN = "token"
    TOOL_UPDATE = "tool_update"
    RESULT = "result"
    TERMINAL = "terminal"


class StreamChunk(BaseModel):
    schema_version: int = 1
    kind: StreamChunkKind
    content: str | None = None
    result: InvokeResult | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    @classmethod
    def token(cls, text: str) -> StreamChunk:
        return cls(kind=StreamChunkKind.TOKEN, content=text)

    @classmethod
    def from_result(cls, result: InvokeResult) -> StreamChunk:
        return cls(kind=StreamChunkKind.RESULT, result=result)

    @classmethod
    def terminal(cls) -> StreamChunk:
        return cls(kind=StreamChunkKind.TERMINAL)


class InvokeResult(BaseModel):
    """
    Typed outcome of a callable invocation.

    Errors are captured *inside* the result — IInvocable.invoke() never raises.
    """

    schema_version: int = 1
    callable_name: str
    callable_type: CallableType
    output: BaseModel | None = None
    error: CitnegaError | None = None
    duration_ms: int
    sub_invocations: list[InvokeResult] = Field(default_factory=list)
    token_usage: dict[str, int] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}

    @property
    def success(self) -> bool:
        return self.error is None

    def get_output_field(self, field: str, default: str = "") -> str:
        """Safely extract a string field from the output model.

        Most tool outputs expose a ``result`` field; specialist outputs use
        ``response``.  This helper avoids ``type: ignore[attr-defined]`` at
        every call site.
        """
        if self.output is None:
            return default
        return str(getattr(self.output, field, default))

    @classmethod
    def ok(
        cls,
        name: str,
        callable_type: CallableType,
        output: BaseModel,
        duration_ms: int,
        token_usage: dict[str, int] | None = None,
    ) -> InvokeResult:
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
        error: CitnegaError,
        duration_ms: int,
    ) -> InvokeResult:
        return cls(
            callable_name=name,
            callable_type=callable_type,
            error=error,
            duration_ms=duration_ms,
        )


# Resolve forward references so Pydantic can validate CitnegaError at runtime.
def _rebuild() -> None:
    InvokeResult.model_rebuild()
    StreamChunk.model_rebuild()


_rebuild()
