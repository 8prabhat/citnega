"""Model gateway Pydantic models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ModelCapabilityFlags(BaseModel):
    local_only: bool = False
    supports_streaming: bool = True
    supports_tool_calling: bool = False
    supports_reasoning: bool = False
    supports_json_output: bool = False
    supports_multimodal: bool = False
    supports_long_context: bool = False
    max_context_tokens: int = 4096


class ModelInfo(BaseModel):
    model_id: str
    provider_type: str
    model_name: str
    local: bool
    capabilities: ModelCapabilityFlags
    cost_rank: int = 1  # 1=free local, 5=expensive remote
    priority: int = 50
    preferred_for: list[str] = Field(default_factory=list)
    health_status: str = "unknown"


class ModelMessage(BaseModel):
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict[str, object]] = Field(default_factory=list)


class TaskNeeds(BaseModel):
    """Routing hints supplied by the caller to influence model selection."""

    local_only: bool = False
    streaming_required: bool = True
    tool_calling_required: bool = False
    reasoning_required: bool = False
    task_type: str = "general"
    min_context_tokens: int = 0


class ModelRequest(BaseModel):
    model_id: str | None = None  # None = let gateway route
    messages: list[ModelMessage]
    tools: list[dict[str, object]] = Field(default_factory=list)
    temperature: float = 0.7
    max_tokens: int | None = None
    stream: bool = True
    response_format: dict[str, object] | None = None
    needs: TaskNeeds | None = None


class ModelChunk(BaseModel):
    """A single streaming chunk from a model provider."""

    content: str | None = None
    thinking: str | None = None  # native reasoning field (Ollama thinking models)
    tool_call_delta: list[dict[str, object]] | dict[str, object] | None = None
    finish_reason: str | None = None
    usage: dict[str, int] | None = None


class ModelResponse(BaseModel):
    """Normalised non-streaming response from a model provider."""

    model_id: str
    content: str
    tool_calls: list[dict[str, object]] = Field(default_factory=list)
    finish_reason: str
    usage: dict[str, int]  # prompt_tokens, completion_tokens, total_tokens
