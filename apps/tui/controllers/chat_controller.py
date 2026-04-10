"""
ChatController — translates canonical events into widget mutations.

The controller:
  1. Handles user input (slash commands → routed; plain text → service call)
  2. On run start, mounts a StreamingBlock and starts an EventConsumerWorker
  3. Routes incoming TUI messages to the correct widget update methods
  4. Manages the slash command popup lifecycle
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.containers import VerticalScroll

from citnega.apps.tui.widgets.approval_block import ApprovalBlock
from citnega.apps.tui.widgets.message_block import MessageBlock
from citnega.apps.tui.widgets.plan_approval_block import PlanApprovalBlock
from citnega.apps.tui.widgets.streaming_block import StreamingBlock
from citnega.apps.tui.widgets.thinking_block import ThinkingBlock
from citnega.apps.tui.widgets.tool_call_block import ToolCallBlock
from citnega.apps.tui.workers.event_consumer import (
    ApprovalRequested,
    RunFinished,
    RunStarted,
    ThinkingReceived,
    ToolCallFinished,
    ToolCallStarted,
    TokenReceived,
    EventConsumerWorker,
)

if TYPE_CHECKING:
    from textual.app import App
    from citnega.packages.runtime.app_service import ApplicationService


class ChatController:
    """
    Mediator between the TUI (App + widgets) and the ApplicationService.

    Instantiated once by CitnegaApp.on_mount().
    """

    def __init__(
        self,
        app: "App",
        service: "ApplicationService",
        session_id: str,
    ) -> None:
        self._app        = app
        self._service    = service
        self._session_id = session_id

        # Active streaming block (one at a time — sequential turns)
        self._streaming_block: StreamingBlock | None = None
        # Active thinking block for current turn (created on first ThinkingReceived)
        self._thinking_block: ThinkingBlock | None = None
        # Mapping callable_name → open ToolCallBlock
        self._open_tool_blocks: dict[str, ToolCallBlock] = {}
        # Active event consumer worker
        self._consumer: EventConsumerWorker | None = None
        # Slash command registry
        self._slash_commands = _build_slash_registry(app, service, session_id, self)
        # Popup widget reference
        self._popup = None
        # Plan mode state machine
        # None → awaiting_approval → executing → None
        self._plan_state: str | None = None

    # ── User input routing ─────────────────────────────────────────────────────

    async def handle_user_input(self, text: str) -> None:
        """
        Route user input:
          - Starts with "/" → slash command
          - Mode is "plan" and not awaiting approval → plan draft phase
          - Otherwise → normal turn
        """
        if text.startswith("/"):
            await self._handle_slash(text)
            return

        if self._plan_state == "awaiting_approval":
            await self._append_message(
                "system",
                "A plan is waiting for your approval above. "
                "Click ▶ Proceed to execute it or ✗ Cancel to discard.",
            )
            return

        mode = self._service.get_session_mode(self._session_id)
        if mode == "plan" and self._plan_state is None:
            await self._start_plan_draft(text)
        else:
            await self._start_turn(text)

    async def _start_plan_draft(self, text: str) -> None:
        """Phase 1 of plan mode: generate plan only, then ask for approval."""
        from citnega.packages.runtime.session_modes import PlanMode  # noqa: PLC0415
        self._plan_state = "awaiting_approval"
        self._service.set_session_plan_phase(self._session_id, PlanMode.PHASE_DRAFT)
        await self._append_message("user", text)
        await self._run_turn(text)

    async def _start_turn(self, text: str) -> None:
        """Normal (non-plan) turn: show user message and stream response."""
        await self._append_message("user", text)
        await self._run_turn(text)

    async def _run_turn(self, text: str) -> None:
        """Shared turn execution: start service run + mount StreamingBlock."""
        try:
            run_id = await self._service.run_turn(self._session_id, text)
        except Exception as exc:
            await self._append_message("system", f"Error starting turn: {exc}")
            return

        self._streaming_block = StreamingBlock()
        scroll = self._app.screen.query_one("#chat-scroll", VerticalScroll)
        await scroll.mount(self._streaming_block)
        self._app.call_after_refresh(scroll.scroll_end)

        self._consumer = EventConsumerWorker(self._app, self._service, run_id)
        self._consumer.start()

    async def on_plan_approval_block_resolved(
        self, message: PlanApprovalBlock.Resolved
    ) -> None:
        """Called when the user clicks Proceed or Cancel on the plan block."""
        from citnega.packages.runtime.session_modes import PlanMode  # noqa: PLC0415
        if message.approved:
            self._plan_state = "executing"
            self._service.set_session_plan_phase(
                self._session_id, PlanMode.PHASE_EXECUTE
            )
            await self._run_turn("Execute the plan above step by step.")
        else:
            self._plan_state = None
            self._service.set_session_plan_phase(
                self._session_id, PlanMode.PHASE_DRAFT
            )
            await self._append_message(
                "system", "Plan cancelled. You can refine your request."
            )

    # ── TUI message handlers (called by App.on_*) ──────────────────────────────

    async def on_thinking_received(self, message: ThinkingReceived) -> None:
        """Create the ThinkingBlock on first token; stream into it thereafter."""
        if self._thinking_block is None:
            self._thinking_block = ThinkingBlock()
            scroll = self._app.screen.query_one("#chat-scroll", VerticalScroll)
            # Mount BEFORE the StreamingBlock so thinking appears above the response
            if self._streaming_block is not None:
                await scroll.mount(self._thinking_block, before=self._streaming_block)
            else:
                await scroll.mount(self._thinking_block)
            self._app.call_after_refresh(scroll.scroll_end)

        self._thinking_block.append_token(message.token)

        if message.is_final:
            self._thinking_block.finalize()
            self._thinking_block = None

    async def on_token_received(self, message: TokenReceived) -> None:
        # If a thinking block is still open when response tokens arrive, close it
        if self._thinking_block is not None:
            self._thinking_block.finalize()
            self._thinking_block = None

        if self._streaming_block is not None:
            self._streaming_block.append_token(message.token)
            # Keep the scroll pinned to the bottom as tokens arrive
            try:
                scroll = self._app.screen.query_one("#chat-scroll", VerticalScroll)
                scroll.scroll_end(animate=False)
            except Exception:
                pass

    async def on_run_finished(self, message: RunFinished) -> None:
        # Finalize any still-open thinking block (stream ended without </think>)
        if self._thinking_block is not None:
            self._thinking_block.finalize()
            self._thinking_block = None

        if self._streaming_block is not None:
            await self._streaming_block.finalize()
            self._streaming_block = None

        # Update status bar
        from citnega.apps.tui.widgets.status_bar import StatusBar  # noqa: PLC0415
        status = self._app.screen.query_one(StatusBar)
        status.run_state = "idle"

        if message.final_state not in ("completed", "cancelled"):
            await self._append_message(
                "system",
                f"Run ended with state: {message.final_state}",
            )

        # After plan draft completes, show the approval block
        mode = self._service.get_session_mode(self._session_id)
        if mode == "plan" and self._plan_state == "awaiting_approval":
            block = PlanApprovalBlock()
            scroll = self._app.screen.query_one("#chat-scroll", VerticalScroll)
            await scroll.mount(block)
            self._app.call_after_refresh(scroll.scroll_end)

        # After execution completes, reset plan state machine
        elif self._plan_state == "executing":
            self._plan_state = None

    async def on_tool_call_started(self, message: ToolCallStarted) -> None:
        block = ToolCallBlock(
            tool_name=message.callable_name,
            input_summary=f"event_id: {message.event_id[:8]}",
        )
        self._open_tool_blocks[message.callable_name] = block
        scroll = self._app.screen.query_one("#chat-scroll", VerticalScroll)
        await scroll.mount(block)
        self._app.call_after_refresh(scroll.scroll_end)

    async def on_tool_call_finished(self, message: ToolCallFinished) -> None:
        block = self._open_tool_blocks.pop(message.callable_name, None)
        if block is None:
            return
        if message.success:
            block.set_result(message.output_summary)
        else:
            block.set_error(message.output_summary)

    async def on_approval_requested(self, message: ApprovalRequested) -> None:
        block = ApprovalBlock(
            approval_id=message.approval_id,
            callable_name=message.callable_name,
            input_summary=message.input_summary,
        )
        scroll = self._app.screen.query_one("#chat-scroll", VerticalScroll)
        await scroll.mount(block)
        self._app.call_after_refresh(scroll.scroll_end)

    async def on_approval_block_resolved(self, message: ApprovalBlock.Resolved) -> None:
        try:
            await self._service.respond_to_approval(
                message.approval_id,
                approved=message.approved,
            )
        except Exception as exc:
            await self._append_message("system", f"Approval error: {exc}")

    def on_run_started(self, message: RunStarted) -> None:
        from citnega.apps.tui.widgets.status_bar import StatusBar  # noqa: PLC0415
        status = self._app.screen.query_one(StatusBar)
        status.run_state = "running"

    # ── Popup ──────────────────────────────────────────────────────────────────

    def toggle_slash_popup(self) -> None:
        if self._popup is not None:
            self.dismiss_popup()
        else:
            self._show_slash_popup()

    def dismiss_popup(self) -> None:
        if self._popup is not None:
            try:
                self._popup.remove()
            except Exception:
                pass
            self._popup = None

    def _show_slash_popup(self) -> None:
        from citnega.apps.tui.widgets.slash_popup import SlashCommandPopup  # noqa: PLC0415
        cmds = list(self._slash_commands.keys())
        popup = SlashCommandPopup(commands=cmds)
        self._popup = popup
        self._app.mount(popup)

    # ── Helpers ────────────────────────────────────────────────────────────────

    async def _append_message(self, role: str, content: str) -> None:
        block = MessageBlock(role=role, content=content)
        scroll = self._app.screen.query_one("#chat-scroll", VerticalScroll)
        # Remove empty hint if present
        try:
            hint = scroll.query_one("#empty-hint")
            await hint.remove()
        except Exception:
            pass
        await scroll.mount(block)
        self._app.call_after_refresh(scroll.scroll_end)

    async def _handle_slash(self, text: str) -> None:
        parts = text[1:].split()
        cmd_name = parts[0].lower() if parts else ""
        args = parts[1:]
        handler = self._slash_commands.get(cmd_name)
        if handler is None:
            await self._append_message(
                "system",
                f"Unknown command /{cmd_name}. Type /help for available commands."
            )
            return
        await handler.execute(args, self)

    async def shutdown(self) -> None:
        """Cancel background consumer if running."""
        if self._consumer is not None:
            await self._consumer.stop()


# ── Slash command registry factory ────────────────────────────────────────────

def _build_slash_registry(app, service, session_id, controller):
    from citnega.apps.tui.slash_commands.builtin import (  # noqa: PLC0415
        AgentCommand,
        ApproveCommand,
        CancelCommand,
        ClearCommand,
        CompactCommand,
        HelpCommand,
        ModelCommand,
        ModeCommand,
        NewSessionCommand,
        SessionsCommand,
        ThinkCommand,
    )

    cmds = [
        HelpCommand(),
        AgentCommand(service=service),
        ApproveCommand(service=service),
        CancelCommand(service=service),
        ClearCommand(),
        CompactCommand(service=service),
        ModelCommand(service=service),
        ModeCommand(service=service),
        NewSessionCommand(service=service),
        SessionsCommand(service=service),
        ThinkCommand(service=service),
    ]
    return {cmd.name: cmd for cmd in cmds}
