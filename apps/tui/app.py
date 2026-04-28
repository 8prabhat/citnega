"""
Citnega TUI — entry point.

The App owns:
  - The ApplicationService (injected via cli_bootstrap)
  - The ChatController (processes incoming canonical events into UI updates)
  - The EventConsumerWorker (bridges EventEmitter queue → Textual messages)
  - The active session (created on startup if none exists)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
import uuid

_log = logging.getLogger(__name__)

from textual.app import App

from citnega.apps.tui.screens.chat_screen import (
    ChatScreen,
    DismissPopup,
    ToggleSlashPopup,
    UserInputSubmitted,
)
from citnega.apps.tui.screens.session_picker import SessionPickerScreen

if TYPE_CHECKING:
    from citnega.apps.tui.widgets.approval_block import ApprovalBlock
    from citnega.apps.tui.widgets.option_picker_block import OptionPickerBlock
    from citnega.apps.tui.widgets.plan_approval_block import PlanApprovalBlock
    from citnega.apps.tui.workers.event_consumer import (
        ApprovalRequested,
        RunFinished,
        RunPhaseChanged,
        RunStarted,
        ThinkingReceived,
        TokenReceived,
        ToolCallFinished,
        ToolCallStarted,
    )
    from citnega.packages.runtime.app_service import ApplicationService


class CitnegaApp(App):
    """
    Single-window conversational TUI.

    Lifecycle:
      1. on_mount  → push ChatScreen, bootstrap ApplicationService, create session
      2. User sends input → ChatController routes to ApplicationService
      3. EventConsumerWorker drains EventEmitter → posts TUI messages
      4. ChatController handles messages → mutates widgets
    """

    TITLE = "Citnega"
    SUB_TITLE = "agentic assistant"

    def __init__(
        self,
        *,
        service: ApplicationService | None = None,
        session_id: str | None = None,
        theme_name: str = "dark",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._service: ApplicationService | None = service
        self._session_id: str | None = session_id
        self._theme_name = theme_name
        self._controller = None
        self._bootstrap_ctx = None

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def on_mount(self) -> None:
        # 1. Bootstrap the service if not injected
        if self._service is None:
            from citnega.apps.cli.bootstrap import cli_bootstrap

            self._bootstrap_ctx = cli_bootstrap()
            try:
                self._service = await self._bootstrap_ctx.__aenter__()
            except Exception as exc:
                # Fall back to chat screen directly if bootstrap fails
                await self.push_screen(ChatScreen())
                self.notify(f"Bootstrap failed: {exc}", severity="error", timeout=10)
                return

        # 2. If a specific session_id was given, go straight to chat
        if self._session_id is not None:
            await self._start_chat_with_session(self._session_id)
            return

        # 3. Otherwise show the session picker
        from citnega.packages.config.loaders import load_settings

        settings = load_settings()
        limit = settings.conversation.max_sessions_shown

        try:
            all_sessions = await self._service.list_sessions()
        except Exception as exc:
            _log.debug("list_sessions failed: %s", exc)
            all_sessions = []

        # Sort by most recently active first, cap at configured limit
        all_sessions.sort(
            key=lambda s: s.last_active_at or "",
            reverse=True,
        )
        recent = all_sessions[:limit]

        picker = SessionPickerScreen(sessions=recent)
        await self.push_screen(picker)

    async def on_session_picker_screen_session_selected(
        self, message: SessionPickerScreen.SessionSelected
    ) -> None:
        """User picked a session from the picker — resume it."""
        await self.pop_screen()
        await self._start_chat_with_session(message.session_id)

    async def on_history_screen_session_selected(self, message: object) -> None:
        """User picked a session from the History screen (F3) — resume it."""
        from citnega.apps.tui.screens.history_screen import HistoryScreen

        if isinstance(message, HistoryScreen.SessionSelected):
            await self.pop_screen()
            await self._start_chat_with_session(message.session_id)

    async def on_session_picker_screen_new_session_requested(
        self, message: SessionPickerScreen.NewSessionRequested
    ) -> None:
        """User pressed 'n' in the picker — start a fresh session."""
        await self.pop_screen()
        await self._start_chat_with_session(None)

    def _session_defaults(self) -> tuple[str, str]:
        """Return (framework, model_id) defaults from the active service."""
        framework = "direct"
        model_id = ""
        if self._service is None:
            return framework, model_id

        try:
            frameworks = self._service.list_frameworks()
            if isinstance(frameworks, list) and frameworks and isinstance(frameworks[0], str):
                framework = frameworks[0]
        except Exception as exc:
            _log.debug("list_frameworks failed: %s", exc)

        try:
            models = self._service.list_models()
            if isinstance(models, list) and models and isinstance(models[0].model_id, str):
                model_id = models[0].model_id
        except Exception as exc:
            _log.debug("list_models failed: %s", exc)

        return framework, model_id

    async def _start_chat_with_session(self, session_id: str | None) -> None:
        """Push ChatScreen and wire up the controller for *session_id*."""
        await self.push_screen(ChatScreen())

        from citnega.packages.protocol.models.sessions import SessionConfig

        framework, default_model_id = self._session_defaults()

        try:
            if session_id is None:
                config = SessionConfig(
                    session_id=str(uuid.uuid4()),
                    name="new-session",
                    framework=framework,
                    default_model_id=default_model_id,
                )
                session = await self._service.create_session(config)
                self._session_id = session.config.session_id
            else:
                try:
                    session = await self._service.get_session(session_id)
                    self._session_id = session.config.session_id
                    # Warm up the runner so conversation history is in-memory
                    await self._service.ensure_runner(self._session_id)
                    self._resume_session_id = self._session_id
                except Exception:
                    # Session not found — create fresh
                    self.notify(f"Session {session_id!r} not found; starting fresh.")
                    config = SessionConfig(
                        session_id=str(uuid.uuid4()),
                        name="new-session",
                        framework=framework,
                        default_model_id=default_model_id,
                    )
                    session = await self._service.create_session(config)
                    self._session_id = session.config.session_id
        except Exception as exc:
            self.notify(f"Session setup failed: {exc}", severity="error", timeout=10)
            return

        # Seed ContextBar with session identity fields
        from citnega.apps.tui.widgets.context_bar import ContextBar

        try:
            ctx = self.screen.query_one(ContextBar)
            ctx.session_id = self._session_id
            ctx.framework = self._service.list_frameworks()[0] if self._service else "direct"
        except Exception as exc:
            _log.debug("context_bar seed failed: %s", exc)

        # Create controller
        from citnega.apps.tui.controllers.chat_controller import ChatController

        self._controller = ChatController(
            app=self,
            service=self._service,
            session_id=self._session_id,
        )

        # Seed the ContextBar with initial session values
        active_model = self._service.get_session_model(self._session_id) if self._service else ""
        if not active_model and self._service:
            models = self._service.list_models()
            active_model = models[0].model_id if models else ""
        active_mode = (
            self._service.get_session_mode(self._session_id) if self._service else "direct"
        )
        think_val = (
            self._service.get_session_thinking(self._session_id) if self._service else None
        )
        think_label = {True: "on", False: "off", None: "auto"}.get(think_val, "auto")
        import os
        workfolder = os.getcwd()
        try:
            from citnega.packages.config.loaders import load_settings
            ws = load_settings().workspace
            if ws.workfolder_path:
                workfolder = ws.workfolder_path
        except Exception as exc:
            _log.debug("load_settings for workfolder failed: %s", exc)
        session_name = getattr(getattr(session, "config", None), "name", "") or ""
        self._controller.seed_context_bar(
            model=active_model,
            mode=active_mode,
            think=think_label,
            folder=workfolder,
            session_name=session_name,
        )

        # Render persisted history when resuming an existing session
        resume_sid = getattr(self, "_resume_session_id", None)
        if resume_sid and self._service:
            self._resume_session_id = None
            try:
                from collections import defaultdict

                from textual.containers import VerticalScroll

                from citnega.apps.tui.widgets.agent_call_block import AgentCallBlock
                from citnega.apps.tui.widgets.tool_call_block import ToolCallBlock

                raw_messages = self._service.get_conversation_messages(resume_sid)
                # Drop a dangling user message at the end (saved before LLM died)
                if raw_messages and raw_messages[-1].get("role") == "user":
                    raw_messages = raw_messages[:-1]

                # Group tool history by msg_count so blocks appear inline after
                # the message that triggered them (not consolidated at the end).
                # msg_count=N means N messages existed when the tool was called,
                # so the block belongs after raw_messages[N-1] (0-indexed).
                # Entries without msg_count (legacy) go at the very end.
                tool_history = self._service.get_session_tool_history(resume_sid)
                tools_by_pos: defaultdict[int, list[dict]] = defaultdict(list)
                for entry in tool_history[-100:]:
                    pos = entry.get("msg_count")
                    if pos is None:
                        pos = len(raw_messages) + 1  # legacy: append after all messages
                    tools_by_pos[int(pos)].append(entry)

                scroll = self.screen.query_one("#chat-scroll", VerticalScroll)

                async def _mount_tool_blocks(entries: list[dict]) -> None:
                    for entry in entries:
                        ct = entry.get("callable_type", "tool")
                        is_agent = ct in ("specialist", "core")
                        if is_agent:
                            block: AgentCallBlock | ToolCallBlock = AgentCallBlock(
                                agent_name=entry.get("name", "?"),
                                input_summary=entry.get("input_summary", ""),
                            )
                        else:
                            block = ToolCallBlock(
                                tool_name=entry.get("name", "?"),
                                input_summary=entry.get("input_summary", ""),
                            )
                        await scroll.mount(block)
                        if entry.get("success", True):
                            block.set_result(entry.get("output_summary", ""))
                        else:
                            block.set_error(entry.get("output_summary", ""))

                # Interleave: after message[i] mount tool blocks with msg_count == i+1
                for i, msg in enumerate(raw_messages):
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    if content:
                        if role in ("user", "assistant"):
                            await self._controller._append_message(role, content)
                        elif role == "system" and content.startswith("[Compacted"):
                            await self._controller._append_message("system", content)
                    # Tool blocks that ran after message[i] was saved have msg_count == i+1
                    await _mount_tool_blocks(tools_by_pos.get(i + 1, []))

                # Legacy tool blocks (no msg_count) go at the very end
                await _mount_tool_blocks(tools_by_pos.get(len(raw_messages) + 1, []))

            except Exception as exc:
                _log.debug("history_restore failed: %s", exc)

    async def on_unmount(self) -> None:
        if self._controller is not None:
            await self._controller.shutdown()
        if self._bootstrap_ctx is not None:
            await self._bootstrap_ctx.__aexit__(None, None, None)

    # ── Message handlers ───────────────────────────────────────────────────────

    async def on_user_input_submitted(self, message: UserInputSubmitted) -> None:
        if self._controller is None:
            return
        await self._controller.handle_user_input(message.text)

    def on_dismiss_popup(self, message: DismissPopup) -> None:
        if self._controller is not None:
            self._controller.dismiss_popup()

    def on_toggle_slash_popup(self, message: ToggleSlashPopup) -> None:
        if self._controller is not None:
            self._controller.toggle_slash_popup()

    async def on_approval_block_resolved(self, message: ApprovalBlock.Resolved) -> None:
        if self._controller is not None:
            await self._controller.on_approval_block_resolved(message)

    async def on_plan_approval_block_resolved(self, message: PlanApprovalBlock.Resolved) -> None:
        if self._controller is not None:
            await self._controller.on_plan_approval_block_resolved(message)

    async def on_thinking_received(self, message: ThinkingReceived) -> None:
        if self._controller is not None:
            await self._controller.on_thinking_received(message)

    async def on_token_received(self, message: TokenReceived) -> None:
        if self._controller is not None:
            await self._controller.on_token_received(message)

    async def on_run_started(self, message: RunStarted) -> None:
        if self._controller is not None:
            self._controller.on_run_started(message)

    async def on_run_phase_changed(self, message: RunPhaseChanged) -> None:
        if self._controller is not None:
            self._controller.on_run_phase_changed(message)

    async def on_run_finished(self, message: RunFinished) -> None:
        if self._controller is not None:
            await self._controller.on_run_finished(message)

    async def on_tool_call_started(self, message: ToolCallStarted) -> None:
        if self._controller is not None:
            await self._controller.on_tool_call_started(message)

    async def on_tool_call_finished(self, message: ToolCallFinished) -> None:
        if self._controller is not None:
            await self._controller.on_tool_call_finished(message)

    async def on_approval_requested(self, message: ApprovalRequested) -> None:
        if self._controller is not None:
            await self._controller.on_approval_requested(message)

    async def on_option_picker_block_selected(self, message: OptionPickerBlock.Selected) -> None:
        if self._controller is not None:
            await self._controller.on_option_picker_block_selected(message)

    async def on_option_picker_block_dismissed(self, message: OptionPickerBlock.Dismissed) -> None:
        if self._controller is not None:
            await self._controller.on_option_picker_block_dismissed(message)

    # ── Public API ─────────────────────────────────────────────────────────────

    @property
    def service(self) -> ApplicationService | None:
        return self._service

    @property
    def session_id(self) -> str | None:
        return self._session_id


def main() -> None:
    import sys

    # On Windows, Textual requires the ProactorEventLoop for subprocess support.
    if sys.platform == "win32":
        import asyncio

        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    CitnegaApp().run()


if __name__ == "__main__":
    main()
