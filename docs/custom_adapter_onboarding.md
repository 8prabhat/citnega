# Custom Framework Adapter Onboarding

This document is a complete technical specification for implementing a new framework adapter in Citnega. It covers every interface contract, every object type, and every wiring step. Use it as a self-contained guide without needing to read the source.

---

## Architecture Overview

An adapter is a **3-component plugin** that bridges a third-party agent SDK to Citnega's session, tool, and event infrastructure. All three components must be implemented:

| Component | Base Class | Scope | Responsibility |
|-----------|-----------|-------|----------------|
| `Adapter` | `BaseFrameworkAdapter` | Application-scoped (singleton) | Lifecycle, runner factory |
| `Runner` | `BaseFrameworkRunner` | Session-scoped (one per session) | Turn execution, streaming, state |
| `CallableFactory` | `BaseCallableFactory` | Adapter-scoped | Wrap Citnega callables into SDK-native objects |

**Immovable constraint:** The SDK is **never imported at module level**. All `import your_sdk` calls live inside methods that execute lazily, so the application starts cleanly without the SDK installed.

---

## File Layout

```
packages/adapters/your_framework/
    __init__.py
    adapter.py           # YourFrameworkAdapter  →  BaseFrameworkAdapter
    runner.py            # YourRunner            →  BaseFrameworkRunner
    callable_factory.py  # YourCallableFactory   →  BaseCallableFactory
    model_resolver.py    # SDK model construction (all SDK imports isolated here)
```

Nothing outside this directory imports your SDK.

---

## Part 1 — Adapter (`adapter.py`)

### Role

Created once at bootstrap. Validates config, creates one runner per session, shuts down on exit.

### Contract (`BaseFrameworkAdapter`)

```python
# packages/adapters/base/base_adapter.py

class BaseFrameworkAdapter(IFrameworkAdapter):

    def __init__(self) -> None:
        self._config: AdapterConfig | None = None
        self._initialized: bool = False
        self._cancellation_tokens: list[CancellationToken] = []

    # ── PROVIDED — do NOT override ────────────────────────────────────────

    async def initialize(self, config: AdapterConfig) -> None:
        """
        Guards double-init. Sets self._config, calls _do_initialize(config),
        sets self._initialized = True, logs completion.
        """

    async def shutdown(self) -> None:
        """
        Calls token.cancel() on every registered CancellationToken,
        clears the list, then calls _do_shutdown().
        """

    def _new_cancellation_token(self) -> CancellationToken:
        """
        Create and register a token for a new runner.
        MUST be called inside create_runner() and the token passed to the runner.
        """

    def _release_token(self, token: CancellationToken) -> None:
        """Remove a completed runner's token (call on session end if desired)."""

    # ── MUST IMPLEMENT ────────────────────────────────────────────────────

    @property
    @abstractmethod
    def framework_name(self) -> str:
        """Unique lowercase identifier, e.g. 'adk', 'langgraph', 'yoursdk'."""

    @abstractmethod
    async def _do_initialize(self, config: AdapterConfig) -> None:
        """
        Framework-specific init. Validate config, check SDK version.
        Do NOT import the SDK here — defer to runner.
        """

    @abstractmethod
    async def create_runner(
        self,
        session: Session,
        callables: list[IInvocable],
        model_gateway: Any,
    ) -> IFrameworkRunner:
        """
        Create and return a session-scoped runner.
        Called once per session at session creation time.

        Required:
          token = self._new_cancellation_token()   ← MUST call this
          serializer = CheckpointSerializer(
              self._path_resolver.checkpoint_dir(session.config.session_id),
              framework_name=self.framework_name,
          )
          return YourRunner(
              session=session,
              callables=callables,
              cancellation_token=token,
              checkpoint_serializer=serializer,
              ...
          )
        """

    @property
    @abstractmethod
    def callable_factory(self) -> ICallableFactory:
        """Return the factory instance (lazy-init pattern recommended)."""

    # ── OPTIONAL overrides (default: no-op) ──────────────────────────────

    async def _do_shutdown(self) -> None:
        """Release SDK-level resources (connection pools, etc.)."""

    def set_capability_registry(self, registry: Any) -> None:
        """Receive the CapabilityRegistry at startup (for skill lookups)."""

    def get_runner(self, session_id: str) -> IFrameworkRunner | None:
        """Return live runner for session_id, or None."""

    async def set_session_model(self, session_id: str, model_id: str) -> None:
        """Hot-swap the model for an existing session."""

    def list_models(self) -> list[ModelInfo]:
        """Return adapter-owned model catalog (empty list is fine)."""

    def read_session_conversation_field(
        self, session_id: str, field: str
    ) -> list[dict[str, Any]]:
        """
        Cold-read a conversation field for a session with no live runner.
        Used for session recovery. Return [] if not supported.
        """
```

### `AdapterConfig` — input to `_do_initialize`

```python
class AdapterConfig(BaseModel):
    framework_name: str                          # matches your framework_name property
    default_model_id: str                        # e.g. "gpt-4o", "gemma4-27b-local"
    framework_specific: dict[str, Any] = {}      # pass extra SDK config here
```

### Minimal implementation

```python
class YourFrameworkAdapter(BaseFrameworkAdapter):

    def __init__(self, path_resolver: PathResolver) -> None:
        super().__init__()
        self._path_resolver = path_resolver
        self._translator = EventTranslator(framework_name="your_framework")
        self._factory: YourCallableFactory | None = None

    @property
    def framework_name(self) -> str:
        return "your_framework"

    async def _do_initialize(self, config: AdapterConfig) -> None:
        # No SDK imports. Validate config, log only.
        runtime_logger.info("your_framework_adapter_init", model=config.default_model_id)

    async def create_runner(
        self,
        session: Session,
        callables: list[IInvocable],
        model_gateway: Any,
    ) -> "YourRunner":
        token = self._new_cancellation_token()          # required
        serializer = CheckpointSerializer(
            self._path_resolver.checkpoint_dir(session.config.session_id),
            framework_name="your_framework",
        )
        model_id = (
            self._config.default_model_id if self._config
            else session.config.default_model_id
        )
        return YourRunner(
            session=session,
            callables=callables,
            cancellation_token=token,
            checkpoint_serializer=serializer,
            event_translator=self._translator,
            model_id=model_id,
        )

    @property
    def callable_factory(self) -> "YourCallableFactory":
        if self._factory is None:
            self._factory = YourCallableFactory(self._translator)
        return self._factory
```

---

## Part 2 — Runner (`runner.py`)

### Role

One instance per active session, lives across turns. Holds all mutable state: conversation history, live SDK session handle, tool call records. `_do_run_turn` is called on every user message.

### Contract (`BaseFrameworkRunner`)

```python
# packages/adapters/base/base_runner.py

class BaseFrameworkRunner(IFrameworkRunner):

    def __init__(
        self,
        session: Session,
        cancellation_token: CancellationToken,
        checkpoint_serializer: CheckpointSerializer,
    ) -> None:
        self._session = session
        self._token = cancellation_token          # poll is_cancelled() in loops
        self._serializer = checkpoint_serializer
        self._current_run_id: str | None = None
        self._paused = False
        self._active_callable: str | None = None  # set to tool name during tool call
        self._context_token_count = 0

    # ── PROVIDED — do NOT override ────────────────────────────────────────

    async def run_turn(
        self,
        user_input: str,
        context: ContextObject,
        event_queue: asyncio.Queue[CanonicalEvent],
    ) -> str:
        """
        Template method:
          1. token.is_cancelled() → raise asyncio.CancelledError
          2. self._paused         → raise RuntimeError("Runner is paused...")
          3. Set self._current_run_id = context.run_id
          4. Log debug
          5. Call _do_run_turn(user_input, context, event_queue)
          6. Return run_id
        """

    async def pause(self, run_id: str) -> None:
        """Sets self._paused = True, calls _do_pause(run_id)."""

    async def resume(self, run_id: str) -> None:
        """Sets self._paused = False, calls _do_resume(run_id)."""

    async def cancel(self, run_id: str) -> None:
        """Calls self._token.cancel(), then _do_cancel(run_id)."""

    async def get_state_snapshot(self) -> StateSnapshot: ...
    async def save_checkpoint(self, run_id: str) -> CheckpointMeta: ...
    async def restore_checkpoint(self, checkpoint_id: str) -> None: ...

    # ── MUST IMPLEMENT ────────────────────────────────────────────────────

    @abstractmethod
    async def _do_run_turn(
        self,
        user_input: str,
        context: ContextObject,
        event_queue: asyncio.Queue[CanonicalEvent],
    ) -> str:
        """
        Execute one conversational turn.

        Requirements:
          - Import SDK lazily (inside this method or _get_sdk_client())
          - Poll self._token.is_cancelled() inside any streaming loop
          - Emit TokenEvent to event_queue for every text chunk
          - Return context.run_id
        """

    @abstractmethod
    async def _do_pause(self, run_id: str) -> None:
        """Save any in-progress state. Log the event."""

    @abstractmethod
    async def _do_resume(self, run_id: str) -> None:
        """Restore state saved in _do_pause. Log the event."""

    @abstractmethod
    async def _do_cancel(self, run_id: str) -> None:
        """Clear history/state. Cancel any in-flight SDK tasks. Log."""

    @abstractmethod
    async def _do_get_state_snapshot(self) -> RunState:
        """Return a RunState enum value reflecting current execution state."""

    @abstractmethod
    async def _do_save_checkpoint(self, run_id: str) -> dict[str, object]:
        """
        Serialize runner state to a JSON-serializable dict.
        Only primitive types: str, int, float, bool, None, list, dict.
        No SDK objects — they must be reduced to plain Python first.
        """

    # ── OPTIONAL override (default: no-op) ───────────────────────────────

    async def _do_restore_checkpoint(self, framework_state: dict[str, object]) -> None:
        """Rebuild SDK session state from the dict saved by _do_save_checkpoint."""
```

### `ContextObject` — what `_do_run_turn` receives

```python
class ContextObject(BaseModel):
    session_id: str
    run_id: str            # unique per turn — return this from _do_run_turn
    user_input: str        # user's message text
    sources: list[ContextSource]   # KB snippets, session summaries, runtime state
    messages: list[dict[str, Any]] # conversation history:
                                   # [{"role": "user"|"assistant", "content": "..."}]
    active_model_id: str | None    # model for this turn (may override session default)
    total_tokens: int      # tokens assembled in context
    budget_remaining: int  # tokens available for the model response
    truncated: bool        # True if history was pruned to fit budget
    assembled_at: datetime
    metadata: dict[str, Any]       # e.g. {"token_budget_remaining": 6000}
```

### Emitting events — the streaming contract

Every text token must be pushed into `event_queue` as a `TokenEvent`. This drives the TUI streaming display.

```python
from citnega.packages.protocol.events.streaming import TokenEvent
import contextlib

# Inside _do_run_turn, for each text chunk from the SDK:
with contextlib.suppress(asyncio.QueueFull):
    event_queue.put_nowait(
        TokenEvent(
            session_id=self._session.config.session_id,
            run_id=context.run_id,
            turn_id=context.run_id,   # use run_id as turn_id
            token="the text chunk",
            finish_reason=None,       # or "stop" on the final token
        )
    )
```

Additional optional event types (all inherit `BaseEvent`):

| Event class | When to emit |
|-------------|-------------|
| `TokenEvent` | Every LLM text chunk **(required)** |
| `ThinkingEvent` | Model reasoning/chain-of-thought text |
| `CallableStartEvent` | Tool call begins |
| `CallableEndEvent` | Tool call completes |
| `GenericFrameworkEvent` | Any SDK-specific event without a dedicated type |

All events share this base:

```python
class BaseEvent(BaseModel):
    schema_version: int = 1
    event_id: str          # auto-generated UUID
    event_type: str        # class name string
    timestamp: datetime    # auto-set to utcnow
    session_id: str
    run_id: str
    turn_id: str | None
    callable_name: str | None
    callable_type: CallableType | None
    framework_name: str | None
```

### Cancellation — the polling contract

```python
async for chunk in sdk_client.stream(user_input):
    if self._token.is_cancelled():
        raise asyncio.CancelledError("runner cancelled mid-turn")
    with contextlib.suppress(asyncio.QueueFull):
        event_queue.put_nowait(TokenEvent(...))
```

Check `is_cancelled()` after **every** `await` that can block. Do not rely solely on `asyncio.CancelledError` — that only fires at explicit `await` points.

### `RunState` enum — return from `_do_get_state_snapshot`

```python
class RunState(StrEnum):
    PENDING             = "pending"
    CONTEXT_ASSEMBLING  = "context_assembling"
    EXECUTING           = "executing"
    WAITING_APPROVAL    = "waiting_approval"
    PAUSED              = "paused"
    COMPLETED           = "completed"
    FAILED              = "failed"
    CANCELLED           = "cancelled"

# Minimal correct implementation:
async def _do_get_state_snapshot(self) -> RunState:
    if self._token.is_cancelled():
        return RunState.CANCELLED
    if self._paused:
        return RunState.PAUSED
    return RunState.EXECUTING
```

### Checkpoint contract

`_do_save_checkpoint` must return a plain-Python dict. The `CheckpointSerializer` wraps it in a versioned JSON envelope and gzip-compresses it. Returning SDK objects will cause a serialization failure at runtime.

```python
async def _do_save_checkpoint(self, run_id: str) -> dict[str, object]:
    return {
        "history": [
            {"role": m["role"], "content": m["content"]}
            for m in self._history
        ],
        "model_id": self._model_id,
        "session_id": self._session.config.session_id,
    }

async def _do_restore_checkpoint(self, framework_state: dict[str, object]) -> None:
    self._history = list(framework_state.get("history", []))
    # Rebuild SDK session object from history if your SDK requires it
```

### Calling Citnega tools from inside your SDK

When your SDK fires a tool call, this is how to dispatch it to the Citnega callable:

```python
def _make_tool_wrapper(self, cbl: IInvocable) -> Callable:
    """Build an async function that your SDK can call as a tool."""

    async def _fn(**kwargs: object) -> dict[str, object]:
        from citnega.packages.protocol.callables.context import CallContext

        ctx = CallContext(
            session_id=self._session.config.session_id,
            run_id=self._current_run_id or "direct",
            turn_id="your_framework-turn",
            session_config=self._session.config,
        )
        # Validate kwargs against the tool's Pydantic input schema:
        validated = cbl.input_schema.model_validate(kwargs)

        # invoke() NEVER raises — errors are in result.error:
        result = await cbl.invoke(validated, ctx)

        if result.output is not None:
            return result.output.model_dump()
        if result.error is not None:
            return {"error": str(result.error)}
        return {}

    _fn.__name__ = cbl.name
    _fn.__doc__ = cbl.description
    return _fn
```

### `IInvocable` — the tool object contract

```python
class IInvocable(ABC):
    name: str                        # unique name, e.g. "run_shell", "read_file"
    description: str                 # one-sentence purpose
    callable_type: CallableType      # TOOL | SPECIALIST | CORE
    input_schema: type[BaseModel]    # Pydantic model — validate input kwargs against this
    output_schema: type[BaseModel]   # Pydantic model — result.output is an instance
    policy: CallablePolicy           # timeout_seconds, requires_approval, network_allowed

    async def invoke(
        self,
        input: BaseModel,
        context: CallContext,
    ) -> InvokeResult: ...
    # Returns InvokeResult(output=BaseModel|None, error=Exception|None)
    # NEVER raises. All errors land in result.error.
```

```python
class CallableType(StrEnum):
    TOOL       = "tool"       # stateless function (read_file, run_shell, search_web)
    SPECIALIST = "specialist" # stateful sub-agent (SecuritySpecialist, etc.)
    CORE       = "core"       # orchestration agent (ConversationAgent, PlannerAgent)
```

```python
class CallContext:
    session_id: str
    run_id: str
    turn_id: str
    session_config: SessionConfig
    capability_registry: Any = None  # pass if skills lookup is needed
```

### `Session` and `SessionConfig` — what `create_runner` receives

```python
class SessionConfig(BaseModel):
    session_id: str                         # use as SDK session key
    name: str                               # human display name
    framework: str                          # "your_framework"
    default_model_id: str                   # resolved model for this session
    local_only: bool = True
    max_callable_depth: int = 2
    approval_required_tools: list[str] = []
    kb_enabled: bool = True
    max_context_tokens: int = 8192
    approval_timeout_seconds: float = 300.0
    tags: list[str] = []

class Session(BaseModel):
    config: SessionConfig    # immutable — do not write to this
    created_at: datetime
    last_active_at: datetime
    run_count: int = 0
    state: SessionState = SessionState.IDLE
    strategy_spec: StrategySpec | None = None
```

---

## Part 3 — Callable Factory (`callable_factory.py`)

### Role

Translates `IInvocable` objects into your SDK's native tool representation. Each SDK wants a different shape: ADK wants async Python functions; LangGraph wants `StructuredTool`; CrewAI wants `BaseTool` subclasses. This is where that translation lives.

### Contract (`BaseCallableFactory`)

```python
class BaseCallableFactory(ICallableFactory):

    def __init__(self, event_translator: EventTranslator) -> None:
        self._translator = event_translator

    # ── PROVIDED helper ───────────────────────────────────────────────────

    def _build_tool_description(self, callable: IInvocable) -> str:
        """
        Returns a formatted string:
            name: description
            Parameters:
              field1 (type): description
              field2 (type): description
        Uses callable.input_schema.model_json_schema() to extract fields.
        """

    # ── MUST IMPLEMENT ────────────────────────────────────────────────────

    @abstractmethod
    def create_tool(self, callable: IInvocable) -> Any:
        """
        Return whatever your SDK needs to register a tool.

        The return value is consumed by your runner's lazy-init method
        when building the SDK agent. Return format is entirely yours —
        a dict descriptor, a live callable, a dataclass, etc.

        Common pattern (dict descriptor, runner builds live wrapper later):
            return {
                "type": "citnega_tool",
                "name": callable.name,
                "description": self._build_tool_description(callable),
                "callable": callable,
                "input_schema": callable.input_schema.model_json_schema(),
            }
        """

    @abstractmethod
    def create_specialist(self, callable: IStreamable) -> Any:
        """Wrap a specialist agent (sub-agent the model can invoke)."""

    @abstractmethod
    def create_core_agent(self, callable: IStreamable) -> Any:
        """
        Wrap a core orchestration agent (ConversationAgent, PlannerAgent).
        Can return the same shape as create_specialist if your SDK
        does not distinguish between agent types.
        """

    def translate_event(self, framework_event: Any) -> CanonicalEvent | None:
        """Default: delegates to self._translator.translate(). Override if needed."""
```

### Three reference implementations

**ADK** — descriptor dict, runner builds async functions at agent-construction time:
```python
def create_tool(self, callable: IInvocable) -> Any:
    return {
        "type": "citnega_tool",
        "name": callable.name,
        "description": self._build_tool_description(callable),
        "callable": callable,
        "input_schema": callable.input_schema.model_json_schema(),
    }
```

**LangGraph** — descriptor dict with `args_schema` (Pydantic model class, not instance):
```python
def create_tool(self, callable: IInvocable) -> Any:
    return {
        "type": "citnega_tool",
        "name": callable.name,
        "description": self._build_tool_description(callable),
        "callable": callable,
        "args_schema": callable.input_schema,   # the Pydantic model class itself
    }
```

**Direct** — no SDK wrapping needed; pass-through:
```python
def create_tool(self, callable: IInvocable) -> Any:
    return callable
```

---

## Part 4 — Model Resolver (`model_resolver.py`)

### Role

Your SDK requires a specific model object, not just a string ID. All SDK model class imports and construction live **exclusively** here. The runner imports `resolve_your_model(model_id)` — nothing else in Citnega touches your model class.

```python
# packages/adapters/your_framework/model_resolver.py

def resolve_your_model(model_id: str | None) -> Any:
    """
    Translate a Citnega model_id string to your SDK's model object.

    Resolution order:
      1. Explicit prefix  (e.g. "yoursdk/gpt-4o")
      2. Citnega model-registry lookup  (provider_type == "yoursdk")
      3. Pass-through string for SDK-native model names
    """
    try:
        from your_sdk.models import YourModelClass    # SDK import ONLY here
    except ImportError as exc:
        raise ImportError(
            "your_sdk is not installed. Run: pip install 'citnega[your_framework]'"
        ) from exc

    mid = (model_id or "").strip()
    if not mid:
        return YourModelClass()           # SDK default

    # 1. Explicit prefix
    if mid.startswith("yoursdk/"):
        return YourModelClass(model=mid.removeprefix("yoursdk/"))

    # 2. Citnega model registry lookup
    try:
        from citnega.packages.model_gateway.registry import ModelRegistry
        registry = ModelRegistry()
        registry.load()
        for info in registry.list_all():
            if info.model_id == mid and info.provider_type == "yoursdk":
                return YourModelClass(
                    model=info.model_name,
                    api_key=info.api_key,
                    base_url=info.base_url,
                )
    except Exception:
        pass

    # 3. Pass-through
    return YourModelClass(model=mid)
```

The runner calls this lazily (once, on first turn):

```python
def _get_sdk_client(self) -> Any:
    if self._sdk_client is None:
        from citnega.packages.adapters.your_framework.model_resolver import resolve_your_model
        model = resolve_your_model(self._model_id)
        tools = [self._make_tool_wrapper(c) for c in self._callables]
        self._sdk_client = YourSDK.Agent(model=model, tools=tools)
    return self._sdk_client
```

---

## Part 5 — Supporting Infrastructure

These classes are provided by Citnega. Instantiate and use them; do not subclass or modify them.

### `CancellationToken`

```python
# packages/adapters/base/cancellation.py

class CancellationToken:
    def cancel(self) -> None:
        """Signal cancellation. Called by adapter.shutdown()."""

    def is_cancelled(self) -> bool:
        """
        Return True if cancellation was requested.
        Poll this inside every streaming loop in _do_run_turn.
        """

    async def wait(self) -> None:
        """Suspend until cancel() is called."""
```

### `CheckpointSerializer`

```python
# packages/adapters/base/checkpoint_serializer.py

class CheckpointSerializer:
    def __init__(self, checkpoint_dir: Path, framework_name: str) -> None: ...

    def save(
        self,
        session_id: str,
        run_id: str,
        framework_state: dict[str, object],   # YOUR serialized SDK state
    ) -> CheckpointMeta:
        """
        Wrap framework_state in a versioned JSON envelope:
          {
            "schema_version": 1,
            "checkpoint_id": "<uuid>",
            "session_id": "...",
            "run_id": "...",
            "framework_name": "...",
            "created_at": "<iso8601>",
            "framework_state": { <your dict> }
          }
        Gzip-compress and write to checkpoint_dir/{uuid}.json.gz.
        Returns CheckpointMeta(checkpoint_id, file_path, size_bytes, ...).
        """

    def load(self, file_path: str) -> dict[str, object]:
        """
        Decompress and parse a checkpoint file.
        Returns the full blob. Extract blob["framework_state"] for restore.
        Raises ValueError on schema version mismatch.
        """
```

### `EventTranslator`

```python
# packages/adapters/base/event_translator.py

class EventTranslator:
    def __init__(self, framework_name: str) -> None: ...

    def register(self, event_type_name: str, fn: Callable) -> None:
        """
        Register a handler for a specific SDK event class.
        fn signature: (event, session_id, run_id, turn_id) -> CanonicalEvent | None
        """

    def translate(
        self,
        framework_event: Any,
        session_id: str,
        run_id: str,
        turn_id: str | None = None,
    ) -> CanonicalEvent:
        """
        Dispatch to a registered handler by type(event).__name__.
        Falls back to GenericFrameworkEvent if no handler registered.
        """
```

### `CheckpointMeta` — returned by `save_checkpoint`

```python
class CheckpointMeta(BaseModel):
    checkpoint_id: str
    session_id: str
    run_id: str
    created_at: datetime
    framework_name: str
    file_path: str       # absolute path to the .json.gz file
    size_bytes: int
    state_summary: str   # ≤256-char summary of top-level primitive keys
```

### `StateSnapshot` — returned by `get_state_snapshot`

```python
class StateSnapshot(BaseModel):
    session_id: str
    current_run_id: str | None
    active_callable: str | None   # name of currently executing tool/agent, or None
    run_state: RunState
    context_token_count: int
    checkpoint_available: bool
    framework_name: str
    captured_at: datetime
```

---

## Part 6 — Wiring into Bootstrap

Two additive changes only. Nothing else in the codebase changes.

### `packages/bootstrap/bootstrap.py` — one `elif` block in `_select_adapter()`

```python
elif framework == "your_framework":
    from citnega.packages.adapters.your_framework.adapter import YourFrameworkAdapter
    return YourFrameworkAdapter(path_resolver)
```

### `pyproject.toml` — one optional-dependency entry

```toml
[project.optional-dependencies]
your_framework = ["your-sdk-package>=1.0"]
all            = ["citnega[adk,langgraph,crewai,your_framework,...]"]
```

### Activating via settings

In `~/.citnega/settings.toml` (or environment variable):

```toml
[runtime]
framework = "your_framework"
default_model_id = "yoursdk/gpt-4o"
```

---

## Part 7 — Complete Minimal Implementation

Copy this as your starting point. Replace `YourFramework` / `your_framework` / `your_sdk` throughout.

### `adapter.py`

```python
from __future__ import annotations
from typing import TYPE_CHECKING, Any

from citnega.packages.adapters.base.base_adapter import BaseFrameworkAdapter
from citnega.packages.adapters.base.checkpoint_serializer import CheckpointSerializer
from citnega.packages.adapters.base.event_translator import EventTranslator
from citnega.packages.observability.logging_setup import runtime_logger

if TYPE_CHECKING:
    from citnega.packages.adapters.your_framework.callable_factory import YourCallableFactory
    from citnega.packages.adapters.your_framework.runner import YourRunner
    from citnega.packages.protocol.callables.interfaces import IInvocable
    from citnega.packages.protocol.interfaces.adapter import AdapterConfig, ICallableFactory
    from citnega.packages.protocol.models.sessions import Session
    from citnega.packages.storage.path_resolver import PathResolver


class YourFrameworkAdapter(BaseFrameworkAdapter):

    def __init__(self, path_resolver: PathResolver) -> None:
        super().__init__()
        self._path_resolver = path_resolver
        self._translator = EventTranslator(framework_name="your_framework")
        self._factory: YourCallableFactory | None = None

    @property
    def framework_name(self) -> str:
        return "your_framework"

    async def _do_initialize(self, config: AdapterConfig) -> None:
        runtime_logger.info("your_framework_adapter_init", model=config.default_model_id)

    async def create_runner(
        self,
        session: Session,
        callables: list[IInvocable],
        model_gateway: Any,
    ) -> "YourRunner":
        from citnega.packages.adapters.your_framework.runner import YourRunner

        token = self._new_cancellation_token()
        serializer = CheckpointSerializer(
            self._path_resolver.checkpoint_dir(session.config.session_id),
            framework_name="your_framework",
        )
        model_id = (
            self._config.default_model_id if self._config
            else session.config.default_model_id
        )
        return YourRunner(
            session=session,
            callables=callables,
            cancellation_token=token,
            checkpoint_serializer=serializer,
            event_translator=self._translator,
            model_id=model_id,
        )

    @property
    def callable_factory(self) -> ICallableFactory:
        if self._factory is None:
            from citnega.packages.adapters.your_framework.callable_factory import (
                YourCallableFactory,
            )
            self._factory = YourCallableFactory(self._translator)
        return self._factory
```

### `runner.py`

```python
from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, Any

from citnega.packages.adapters.base.base_runner import BaseFrameworkRunner
from citnega.packages.observability.logging_setup import runtime_logger
from citnega.packages.protocol.events.streaming import TokenEvent
from citnega.packages.protocol.models.runs import RunState

if TYPE_CHECKING:
    from citnega.packages.adapters.base.cancellation import CancellationToken
    from citnega.packages.adapters.base.checkpoint_serializer import CheckpointSerializer
    from citnega.packages.adapters.base.event_translator import EventTranslator
    from citnega.packages.protocol.callables.interfaces import IInvocable
    from citnega.packages.protocol.events import CanonicalEvent
    from citnega.packages.protocol.models.context import ContextObject
    from citnega.packages.protocol.models.sessions import Session


class YourRunner(BaseFrameworkRunner):

    def __init__(
        self,
        session: Session,
        callables: list[IInvocable],
        cancellation_token: CancellationToken,
        checkpoint_serializer: CheckpointSerializer,
        event_translator: EventTranslator,
        model_id: str,
    ) -> None:
        super().__init__(session, cancellation_token, checkpoint_serializer)
        self._callables = callables
        self._translator = event_translator
        self._model_id = model_id
        self._sdk_client: Any = None          # lazy-init on first turn
        self._history: list[dict[str, object]] = []

    def _get_sdk_client(self) -> Any:
        """Lazy-build the SDK agent. SDK imported only here."""
        if self._sdk_client is not None:
            return self._sdk_client

        from your_sdk import Agent                        # SDK import HERE only
        from citnega.packages.adapters.your_framework.model_resolver import resolve_your_model

        model = resolve_your_model(self._model_id)
        tools = [self._make_tool_wrapper(c) for c in self._callables]
        self._sdk_client = Agent(model=model, tools=tools)
        return self._sdk_client

    def _make_tool_wrapper(self, cbl: IInvocable) -> Any:
        """Return an async function your SDK can call as a tool."""
        async def _fn(**kwargs: object) -> dict[str, object]:
            from citnega.packages.protocol.callables.context import CallContext
            ctx = CallContext(
                session_id=self._session.config.session_id,
                run_id=self._current_run_id or "direct",
                turn_id="your_framework-turn",
                session_config=self._session.config,
            )
            validated = cbl.input_schema.model_validate(kwargs)
            result = await cbl.invoke(validated, ctx)
            if result.output is not None:
                return result.output.model_dump()
            if result.error is not None:
                return {"error": str(result.error)}
            return {}

        _fn.__name__ = cbl.name
        _fn.__doc__ = cbl.description
        return _fn

    async def _do_run_turn(
        self,
        user_input: str,
        context: ContextObject,
        event_queue: asyncio.Queue[CanonicalEvent],
    ) -> str:
        client = self._get_sdk_client()
        session_id = self._session.config.session_id

        async for chunk in client.stream(user_input):          # adapt to your SDK's API
            if self._token.is_cancelled():
                raise asyncio.CancelledError("runner cancelled")

            text = getattr(chunk, "text", None) or str(chunk)
            if text:
                with contextlib.suppress(asyncio.QueueFull):
                    event_queue.put_nowait(
                        TokenEvent(
                            session_id=session_id,
                            run_id=context.run_id,
                            turn_id=context.run_id,
                            token=text,
                            finish_reason=None,
                        )
                    )
                self._history.append({"role": "assistant", "content": text})

        return context.run_id

    async def _do_pause(self, run_id: str) -> None:
        runtime_logger.info("your_framework_paused", run_id=run_id, history=len(self._history))

    async def _do_resume(self, run_id: str) -> None:
        runtime_logger.info("your_framework_resumed", run_id=run_id, history=len(self._history))

    async def _do_cancel(self, run_id: str) -> None:
        self._history.clear()
        runtime_logger.info("your_framework_cancelled", run_id=run_id)

    async def _do_get_state_snapshot(self) -> RunState:
        if self._token.is_cancelled():
            return RunState.CANCELLED
        if self._paused:
            return RunState.PAUSED
        return RunState.EXECUTING

    async def _do_save_checkpoint(self, run_id: str) -> dict[str, object]:
        return {
            "history": list(self._history),
            "model_id": self._model_id,
            "session_id": self._session.config.session_id,
        }

    async def _do_restore_checkpoint(self, framework_state: dict[str, object]) -> None:
        self._history = list(framework_state.get("history", []))
```

### `callable_factory.py`

```python
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from citnega.packages.adapters.base.base_callable_factory import BaseCallableFactory

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.interfaces import IInvocable, IStreamable
    from citnega.packages.protocol.events import CanonicalEvent


class YourCallableFactory(BaseCallableFactory):

    def create_tool(self, callable: IInvocable) -> Any:
        return {
            "type": "citnega_tool",
            "name": callable.name,
            "description": self._build_tool_description(callable),
            "callable": callable,
            "input_schema": callable.input_schema.model_json_schema(),
        }

    def create_specialist(self, callable: IStreamable) -> Any:
        return {
            "type": "citnega_specialist",
            "name": callable.name,
            "description": callable.description,
            "callable": callable,
        }

    def create_core_agent(self, callable: IStreamable) -> Any:
        return {
            "type": "citnega_core_agent",
            "name": callable.name,
            "description": callable.description,
            "callable": callable,
        }

    def translate_event(self, framework_event: Any) -> CanonicalEvent | None:
        return self._translator.translate(framework_event, "", "", None)
```

### `model_resolver.py`

```python
from __future__ import annotations

from typing import Any


def resolve_your_model(model_id: str | None) -> Any:
    try:
        from your_sdk.models import YourModelClass
    except ImportError as exc:
        raise ImportError(
            "your_sdk is not installed. Run: pip install 'citnega[your_framework]'"
        ) from exc

    mid = (model_id or "").strip()
    if not mid:
        return YourModelClass()

    if mid.startswith("yoursdk/"):
        return YourModelClass(model=mid.removeprefix("yoursdk/"))

    try:
        from citnega.packages.model_gateway.registry import ModelRegistry
        registry = ModelRegistry()
        registry.load()
        for info in registry.list_all():
            if info.model_id == mid and info.provider_type == "yoursdk":
                return YourModelClass(model=info.model_name)
    except Exception:
        pass

    return YourModelClass(model=mid)
```

---

## Part 8 — Testing Your Adapter

Adapter tests live in `tests/unit/adapters/test_your_framework.py`. Use mocks for the SDK itself; test Citnega integration paths with real objects.

```python
# tests/unit/adapters/test_your_framework.py

from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from citnega.packages.protocol.interfaces.adapter import AdapterConfig
from citnega.packages.protocol.models.sessions import Session, SessionConfig


def _make_session(session_id: str = "s1", model_id: str = "test-model") -> Session:
    cfg = SessionConfig(
        session_id=session_id,
        name="test",
        framework="your_framework",
        default_model_id=model_id,
    )
    now = datetime.now(tz=UTC)
    return Session(config=cfg, created_at=now, last_active_at=now)


@pytest.mark.asyncio
async def test_adapter_initializes(tmp_path) -> None:
    from citnega.packages.adapters.your_framework.adapter import YourFrameworkAdapter
    from citnega.packages.storage.path_resolver import PathResolver

    adapter = YourFrameworkAdapter(PathResolver(app_home=tmp_path))
    await adapter.initialize(AdapterConfig(framework_name="your_framework", default_model_id="m1"))
    assert adapter._initialized is True


@pytest.mark.asyncio
async def test_create_runner_returns_runner(tmp_path) -> None:
    from citnega.packages.adapters.your_framework.adapter import YourFrameworkAdapter
    from citnega.packages.adapters.your_framework.runner import YourRunner
    from citnega.packages.storage.path_resolver import PathResolver

    adapter = YourFrameworkAdapter(PathResolver(app_home=tmp_path))
    await adapter.initialize(AdapterConfig(framework_name="your_framework", default_model_id="m1"))
    session = _make_session()
    runner = await adapter.create_runner(session, callables=[], model_gateway=None)
    assert isinstance(runner, YourRunner)


@pytest.mark.asyncio
async def test_pause_blocks_next_turn(tmp_path) -> None:
    from citnega.packages.adapters.your_framework.adapter import YourFrameworkAdapter
    from citnega.packages.storage.path_resolver import PathResolver

    adapter = YourFrameworkAdapter(PathResolver(app_home=tmp_path))
    await adapter.initialize(AdapterConfig(framework_name="your_framework", default_model_id="m1"))
    session = _make_session()
    runner = await adapter.create_runner(session, callables=[], model_gateway=None)

    await runner.pause("run-1")
    with pytest.raises(RuntimeError, match="paused"):
        context = MagicMock()
        context.run_id = "run-2"
        context.total_tokens = 0
        context.metadata = {}
        await runner.run_turn("hello", context, asyncio.Queue())


@pytest.mark.asyncio
async def test_checkpoint_roundtrip(tmp_path) -> None:
    from citnega.packages.adapters.your_framework.adapter import YourFrameworkAdapter
    from citnega.packages.storage.path_resolver import PathResolver

    adapter = YourFrameworkAdapter(PathResolver(app_home=tmp_path))
    await adapter.initialize(AdapterConfig(framework_name="your_framework", default_model_id="m1"))
    session = _make_session()
    runner = await adapter.create_runner(session, callables=[], model_gateway=None)
    runner._history = [{"role": "user", "content": "hello"}]

    meta = await runner.save_checkpoint("run-1")
    assert meta.checkpoint_id
    assert meta.size_bytes > 0

    runner._history = []
    await runner.restore_checkpoint(meta.checkpoint_id)
    assert len(runner._history) == 1
```

---

## Part 9 — Common Pitfalls

| Mistake | Effect | Fix |
|---------|--------|-----|
| `import your_sdk` at top of `adapter.py` or `runner.py` | App fails to start without SDK | Import inside `_get_sdk_client()`, `_do_initialize()`, or `create_tool()` only |
| Raising from `_fn(**kwargs)` tool wrapper | Uncaught exception escapes the tool call loop | Let `BaseCallable.invoke()` catch — it never raises; check `result.error` |
| Returning SDK objects from `_do_save_checkpoint` | `json.dumps` fails at checkpoint time | Reduce all state to plain dicts/lists/strings/ints before returning |
| Never checking `_token.is_cancelled()` | `adapter.shutdown()` hangs on stuck stream | Check after every `await` in `_do_run_turn`'s streaming loop |
| Building SDK agent in `_do_initialize` | Agent built before any session exists | Build lazily in `_get_sdk_client()` on first `_do_run_turn` call |
| Using `model_gateway` to call your SDK's model | Wrong abstraction — that is Citnega's internal model routing | Build your SDK model object in `model_resolver.py`, pass to runner constructor |
| Calling `event_queue.put()` (blocking) | Deadlocks if queue is full | Use `event_queue.put_nowait()` wrapped in `contextlib.suppress(asyncio.QueueFull)` |
| Forgetting `super().__init__()` in runner | `_token`, `_paused`, `_serializer` not initialized | Always call `super().__init__(session, cancellation_token, checkpoint_serializer)` |

---

## Part 10 — Implementation Checklist

```
adapter.py
  [ ] Inherits BaseFrameworkAdapter
  [ ] framework_name returns unique lowercase string matching settings value
  [ ] _do_initialize: no SDK imports; log only
  [ ] create_runner: calls self._new_cancellation_token()
  [ ] create_runner: builds CheckpointSerializer with correct checkpoint_dir
  [ ] callable_factory: lazy-init, returns factory instance
  [ ] _do_shutdown: releases SDK-level resources if any

runner.py
  [ ] Inherits BaseFrameworkRunner
  [ ] super().__init__(session, cancellation_token, checkpoint_serializer) called
  [ ] SDK client/agent built lazily in _get_sdk_client() or equivalent
  [ ] _do_run_turn: polls self._token.is_cancelled() inside streaming loop
  [ ] _do_run_turn: emits TokenEvent to event_queue for every text chunk
  [ ] _do_run_turn: uses contextlib.suppress(asyncio.QueueFull) around put_nowait
  [ ] _do_run_turn: returns context.run_id
  [ ] _do_pause / _do_resume: save/restore state; log with run_id
  [ ] _do_cancel: clears history and in-flight state; logs
  [ ] _do_get_state_snapshot: returns RunState enum
  [ ] _do_save_checkpoint: returns JSON-serializable dict only (no SDK objects)
  [ ] _do_restore_checkpoint: rebuilds state from checkpoint dict

callable_factory.py
  [ ] Inherits BaseCallableFactory
  [ ] create_tool: returns SDK-native representation (or descriptor dict)
  [ ] create_specialist: same pattern
  [ ] create_core_agent: same pattern

model_resolver.py
  [ ] SDK model class imported ONLY in this file
  [ ] ImportError raised with pip install hint when SDK missing
  [ ] Handles explicit prefix, model-registry lookup, and pass-through

bootstrap.py
  [ ] One elif block added to _select_adapter()

pyproject.toml
  [ ] One entry in [project.optional-dependencies]

tests/unit/adapters/test_your_framework.py
  [ ] Adapter initializes
  [ ] create_runner returns correct runner type
  [ ] Pause blocks next run_turn
  [ ] Checkpoint save/restore roundtrip
  [ ] SDK mocked so test runs without SDK installed
```
