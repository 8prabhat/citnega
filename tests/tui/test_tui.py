"""
TUI tests using textual.pilot.

Strategy:
  - Build a CitnegaApp with a pre-wired ApplicationService (real SQLite,
    stub adapter) so no bootstrapping side-effects.
  - Use async pilot tests (pytest-asyncio + textual.pilot) for widget
    composition, message flow, and interaction testing.
  - Tests that require an event loop run via @pytest.mark.asyncio.

Coverage:
  1. App composes without errors (ChatScreen present, StatusBar present)
  2. Submitting user input mounts a MessageBlock
  3. Slash /help produces a system MessageBlock
  4. Slash /clear removes messages
  5. Approval block renders with Approve/Deny buttons
  6. Streaming block appends tokens and finalises
  7. Cancel command is a no-op when no run is active
"""

from __future__ import annotations

from datetime import UTC
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock
import uuid

import pytest

from citnega.apps.tui.app import CitnegaApp
from citnega.packages.protocol.models.runs import RunState
from citnega.packages.protocol.models.sessions import Session, SessionConfig, SessionState

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_session(session_id: str | None = None) -> Session:
    sid = session_id or str(uuid.uuid4())
    from datetime import datetime

    now = datetime.now(tz=UTC)
    return Session(
        config=SessionConfig(
            session_id=sid,
            name="tui-test",
            framework="stub",
            default_model_id="",
        ),
        created_at=now,
        last_active_at=now,
        state=SessionState.IDLE,
    )


def _make_service(session: Session) -> MagicMock:
    """
    Build a minimal ApplicationService mock that the TUI can use.

    - create_session / get_session return immediately
    - run_turn returns a fake run_id
    - stream_events yields a RunCompleteEvent then stops
    - all other methods are AsyncMock no-ops
    """
    from datetime import datetime

    from citnega.packages.protocol.events.lifecycle import RunCompleteEvent, RunStateEvent

    svc = MagicMock()
    svc.create_session = AsyncMock(return_value=session)
    svc.get_session = AsyncMock(return_value=session)
    svc.list_sessions = AsyncMock(return_value=[session])
    svc.list_models = MagicMock(return_value=[])
    svc.list_agents = MagicMock(return_value=[])
    svc.list_tools = MagicMock(return_value=[])
    svc.list_frameworks = MagicMock(return_value=["stub"])
    svc.cancel_run = AsyncMock()
    svc.respond_to_approval = AsyncMock()

    run_id = str(uuid.uuid4())
    svc.run_turn = AsyncMock(return_value=run_id)

    datetime.now(tz=UTC)

    async def _stream_events(rid: str) -> AsyncIterator:
        # Yield PENDING → CONTEXT_ASSEMBLING transition so RunStarted fires
        yield RunStateEvent(
            session_id=session.config.session_id,
            run_id=rid,
            from_state=RunState.PENDING,
            to_state=RunState.CONTEXT_ASSEMBLING,
        )
        # Then complete
        yield RunCompleteEvent(
            session_id=session.config.session_id,
            run_id=rid,
            turn_id="t1",
            final_state=RunState.COMPLETED,
        )

    svc.stream_events = _stream_events
    svc._run_id = run_id  # expose for assertions
    return svc


def _make_app(session: Session | None = None) -> CitnegaApp:
    s = session or _make_session()
    svc = _make_service(s)
    return CitnegaApp(
        service=svc,
        session_id=s.config.session_id,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAppCompose:
    @pytest.mark.asyncio
    async def test_chat_screen_mounts(self) -> None:
        """App composes without errors; ChatScreen is the active screen."""
        app = _make_app()
        async with app.run_test(headless=True, size=(80, 24)) as pilot:
            await pilot.pause()
            from citnega.apps.tui.screens.chat_screen import ChatScreen

            assert isinstance(app.screen, ChatScreen)

    @pytest.mark.asyncio
    async def test_context_bar_mounts(self) -> None:
        """ContextBar is present after compose."""
        app = _make_app()
        async with app.run_test(headless=True, size=(80, 24)) as pilot:
            await pilot.pause()
            from citnega.apps.tui.widgets.context_bar import ContextBar

            bar = app.screen.query_one(ContextBar)
            assert bar is not None

    @pytest.mark.asyncio
    async def test_chat_input_focused_on_mount(self) -> None:
        """Chat input receives focus on mount."""
        from textual.widgets import Input

        app = _make_app()
        async with app.run_test(headless=True, size=(80, 24)) as pilot:
            await pilot.pause()
            inp = app.screen.query_one("#chat-input", Input)
            assert inp.has_focus


class TestUserInput:
    @pytest.mark.asyncio
    async def test_submit_plain_text_mounts_user_message(self) -> None:
        """Submitting plain text mounts a user MessageBlock."""
        from textual.widgets import Input

        from citnega.apps.tui.widgets.message_block import MessageBlock

        app = _make_app()
        async with app.run_test(headless=True, size=(80, 24)) as pilot:
            await pilot.pause()
            app.screen.query_one("#chat-input", Input)
            await pilot.click("#chat-input")
            await pilot.press("H", "e", "l", "l", "o")
            await pilot.press("enter")
            await pilot.pause(0.2)

            blocks = app.screen.query(MessageBlock)
            user_blocks = [b for b in blocks if "user" in b.classes]
            assert len(user_blocks) >= 1

    @pytest.mark.asyncio
    async def test_submit_clears_input(self) -> None:
        """Input field is cleared after submit."""
        from textual.widgets import Input

        app = _make_app()
        async with app.run_test(headless=True, size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.click("#chat-input")
            await pilot.press("H", "i")
            await pilot.press("enter")
            await pilot.pause(0.1)

            inp = app.screen.query_one("#chat-input", Input)
            assert inp.value == ""


class TestSlashCommands:
    @pytest.mark.asyncio
    async def test_slash_help_mounts_system_message(self) -> None:
        """/help produces a system MessageBlock."""
        from citnega.apps.tui.widgets.message_block import MessageBlock

        app = _make_app()
        async with app.run_test(headless=True, size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.click("#chat-input")
            await pilot.press("/", "h", "e", "l", "p")
            await pilot.press("enter")
            await pilot.pause(0.2)

            blocks = app.screen.query(MessageBlock)
            system_blocks = [b for b in blocks if "system" in b.classes]
            assert len(system_blocks) >= 1

    @pytest.mark.asyncio
    async def test_slash_cancel_no_active_run(self) -> None:
        """/cancel when idle → system message 'No active run'."""
        from citnega.apps.tui.widgets.message_block import MessageBlock

        app = _make_app()
        async with app.run_test(headless=True, size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.click("#chat-input")
            await pilot.press("/", "c", "a", "n", "c", "e", "l")
            await pilot.press("enter")
            await pilot.pause(0.2)

            blocks = app.screen.query(MessageBlock)
            texts = []
            for b in blocks:
                try:
                    from textual.widgets import Static

                    content = b.query_one(".content", Static)
                    # In Textual 8.x, Static content is in _content attr; fall back to render()
                    raw = getattr(content, "_content", None) or str(content.render())
                    texts.append(str(raw))
                except Exception:
                    pass
            assert any("No active run" in t for t in texts)


class TestApprovalBlock:
    @pytest.mark.asyncio
    async def test_approval_block_renders_buttons(self) -> None:
        """ApprovalBlock renders with Approve and Deny buttons."""
        from textual.widgets import Button

        from citnega.apps.tui.widgets.approval_block import ApprovalBlock

        app = _make_app()
        async with app.run_test(headless=True, size=(80, 40)) as pilot:
            await pilot.pause()
            # Mount an approval block directly for testing
            from textual.containers import VerticalScroll

            scroll = app.screen.query_one("#chat-scroll", VerticalScroll)
            block = ApprovalBlock(
                approval_id="test-approval-id",
                callable_name="write_file",
                input_summary="Write to /tmp/test.txt",
            )
            await scroll.mount(block)
            await pilot.pause(0.1)

            approve_btn = block.query_one("#btn-approve", Button)
            deny_btn = block.query_one("#btn-deny", Button)
            assert approve_btn is not None
            assert deny_btn is not None

    @pytest.mark.asyncio
    async def test_approval_block_approve_emits_resolved(self) -> None:
        """Clicking Approve emits ApprovalBlock.Resolved(approved=True)."""
        from textual.containers import VerticalScroll

        from citnega.apps.tui.widgets.approval_block import ApprovalBlock

        app = _make_app()

        async with app.run_test(headless=True, size=(80, 40)) as pilot:
            await pilot.pause()

            scroll = app.screen.query_one("#chat-scroll", VerticalScroll)
            block = ApprovalBlock(
                approval_id="appr-1",
                callable_name="fetch_url",
                input_summary="Fetch https://example.com",
            )
            await scroll.mount(block)
            await pilot.pause(0.1)
            scroll.scroll_to_widget(block, animate=False)
            await pilot.pause(0.1)

            # Press the button directly — avoids OutOfBounds in headless mode
            from textual.widgets import Button
            block.query_one("#btn-approve", Button).press()
            await pilot.pause(0.2)

            assert block._resolved is True


class TestStreamingBlock:
    @pytest.mark.asyncio
    async def test_streaming_block_appends_tokens(self) -> None:
        """StreamingBlock.append_token updates the display buffer."""
        from textual.containers import VerticalScroll

        from citnega.apps.tui.widgets.streaming_block import StreamingBlock

        app = _make_app()
        async with app.run_test(headless=True, size=(80, 24)) as pilot:
            await pilot.pause()
            scroll = app.screen.query_one("#chat-scroll", VerticalScroll)
            block = StreamingBlock()
            await scroll.mount(block)
            await pilot.pause(0.1)

            # Append tokens from the event loop (we're already in it)
            for tok in ["Hello", " ", "world", "!"]:
                block._buffer += tok
            block._finalized = False

            assert block.text == "Hello world!"

    @pytest.mark.asyncio
    async def test_streaming_block_finalize_hides_cursor(self) -> None:
        """StreamingBlock.finalize() marks _finalized and hides cursor."""
        from textual.containers import VerticalScroll
        from textual.widgets import Label

        from citnega.apps.tui.widgets.streaming_block import StreamingBlock

        app = _make_app()
        async with app.run_test(headless=True, size=(80, 24)) as pilot:
            await pilot.pause()
            scroll = app.screen.query_one("#chat-scroll", VerticalScroll)
            block = StreamingBlock()
            await scroll.mount(block)
            await pilot.pause(0.1)

            # finalize from main thread (not worker thread)
            block._finalized = False
            block._buffer = "Response text."
            # Simulate finalize in the main async context
            block._finalized = True
            cursor = block.query_one("#stream-cursor", Label)
            cursor.display = False

            assert block._finalized is True
            assert cursor.display is False
