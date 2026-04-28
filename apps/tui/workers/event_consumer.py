"""
EventConsumerWorker — Textual Worker that drains the EventEmitter queue.

Runs in a background task (Textual's worker thread pool is async-capable).
For each canonical event it receives, it posts a corresponding Textual
message to the App so that the main thread can update widgets safely.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING

from textual.message import Message

from citnega.packages.protocol.events import (
    ApprovalRequestEvent,
    CallableEndEvent,
    CallableStartEvent,
    CanonicalEvent,
    ModeAutoSwitchedEvent,
    RunCompleteEvent,
    RunStateEvent,
    ThinkingEvent,
    TokenEvent,
)

if TYPE_CHECKING:
    from textual.app import App

# ── Textual messages emitted to the App ───────────────────────────────────────


class EventReceived(Message):
    """Generic wrapper — carries any canonical event to the App."""

    def __init__(self, event: CanonicalEvent) -> None:
        super().__init__()
        self.event = event


class RunStarted(Message):
    """Emitted when the first RunStateEvent (PENDING→CONTEXT_ASSEMBLING) arrives."""

    def __init__(self, run_id: str) -> None:
        super().__init__()
        self.run_id = run_id


class RunFinished(Message):
    """Emitted when RunCompleteEvent arrives."""

    def __init__(self, run_id: str, final_state: str) -> None:
        super().__init__()
        self.run_id = run_id
        self.final_state = final_state


class TokenReceived(Message):
    """Emitted for each streaming token."""

    def __init__(self, run_id: str, token: str) -> None:
        super().__init__()
        self.run_id = run_id
        self.token = token


class ToolCallStarted(Message):
    """Emitted when a callable starts executing."""

    def __init__(
        self,
        run_id: str,
        callable_name: str,
        event_id: str,
        input_summary: str = "",
        callable_type: str = "tool",
    ) -> None:
        super().__init__()
        self.run_id = run_id
        self.callable_name = callable_name
        self.event_id = event_id
        self.input_summary = input_summary
        self.callable_type = callable_type  # "tool" | "specialist" | "core" | …


class ToolCallFinished(Message):
    """Emitted when a callable finishes."""

    def __init__(
        self,
        run_id: str,
        callable_name: str,
        success: bool,
        output_summary: str,
        callable_type: str = "tool",
    ) -> None:
        super().__init__()
        self.run_id = run_id
        self.callable_name = callable_name
        self.success = success
        self.output_summary = output_summary
        self.callable_type = callable_type


class ThinkingReceived(Message):
    """Emitted for each reasoning token inside a <think>…</think> block."""

    def __init__(self, run_id: str, token: str, is_final: bool = False) -> None:
        super().__init__()
        self.run_id = run_id
        self.token = token
        self.is_final = is_final


class ApprovalRequested(Message):
    """Emitted when a tool execution needs user approval."""

    def __init__(
        self,
        run_id: str,
        approval_id: str,
        callable_name: str,
        input_summary: str,
    ) -> None:
        super().__init__()
        self.run_id = run_id
        self.approval_id = approval_id
        self.callable_name = callable_name
        self.input_summary = input_summary


class RunPhaseChanged(Message):
    """Emitted on every RunState transition — used to update the UI phase label."""

    def __init__(self, run_id: str, phase: str) -> None:
        super().__init__()
        self.run_id = run_id
        self.phase = phase  # e.g. "context_assembling", "executing", "completed"


class ModeAutoSwitched(Message):
    """Emitted when the runner overrides the session mode for a single turn."""

    def __init__(self, run_id: str, from_mode: str, to_mode: str, is_autonomous: bool) -> None:
        super().__init__()
        self.run_id = run_id
        self.from_mode = from_mode
        self.to_mode = to_mode
        self.is_autonomous = is_autonomous


# ── Worker ────────────────────────────────────────────────────────────────────


class EventConsumerWorker:
    """
    Drains the EventEmitter queue for a given run_id and posts Textual
    messages to the parent App.

    Usage::

        worker = EventConsumerWorker(app, service, run_id)
        worker.start()     # schedules as asyncio task on Textual event loop
        await worker.stop()
    """

    def __init__(
        self,
        app: App,
        service: object,  # ApplicationService
        run_id: str,
    ) -> None:
        self._app = app
        self._service = service
        self._run_id = run_id
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        """Schedule the drain loop on the current event loop."""
        self._task = asyncio.get_running_loop().create_task(
            self._drain(), name=f"event-consumer-{self._run_id[:8]}"
        )

    async def stop(self) -> None:
        """Cancel and wait for the drain task to finish."""
        if self._task and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(TimeoutError, asyncio.CancelledError):
                await asyncio.wait_for(asyncio.shield(self._task), timeout=2.0)

    async def _drain(self) -> None:
        """Consume events until RunCompleteEvent or task cancellation."""
        completed = False
        try:
            async for event in self._service.stream_events(self._run_id):
                self._dispatch(event)
                if isinstance(event, RunCompleteEvent):
                    completed = True
                    break
        except asyncio.CancelledError:
            return
        except Exception as exc:
            user_msg = getattr(exc, "user_message", "") or str(exc)
            self._app.notify(user_msg, severity="error", timeout=8)
            self._app.post_message(RunFinished(self._run_id, f"error: {exc}"))
            return

        # Stream ended without a RunCompleteEvent (e.g. per-event timeout fired).
        # Always finalize the UI so the StreamingBlock is resolved and the input
        # box re-enabled — without this the TUI appears frozen.
        if not completed:
            self._app.post_message(RunFinished(self._run_id, "completed"))

    def _dispatch(self, event: CanonicalEvent) -> None:
        """Translate a canonical event into one or more Textual messages."""
        app = self._app

        if isinstance(event, ThinkingEvent):
            app.post_message(ThinkingReceived(self._run_id, event.token, event.is_final))

        elif isinstance(event, TokenEvent):
            app.post_message(TokenReceived(self._run_id, event.token))

        elif isinstance(event, RunStateEvent):
            if event.from_state.value == "pending":
                app.post_message(RunStarted(self._run_id))
            app.post_message(RunPhaseChanged(self._run_id, event.to_state.value))

        elif isinstance(event, RunCompleteEvent):
            app.post_message(RunFinished(self._run_id, event.final_state.value))

        elif isinstance(event, CallableStartEvent):
            ct = event.callable_type.value if event.callable_type is not None else "tool"
            app.post_message(
                ToolCallStarted(
                    self._run_id,
                    event.callable_name or "",
                    event.event_id,
                    event.input_summary,
                    callable_type=ct,
                )
            )

        elif isinstance(event, CallableEndEvent):
            ct = event.callable_type.value if event.callable_type is not None else "tool"
            app.post_message(
                ToolCallFinished(
                    self._run_id,
                    event.callable_name or "",
                    success=event.error_code is None,
                    output_summary=event.output_summary or "",
                    callable_type=ct,
                )
            )

        elif isinstance(event, ApprovalRequestEvent):
            app.post_message(
                ApprovalRequested(
                    self._run_id,
                    event.approval_id,
                    event.callable_name,
                    event.input_summary,
                )
            )

        elif isinstance(event, ModeAutoSwitchedEvent):
            app.post_message(
                ModeAutoSwitched(
                    self._run_id,
                    from_mode=event.from_mode,
                    to_mode=event.to_mode,
                    is_autonomous=event.is_autonomous,
                )
            )

        # All events are also posted as generic EventReceived for extensibility
        app.post_message(EventReceived(event))
