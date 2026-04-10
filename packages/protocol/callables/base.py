"""
BaseCallable and BaseCoreAgent — Template Method implementations.

BaseCallable.invoke() defines the canonical pre/post skeleton:
  validate → policy → emit start → _execute → catch → emit end → trace

Subclasses override only ``_execute()``. This is the DRY anchor for all
callable pre/post logic — no subclass duplicates tracing, policy checks,
or event emission.
"""

from __future__ import annotations

import time
from abc import abstractmethod
from typing import TYPE_CHECKING, AsyncIterator, Type

from pydantic import BaseModel

from citnega.packages.protocol.callables.context import CallContext
from citnega.packages.protocol.callables.interfaces import IOrchestrable, IStreamable
from citnega.packages.protocol.callables.results import InvokeResult, StreamChunk
from citnega.packages.protocol.callables.types import CallableMetadata, CallablePolicy, CallableType
from citnega.packages.shared.errors import CitnegaError, UnhandledCallableError

if TYPE_CHECKING:
    from citnega.packages.protocol.interfaces.events import IEventEmitter, ITracer
    from citnega.packages.protocol.interfaces.policy import IPolicyEnforcer
    from citnega.packages.protocol.interfaces.routing import IRoutingPolicy


class BaseCallable(IStreamable):
    """
    Concrete base for all tools and specialist agents.

    Subclasses must set class-level ``name``, ``description``,
    ``callable_type``, ``input_schema``, ``output_schema``, and ``policy``,
    then implement ``_execute()``.
    """

    name:          str
    description:   str
    callable_type: CallableType
    input_schema:  Type[BaseModel]
    output_schema: Type[BaseModel]
    policy:        CallablePolicy = CallablePolicy()

    def __init__(
        self,
        policy_enforcer: "IPolicyEnforcer",
        event_emitter: "IEventEmitter",
        tracer: "ITracer",
    ) -> None:
        self._policy_enforcer = policy_enforcer
        self._event_emitter   = event_emitter
        self._tracer          = tracer

    async def invoke(self, input: BaseModel, context: CallContext) -> InvokeResult:
        """
        Template method — the single canonical execution path for all callables.

        Steps:
          1. Validate input against input_schema.
          2. Enforce policy (raises CallablePolicyError on violation).
          3. Emit CallableStartEvent.
          4. Call _execute() — subclass implementation.
          5. Capture CitnegaError or wrap unknown exceptions.
          6. Emit CallableEndEvent.
          7. Trace the invocation.
          8. Return InvokeResult (never raises).
        """
        from citnega.packages.protocol.events.callable import (
            CallableEndEvent,
            CallableStartEvent,
        )

        validated = self.input_schema.model_validate(
            input.model_dump() if isinstance(input, BaseModel) else input
        )

        self._event_emitter.emit(
            CallableStartEvent.from_invocation(self, context)
        )

        start = time.monotonic()
        result: InvokeResult

        try:
            await self._policy_enforcer.enforce(self, validated, context)

            output = await self._policy_enforcer.run_with_timeout(
                self,
                self._execute(validated, context),
                context,
                self._event_emitter,
            )
            # Check output serialisation size against policy limit
            try:
                raw_bytes = len(output.model_dump_json().encode())
            except Exception:
                raw_bytes = 0
            await self._policy_enforcer.check_output_size(
                self, raw_bytes, context, self._event_emitter
            )
            result = InvokeResult.ok(
                name=self.name,
                callable_type=self.callable_type,
                output=output,
                duration_ms=int((time.monotonic() - start) * 1000),
            )
        except CitnegaError as exc:
            result = InvokeResult.from_error(
                name=self.name,
                callable_type=self.callable_type,
                error=exc,
                duration_ms=int((time.monotonic() - start) * 1000),
            )
        except Exception as exc:
            wrapped = UnhandledCallableError(str(exc), original=exc)
            result = InvokeResult.from_error(
                name=self.name,
                callable_type=self.callable_type,
                error=wrapped,
                duration_ms=int((time.monotonic() - start) * 1000),
            )
        finally:
            context.run_cleanups()

        self._event_emitter.emit(
            CallableEndEvent.from_result(result, context)
        )
        self._tracer.record(self, validated, result, context)

        return result

    @abstractmethod
    async def _execute(self, input: BaseModel, context: CallContext) -> BaseModel:
        """Subclasses implement the actual work here."""
        ...

    async def stream_invoke(
        self,
        input: BaseModel,
        context: CallContext,
    ) -> AsyncIterator[StreamChunk]:
        """
        Default streaming: run invoke(), yield one RESULT chunk + TERMINAL.

        Specialist agents and core agents override this to yield TOKEN chunks.
        """
        result = await self.invoke(input, context)
        yield StreamChunk.from_result(result)
        yield StreamChunk.terminal()

    def get_metadata(self) -> CallableMetadata:
        return CallableMetadata(
            name=self.name,
            description=self.description,
            callable_type=self.callable_type,
            input_schema_json=self.input_schema.model_json_schema(),
            output_schema_json=self.output_schema.model_json_schema(),
            policy=self.policy,
        )


class BaseCoreAgent(BaseCallable, IOrchestrable):
    """
    Base for all core agents (ConversationAgent, PlannerAgent).

    Adds sub-callable registration and routing policy support on top of
    BaseCallable's template method.
    """

    callable_type: CallableType = CallableType.CORE

    def __init__(self, *args: object, **kwargs: object) -> None:
        # Accept optional tool_registry as 4th positional or keyword arg
        # (AgentRegistry passes it uniformly; BaseCallable only takes 3 positional)
        tool_registry = kwargs.pop("tool_registry", None)
        if len(args) > 3:
            args, tool_registry = args[:3], args[3]
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._sub_callables: list[IStreamable] = []
        self._routing_policy: "IRoutingPolicy | None" = None
        self._tool_registry: dict = dict(tool_registry) if isinstance(tool_registry, dict) else {}

    def register_sub_callable(self, callable: IStreamable) -> None:  # type: ignore[override]
        self._sub_callables.append(callable)

    def list_sub_callables(self) -> list[IStreamable]:  # type: ignore[override]
        return list(self._sub_callables)

    def set_routing_policy(self, policy: "IRoutingPolicy") -> None:
        self._routing_policy = policy
