"""
CrewAIRunner — executes turns using CrewAI.

All ``crewai`` imports are confined here.

CrewAI integration strategy:
  1. Build a Crew with one Agent + all registered tools on first use.
  2. Run each turn via ``crew.kickoff_async()``.
  3. Emit the final assistant text as a single TokenEvent.
  4. Checkpoint: serialize the last crew output and task description.
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


class CrewAIRunner(BaseFrameworkRunner):
    """IFrameworkRunner backed by CrewAI."""

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
        self._last_output: str = ""
        self._last_task: str = ""

    def _build_crew(self, task_description: str) -> Any:
        """Lazy-build a CrewAI Crew for the given task."""
        try:
            from crewai import Agent, Crew, Process, Task  # type: ignore[import]
            from crewai.tools import BaseTool as CrewBaseTool  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "crewai not installed. Install with: uv add 'citnega[crewai]'"
            ) from exc

        # Build CrewAI tools from Citnega callables
        tools = []
        for c in self._callables:

            def _make_crew_tool(cbl: IInvocable) -> Any:
                class _CitnegaTool(CrewBaseTool):
                    name: str = cbl.name
                    description: str = cbl.description

                    def _run(self_, **kwargs: object) -> str:
                        # CrewAI calls _run synchronously; bridge to async via asyncio
                        import asyncio as _asyncio

                        from citnega.packages.protocol.callables.context import CallContext

                        ctx = CallContext(
                            session_id=self._session.config.session_id,
                            run_id=self._current_run_id or "crew-direct",
                            turn_id="crew-turn",
                            session_config=self._session.config,
                        )
                        try:
                            loop = _asyncio.get_event_loop()
                        except RuntimeError:
                            loop = _asyncio.new_event_loop()

                        result = loop.run_until_complete(
                            cbl.invoke(cbl.input_schema.model_validate(kwargs), ctx)
                        )
                        if result.output:
                            return result.output.model_dump_json()
                        return str(result.error) if result.error else ""

                return _CitnegaTool()

            tools.append(_make_crew_tool(c))

        agent = Agent(
            role="General Assistant",
            goal="Complete the given task accurately.",
            backstory="You are a helpful AI assistant.",
            tools=tools,
            llm=self._model_id,
            verbose=False,
        )
        task = Task(
            description=task_description,
            expected_output="A comprehensive response to the user request.",
            agent=agent,
        )
        crew = Crew(
            agents=[agent],
            tasks=[task],
            process=Process.sequential,
            verbose=False,
        )
        return crew

    async def _do_run_turn(
        self,
        user_input: str,
        context: ContextObject,
        event_queue: asyncio.Queue[CanonicalEvent],
    ) -> str:
        self._last_task = user_input
        crew = self._build_crew(user_input)
        session_id = self._session.config.session_id

        # CrewAI kickoff_async returns the final result
        result = await crew.kickoff_async(inputs={})

        if self._token.is_cancelled():
            raise asyncio.CancelledError("CrewAI runner cancelled")

        output_text = str(result) if result else ""
        self._last_output = output_text

        if output_text:
            with contextlib.suppress(asyncio.QueueFull):
                event_queue.put_nowait(
                    TokenEvent(
                        session_id=session_id,
                        run_id=context.run_id,
                        turn_id=context.run_id,
                        token=output_text,
                        finish_reason="stop",
                    )
                )

        return context.run_id

    async def _do_pause(self, run_id: str) -> None:
        runtime_logger.info("crewai_runner_paused", run_id=run_id)

    async def _do_resume(self, run_id: str) -> None:
        runtime_logger.info("crewai_runner_resumed", run_id=run_id)

    async def _do_cancel(self, run_id: str) -> None:
        runtime_logger.info("crewai_runner_cancelled", run_id=run_id)

    async def _do_get_state_snapshot(self) -> RunState:
        return RunState.EXECUTING if not self._token.is_cancelled() else RunState.CANCELLED

    async def _do_save_checkpoint(self, run_id: str) -> dict[str, object]:
        return {
            "last_output": self._last_output,
            "last_task": self._last_task,
            "model_id": self._model_id,
            "session_id": self._session.config.session_id,
        }

    async def _do_restore_checkpoint(self, framework_state: dict[str, object]) -> None:
        self._last_output = str(framework_state.get("last_output", ""))
        self._last_task = str(framework_state.get("last_task", ""))
