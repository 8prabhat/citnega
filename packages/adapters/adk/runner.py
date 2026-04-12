"""
ADK FrameworkRunner — executes turns using Google ADK.

All ``google.adk`` imports are confined here.

ADK integration strategy:
  1. On ``create_runner()``, build an ADK Agent with all registered tools.
  2. On each ``run_turn()``, create an ADK Runner, run the agent, and
     translate ADK events to CanonicalEvents via EventTranslator.
  3. Cancellation: poll CancellationToken between ADK streaming chunks.
  4. Checkpoints: serialize ADK session history as framework_state.
"""

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


class ADKRunner(BaseFrameworkRunner):
    """
    IFrameworkRunner backed by Google ADK.

    The runner holds a live ADK session per Citnega session.  Each call
    to ``run_turn()`` appends to that session's conversation history.
    """

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
        # ADK session history stored as list of turn dicts for checkpointing
        self._history: list[dict[str, object]] = []
        self._adk_runner: Any = None  # lazy-initialised on first run_turn

    def _resolve_adk_model(self) -> Any:
        """
        Return an ADK-compatible model reference.

        Resolution order:
        1. Already in LiteLLM format (``ollama/<model>``, ``litellm/<model>``) → LiteLlm
        2. Citnega model-registry ID (e.g. ``gemma4-27b-local``) with provider_type
           ``ollama`` → resolve to ``ollama/<model_name>`` via LiteLlm
        3. Anything else → pass through as a string (Gemini / Vertex native)
        """
        from citnega.packages.adapters.adk.model_resolver import resolve_adk_model_reference

        return resolve_adk_model_reference(self._model_id)

    @staticmethod
    def _make_lite_llm(model_str: str) -> Any:
        from citnega.packages.adapters.adk.model_resolver import make_lite_llm

        return make_lite_llm(model_str)

    def _get_adk_runner(self) -> Any:
        """Lazy-init: import ADK and build runner only when first needed."""
        if self._adk_runner is not None:
            return self._adk_runner
        try:
            # Late import — only available when google-adk is installed
            from google.adk.agents import LlmAgent  # type: ignore[import]
            from google.adk.runners import Runner  # type: ignore[import]
            from google.adk.sessions import InMemorySessionService  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "google-adk is not installed. Install with: uv add 'citnega[adk]'"
            ) from exc

        # Build tool wrappers — ADK expects callables as functions
        tools = []
        for c in self._callables:
            # We create a lightweight closure per callable
            def _make_fn(cbl: IInvocable) -> Any:
                async def _adk_tool_fn(**kwargs: object) -> dict[str, object]:
                    from citnega.packages.protocol.callables.context import CallContext

                    # Build a minimal CallContext for this invocation
                    ctx = CallContext(
                        session_id=self._session.config.session_id,
                        run_id=self._current_run_id or "adk-direct",
                        turn_id="adk-turn",
                        session_config=self._session.config,
                    )
                    result = await cbl.invoke(cbl.input_schema.model_validate(kwargs), ctx)
                    if result.output:
                        return result.output.model_dump()
                    if result.error:
                        return {"error": str(result.error)}
                    return {}

                _adk_tool_fn.__name__ = cbl.name
                _adk_tool_fn.__doc__ = cbl.description
                return _adk_tool_fn

            tools.append(_make_fn(c))

        session_service = InMemorySessionService()
        adk_model = self._resolve_adk_model()
        agent = LlmAgent(
            name=f"citnega_{self._session.config.session_id[:8]}",
            model=adk_model,
            tools=tools,
        )
        self._adk_runner = Runner(
            agent=agent,
            app_name="citnega",
            session_service=session_service,
        )
        return self._adk_runner

    async def _do_run_turn(
        self,
        user_input: str,
        context: ContextObject,
        event_queue: asyncio.Queue[CanonicalEvent],
    ) -> str:
        try:
            from google.genai.types import Content, Part  # type: ignore[import]
        except ImportError as exc:
            raise ImportError("google-adk not installed") from exc

        adk_runner = self._get_adk_runner()
        session_id = self._session.config.session_id
        message = Content(role="user", parts=[Part(text=user_input)])

        async for event in adk_runner.run_async(
            user_id=session_id,
            session_id=session_id,
            new_message=message,
        ):
            if self._token.is_cancelled():
                raise asyncio.CancelledError("ADK runner cancelled")

            # Emit token events for streaming text
            if hasattr(event, "content") and event.content:
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        with contextlib.suppress(asyncio.QueueFull):
                            event_queue.put_nowait(
                                TokenEvent(
                                    session_id=session_id,
                                    run_id=context.run_id,
                                    turn_id=context.run_id,
                                    token=part.text,
                                    finish_reason=None,
                                )
                            )

            # Record in history for checkpointing
            if hasattr(event, "content") and event.content:
                self._history.append(
                    {
                        "role": getattr(event.content, "role", "assistant"),
                        "text": "".join(getattr(p, "text", "") for p in event.content.parts),
                    }
                )

        return context.run_id

    async def _do_pause(self, run_id: str) -> None:
        # ADK does not have a native pause; set a flag and poll in _do_run_turn
        runtime_logger.info("adk_runner_paused", run_id=run_id)

    async def _do_resume(self, run_id: str) -> None:
        runtime_logger.info("adk_runner_resumed", run_id=run_id)

    async def _do_cancel(self, run_id: str) -> None:
        runtime_logger.info("adk_runner_cancelled", run_id=run_id)

    async def _do_get_state_snapshot(self) -> RunState:
        return RunState.EXECUTING if not self._token.is_cancelled() else RunState.CANCELLED

    async def _do_save_checkpoint(self, run_id: str) -> dict[str, object]:
        return {
            "history": self._history,
            "model_id": self._model_id,
            "session_id": self._session.config.session_id,
        }

    async def _do_restore_checkpoint(self, framework_state: dict[str, object]) -> None:
        self._history = framework_state.get("history", [])  # type: ignore[assignment]
