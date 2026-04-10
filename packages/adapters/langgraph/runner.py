"""
LangGraphRunner — executes turns using LangGraph ReAct agent.

All ``langgraph`` / ``langchain_core`` imports are confined here.

LangGraph integration strategy:
  1. Build a ReAct graph with all registered tools on first use.
  2. Run each turn via ``graph.astream()`` collecting token + tool events.
  3. Emit canonical events (TokenEvent, CallableStartEvent, etc.) to queue.
  4. Checkpoint: serialize LangGraph state dict.
"""

from __future__ import annotations

import asyncio
from typing import Any

from citnega.packages.adapters.base.base_runner import BaseFrameworkRunner
from citnega.packages.adapters.base.cancellation import CancellationToken
from citnega.packages.adapters.base.checkpoint_serializer import CheckpointSerializer
from citnega.packages.adapters.base.event_translator import EventTranslator
from citnega.packages.observability.logging_setup import runtime_logger
from citnega.packages.protocol.callables.interfaces import IInvocable
from citnega.packages.protocol.events import CanonicalEvent
from citnega.packages.protocol.events.streaming import TokenEvent
from citnega.packages.protocol.models.context import ContextObject
from citnega.packages.protocol.models.runs import RunState
from citnega.packages.protocol.models.sessions import Session


class LangGraphRunner(BaseFrameworkRunner):
    """IFrameworkRunner backed by LangGraph."""

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
        self._graph: Any = None
        self._graph_state: dict[str, object] = {}

    def _build_graph(self) -> Any:
        """Lazy-build the LangGraph ReAct graph."""
        if self._graph is not None:
            return self._graph
        try:
            from langchain_core.tools import StructuredTool  # type: ignore[import]
            from langgraph.prebuilt import create_react_agent  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "langgraph / langchain_core not installed. "
                "Install with: uv add 'citnega[langgraph]'"
            ) from exc

        tools = []
        for c in self._callables:
            def _make_tool(cbl: IInvocable) -> Any:
                async def _fn(**kwargs: object) -> dict[str, object]:
                    from citnega.packages.protocol.callables.context import CallContext
                    ctx = CallContext(
                        session_id=self._session.config.session_id,
                        run_id=self._current_run_id or "lg-direct",
                        turn_id="lg-turn",
                        session_config=self._session.config,
                    )
                    result = await cbl.invoke(cbl.input_schema.model_validate(kwargs), ctx)
                    if result.output:
                        return result.output.model_dump()
                    return {"error": str(result.error) if result.error else "no output"}
                return StructuredTool.from_function(
                    coroutine=_fn,
                    name=cbl.name,
                    description=cbl.description,
                    args_schema=cbl.input_schema,
                )
            tools.append(_make_tool(c))

        # Use a simple dict-based model that accepts any model_id string
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI  # type: ignore[import]
            llm = ChatGoogleGenerativeAI(model=self._model_id)
        except ImportError:
            try:
                from langchain_openai import ChatOpenAI  # type: ignore[import]
                llm = ChatOpenAI(model=self._model_id)
            except ImportError:
                # Fallback: create a no-op LLM for testing
                from langchain_core.language_models.fake import FakeListChatModel  # type: ignore[import]
                llm = FakeListChatModel(responses=["No LLM installed."])

        self._graph = create_react_agent(llm, tools=tools)
        return self._graph

    async def _do_run_turn(
        self,
        user_input: str,
        context: ContextObject,
        event_queue: asyncio.Queue[CanonicalEvent],
    ) -> str:
        graph = self._build_graph()
        session_id = self._session.config.session_id

        # Build the initial message list
        messages = [{"role": "user", "content": user_input}]

        async for chunk in graph.astream(
            {"messages": messages},
            stream_mode="values",
        ):
            if self._token.is_cancelled():
                raise asyncio.CancelledError("LangGraph runner cancelled")

            # Extract assistant tokens from the chunk
            for msg in chunk.get("messages", []):
                role = getattr(msg, "type", None) or getattr(msg, "role", "")
                if role in ("ai", "assistant"):
                    content = getattr(msg, "content", "")
                    if isinstance(content, str) and content:
                        try:
                            event_queue.put_nowait(TokenEvent(
                                session_id=session_id,
                                run_id=context.run_id,
                                turn_id=context.run_id,
                                token=content,
                                finish_reason=None,
                            ))
                        except asyncio.QueueFull:
                            pass

            # Persist state for checkpointing
            self._graph_state = {"messages": [
                {"role": getattr(m, "type", "unknown"), "content": getattr(m, "content", "")}
                for m in chunk.get("messages", [])
            ]}

        return context.run_id

    async def _do_pause(self, run_id: str) -> None:
        runtime_logger.info("langgraph_runner_paused", run_id=run_id)

    async def _do_resume(self, run_id: str) -> None:
        runtime_logger.info("langgraph_runner_resumed", run_id=run_id)

    async def _do_cancel(self, run_id: str) -> None:
        runtime_logger.info("langgraph_runner_cancelled", run_id=run_id)

    async def _do_get_state_snapshot(self) -> RunState:
        return RunState.EXECUTING if not self._token.is_cancelled() else RunState.CANCELLED

    async def _do_save_checkpoint(self, run_id: str) -> dict[str, object]:
        return {
            "graph_state": self._graph_state,
            "model_id": self._model_id,
            "session_id": self._session.config.session_id,
        }

    async def _do_restore_checkpoint(
        self, framework_state: dict[str, object]
    ) -> None:
        self._graph_state = framework_state.get("graph_state", {})  # type: ignore[assignment]
