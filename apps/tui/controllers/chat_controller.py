"""
ChatController — translates canonical events into widget mutations.

The controller:
  1. Handles user input (slash commands → routed; plain text → service call)
  2. On run start, mounts a StreamingBlock and starts an EventConsumerWorker
  3. Routes incoming TUI messages to the correct widget update methods
  4. Manages the slash command popup lifecycle
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from textual.containers import VerticalScroll

from citnega.apps.tui.widgets.agent_call_block import AgentCallBlock
from citnega.apps.tui.widgets.approval_block import ApprovalBlock
from citnega.apps.tui.widgets.message_block import MessageBlock
from citnega.apps.tui.widgets.option_picker_block import OptionPickerBlock
from citnega.apps.tui.widgets.plan_approval_block import PlanApprovalBlock
from citnega.apps.tui.widgets.streaming_block import StreamingBlock
from citnega.apps.tui.widgets.thinking_block import ThinkingBlock
from citnega.apps.tui.widgets.tool_call_block import ToolCallBlock
from citnega.apps.tui.workers.event_consumer import (
    ApprovalRequested,
    EventConsumerWorker,
    RunFinished,
    RunPhaseChanged,
    RunStarted,
    ThinkingReceived,
    TokenReceived,
    ToolCallFinished,
    ToolCallStarted,
)
from citnega.packages.observability.logging_setup import runtime_logger as _logger

if TYPE_CHECKING:
    from textual.app import App

    from citnega.packages.protocol.interfaces.application_service import (
        IApplicationService as ApplicationService,
    )


class ChatController:
    """
    Mediator between the TUI (App + widgets) and the ApplicationService.

    Instantiated once by CitnegaApp.on_mount().
    """

    def __init__(
        self,
        app: App,
        service: ApplicationService,
        session_id: str,
    ) -> None:
        self._app = app
        self._service = service
        self._session_id = session_id

        # Active streaming block (one at a time — sequential turns)
        self._streaming_block: StreamingBlock | None = None
        # Thinking block currently streaming tokens (not yet finalized)
        self._thinking_block: ThinkingBlock | None = None
        # Last finalized thinking block — claimed by the next tool/agent call to map them visually
        self._last_thinking_block: ThinkingBlock | None = None
        # Mapping callable_name → open ToolCallBlock
        self._open_tool_blocks: dict[str, ToolCallBlock] = {}
        # Mapping callable_name → input_summary (captured on start, used on finish for persistence)
        self._tool_input_summaries: dict[str, str] = {}
        # Mapping callable_name → msg_count at tool start (before assistant msg is added).
        # Captured on ToolCallStarted so the race with add_message("assistant") doesn't affect
        # which conversation position the tool block gets assigned on session resume.
        self._tool_msg_counts: dict[str, int] = {}
        # Active event consumer worker
        self._consumer: EventConsumerWorker | None = None
        # Slash command registry
        self._slash_commands = _build_slash_registry(app, service, session_id, self)
        # Popup widget reference
        self._popup = None
        # Plan mode state machine
        # None → awaiting_approval → executing → None
        self._plan_state: str | None = None
        # Pending picker callbacks: widget_id → async callable(value, label)
        self._picker_callbacks: dict[str, object] = {}
        # Multi-step wizard intercept — set by workspace slash commands
        self._pending_wizard = None  # WizardState | None
        self._wizard_data: dict = {}

    # ── User input routing ─────────────────────────────────────────────────────

    async def handle_user_input(self, text: str) -> None:
        """
        Route user input:
          - Active wizard → consumed by wizard (multi-step free-text flows)
          - Starts with "/" → slash command
          - Mode is "plan" and not awaiting approval → plan draft phase
          - Otherwise → normal turn
        """
        try:
            await self._handle_user_input_inner(text)
        except Exception as exc:
            self._app.notify(f"Input error: {exc}", severity="error", timeout=8)

    async def _handle_user_input_inner(self, text: str) -> None:
        if self._pending_wizard is not None:
            wizard, self._pending_wizard = self._pending_wizard, None
            await wizard.on_input(text, self)
            return

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
        from citnega.packages.protocol.modes import PlanMode

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
            msg = getattr(exc, "user_message", "") or str(exc)
            await self._append_message("system", f"Error: {msg}")
            return

        try:
            self._streaming_block = StreamingBlock()
            scroll = self._app.screen.query_one("#chat-scroll", VerticalScroll)
            await scroll.mount(self._streaming_block)
            self._app.call_after_refresh(scroll.scroll_end)
        except Exception as exc:
            self._app.notify(
                f"UI error mounting response block: {exc}", severity="error", timeout=8
            )
            return

        self._consumer = EventConsumerWorker(self._app, self._service, run_id)
        self._consumer.start()

    async def on_plan_approval_block_resolved(self, message: PlanApprovalBlock.Resolved) -> None:
        """Called when the user clicks Proceed or Cancel on the plan block."""
        from citnega.packages.protocol.modes import PlanMode

        if message.approved:
            self._plan_state = "executing"
            self._service.set_session_plan_phase(self._session_id, PlanMode.PHASE_EXECUTE)
            await self._run_turn("Execute the plan above step by step.")
        else:
            self._plan_state = None
            self._service.set_session_plan_phase(self._session_id, PlanMode.PHASE_DRAFT)
            await self._append_message("system", "Plan cancelled. You can refine your request.")

    # ── TUI message handlers (called by App.on_*) ──────────────────────────────

    async def on_thinking_received(self, message: ThinkingReceived) -> None:
        """Create the ThinkingBlock on first token; stream into it thereafter.

        Each finalized thinking block is tracked in _last_thinking_block so
        the next tool/agent call can claim it visually (thinking → tool mapping).
        """
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
            self._last_thinking_block = self._thinking_block   # remember for tool mapping
            self._thinking_block = None

    async def on_token_received(self, message: TokenReceived) -> None:
        # If a thinking block is still open when response tokens arrive, close it
        if self._thinking_block is not None:
            self._thinking_block.finalize()
            self._last_thinking_block = self._thinking_block
            self._thinking_block = None
        # Response tokens following thinking are NOT tool calls — clear the mapping
        self._last_thinking_block = None

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
        self._last_thinking_block = None

        if self._streaming_block is not None:
            await self._streaming_block.finalize()
            self._streaming_block = None

        self._update_context_bar(state="idle")

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
        input_summary = message.input_summary or f"run:{message.run_id[:8]}"
        self._tool_input_summaries[message.callable_name] = input_summary
        # Capture msg_count NOW — before the assistant message is added — so that
        # the stored position is stable regardless of async ordering.
        try:
            n = len(self._service.get_conversation_messages(self._session_id))
        except Exception:
            n = 0
        self._tool_msg_counts[message.callable_name] = n

        # Claim the last finalized thinking block: connect it visually to THIS tool/agent call
        from_thinking = self._last_thinking_block is not None
        if self._last_thinking_block is not None:
            self._last_thinking_block.connect_to_next()
            self._last_thinking_block = None   # one-to-one: each thinking maps to first tool

        is_agent = message.callable_type in ("specialist", "core")
        if is_agent:
            block: ToolCallBlock | AgentCallBlock = AgentCallBlock(
                agent_name=message.callable_name,
                input_summary=input_summary,
                from_thinking=from_thinking,
            )
        else:
            block = ToolCallBlock(
                tool_name=message.callable_name,
                input_summary=input_summary,
                from_thinking=from_thinking,
            )
        self._open_tool_blocks[message.callable_name] = block

        # Mount inline in the chat stream — Claude Code style
        try:
            scroll = self._app.screen.query_one("#chat-scroll", VerticalScroll)
            # Insert before the streaming block so tool calls appear above the response
            if self._streaming_block is not None:
                await scroll.mount(block, before=self._streaming_block)
            else:
                await scroll.mount(block)
            self._app.call_after_refresh(scroll.scroll_end)
        except Exception as exc:
            _logger.debug("tui_tool_block_mount_failed", error=str(exc))

    async def on_tool_call_finished(self, message: ToolCallFinished) -> None:
        block = self._open_tool_blocks.pop(message.callable_name, None)
        if block is None:
            return
        if message.success:
            block.set_result(message.output_summary)
        else:
            block.set_error(message.output_summary)

        # Persist to tool history for session resume
        input_summary = self._tool_input_summaries.pop(message.callable_name, "")
        msg_count = self._tool_msg_counts.pop(message.callable_name, None)
        try:
            await self._service.record_tool_call(
                self._session_id,
                message.callable_name,
                input_summary,
                message.output_summary or "",
                message.success,
                callable_type=message.callable_type,
                msg_count=msg_count,
            )
        except Exception as _exc:
            _logger.debug("tui_record_tool_call_failed", error=str(_exc))

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
        self._update_context_bar(state="running")

    def on_run_phase_changed(self, message: RunPhaseChanged) -> None:
        """Update ContextBar state on every run-state transition."""
        self._update_context_bar(state=message.phase)

    # ── Popup ──────────────────────────────────────────────────────────────────

    def toggle_slash_popup(self) -> None:
        if self._popup is not None:
            self.dismiss_popup()
        else:
            self._show_slash_popup()

    def dismiss_popup(self) -> None:
        if self._popup is not None:
            with contextlib.suppress(Exception):
                self._popup.remove()
            self._popup = None

    def on_input_value_changed(self, value: str) -> None:
        """Called by ChatScreen whenever the chat input value changes."""
        if value.startswith("/"):
            prefix = value[1:]  # text after the slash
            if self._popup is None:
                self._show_slash_popup(initial_filter=prefix)
            else:
                self._popup.update_filter(prefix)
        else:
            if self._popup is not None:
                self.dismiss_popup()

    def _show_slash_popup(self, initial_filter: str = "") -> None:
        from citnega.apps.tui.widgets.slash_popup import SlashCommandPopup

        cmds = [
            (name, getattr(cmd, "help_text", ""))
            for name, cmd in self._slash_commands.items()
        ]
        popup = SlashCommandPopup(commands=cmds)
        if initial_filter:
            popup._filter = initial_filter
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

    async def _append_picker(
        self,
        title: str,
        options: list[tuple[str, str]],
        on_select,
        on_dismiss=None,
    ) -> None:
        """
        Mount an interactive ``OptionPickerBlock`` in the chat scroll.

        Args:
            title:      Heading shown above the list.
            options:    ``[(value, display_label), ...]``
            on_select:  Async callable ``(value: str, label: str) -> None``
                        invoked when the user picks an option.
            on_dismiss: Optional async callable ``() -> None`` invoked on Esc.
        """
        import uuid as _uuid

        widget_id = f"picker-{_uuid.uuid4().hex[:8]}"
        block = OptionPickerBlock(title=title, options=options, id=widget_id)
        self._picker_callbacks[widget_id] = (on_select, on_dismiss)
        scroll = self._app.screen.query_one("#chat-scroll", VerticalScroll)
        try:
            hint = scroll.query_one("#empty-hint")
            await hint.remove()
        except Exception:
            pass
        await scroll.mount(block)
        self._app.call_after_refresh(scroll.scroll_end)

    async def on_option_picker_block_selected(self, message: OptionPickerBlock.Selected) -> None:
        """Routed from CitnegaApp — a picker option was chosen."""
        callbacks = self._picker_callbacks.pop(message.picker_id, None)
        if callbacks:
            on_select, _ = callbacks
            if on_select is not None:
                await on_select(message.value, message.label)

    async def on_option_picker_block_dismissed(self, message: OptionPickerBlock.Dismissed) -> None:
        """Routed from CitnegaApp — user pressed Escape on a picker."""
        callbacks = self._picker_callbacks.pop(message.picker_id, None)
        if callbacks:
            _, on_dismiss = callbacks
            if on_dismiss is not None:
                await on_dismiss()
            else:
                await self._append_message("system", "Selection cancelled.")

    async def _handle_slash(self, text: str) -> None:
        parts = text[1:].split()
        cmd_name = parts[0].lower() if parts else ""
        args = parts[1:]
        handler = self._slash_commands.get(cmd_name)
        if handler is None:
            await self._append_message(
                "system", f"Unknown command /{cmd_name}. Type /help for available commands."
            )
            return
        await handler.execute(args, self)

    # ── ContextBar helpers ─────────────────────────────────────────────────────

    def _update_context_bar(self, **kwargs) -> None:
        """Update one or more ContextBar reactive fields (model, mode, think, folder, state)."""
        try:
            from citnega.apps.tui.widgets.context_bar import ContextBar

            bar = self._app.screen.query_one(ContextBar)
            for field, value in kwargs.items():
                setattr(bar, field, value)
        except Exception:
            pass

    def seed_context_bar(
        self,
        model: str = "",
        mode: str = "direct",
        think: str = "off",
        folder: str = "",
        session_name: str = "",
    ) -> None:
        """Called by the App after controller creation to pre-populate the bar."""
        self._update_context_bar(
            model=model,
            mode=mode,
            think=think,
            folder=folder,
            state="idle",
            session_name=session_name,
        )

    async def shutdown(self) -> None:
        """Cancel background consumer if running."""
        if self._consumer is not None:
            await self._consumer.stop()


# ── Slash command registry factory ────────────────────────────────────────────


def _build_slash_registry(app, service, session_id, controller):
    from citnega.apps.tui.slash_commands.builtin import (
        AgentCommand,
        ApproveCommand,
        CancelCommand,
        ClearCommand,
        CompactCommand,
        DeleteSessionCommand,
        HelpCommand,
        ModeCommand,
        ModelCommand,
        NewSessionCommand,
        RenameCommand,
        SessionsCommand,
        ShowSessionCommand,
        SkillCommand,
        SkillsCommand,
        ThinkCommand,
    )
    from citnega.apps.tui.slash_commands.workspace import (
        CreateAgentCommand,
        CreateMentalModelCommand,
        CreateSkillCommand,
        CreateToolCommand,
        CreateWorkflowCommand,
        RefreshCommand,
        SetWorkfolderCommand,
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
        RenameCommand(service=service),
        DeleteSessionCommand(service=service),
        ShowSessionCommand(service=service),
        SessionsCommand(service=service),
        ThinkCommand(service=service),
        SkillsCommand(),
        SkillCommand(),
        # Workspace commands
        SetWorkfolderCommand(service=service),
        RefreshCommand(service=service),
        CreateToolCommand(service=service),
        CreateAgentCommand(service=service),
        CreateWorkflowCommand(service=service),
        CreateSkillCommand(service=service),
        CreateMentalModelCommand(service=service),
    ]
    return {cmd.name: cmd for cmd in cmds}
