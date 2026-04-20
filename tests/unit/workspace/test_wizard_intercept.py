"""Unit tests for ChatController wizard intercept logic."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from citnega.apps.tui.slash_commands.workspace import WizardState

# ── Minimal controller stub ────────────────────────────────────────────────────


class _FakeController:
    """Minimal stub that mimics the wizard-related parts of ChatController."""

    def __init__(self):
        self._pending_wizard = None
        self._wizard_data: dict = {}
        self._messages: list[tuple[str, str]] = []

    async def _append_message(self, role: str, content: str) -> None:
        self._messages.append((role, content))

    async def handle_user_input(self, text: str) -> None:
        """Replicate the 3-line wizard intercept from the real ChatController."""
        if self._pending_wizard is not None:
            wizard, self._pending_wizard = self._pending_wizard, None
            await wizard.on_input(text, self)
            return
        # Normal flow — just record the text
        self._messages.append(("user", text))


# ── Tests ──────────────────────────────────────────────────────────────────────


class TestWizardIntercept:
    def test_wizard_consumes_next_input(self) -> None:
        ctrl = _FakeController()
        received: list[str] = []

        async def _on_input(text: str, c) -> None:
            received.append(text)

        ctrl._pending_wizard = WizardState("step", _on_input)
        asyncio.run(ctrl.handle_user_input("hello wizard"))

        assert received == ["hello wizard"]

    def test_wizard_is_cleared_before_callback(self) -> None:
        """Wizard is set to None before on_input is called so re-entrant
        setting inside the callback works correctly."""
        ctrl = _FakeController()
        wizard_state_at_callback: list = []

        async def _on_input(text: str, c) -> None:
            wizard_state_at_callback.append(c._pending_wizard)

        ctrl._pending_wizard = WizardState("step", _on_input)
        asyncio.run(ctrl.handle_user_input("test"))

        # At the moment on_input was called, _pending_wizard was already None
        assert wizard_state_at_callback == [None]

    def test_new_wizard_set_inside_callback(self) -> None:
        """A wizard step can schedule the next step by setting _pending_wizard
        inside its own on_input callback."""
        ctrl = _FakeController()
        step2_received: list[str] = []

        async def _step2(text: str, c) -> None:
            step2_received.append(text)

        async def _step1(text: str, c) -> None:
            c._pending_wizard = WizardState("step2", _step2)

        ctrl._pending_wizard = WizardState("step1", _step1)
        asyncio.run(ctrl.handle_user_input("step1 answer"))
        asyncio.run(ctrl.handle_user_input("step2 answer"))

        assert step2_received == ["step2 answer"]

    def test_normal_slash_when_no_wizard(self) -> None:
        ctrl = _FakeController()
        asyncio.run(ctrl.handle_user_input("hello"))
        assert ("user", "hello") in ctrl._messages

    def test_wizard_does_not_intercept_if_none(self) -> None:
        ctrl = _FakeController()
        ctrl._pending_wizard = None
        asyncio.run(ctrl.handle_user_input("regular input"))
        assert ("user", "regular input") in ctrl._messages

    def test_wizard_state_attributes(self) -> None:
        async def _noop(t, c):
            pass

        ws = WizardState("my_step", _noop, "Enter your name:")
        assert ws.step_name == "my_step"
        assert ws.on_input is _noop
        assert ws.prompt == "Enter your name:"


class _FakeSlashController(_FakeController):
    def __init__(self):
        super().__init__()
        self.pickers: list[tuple[str, list[tuple[str, str]]]] = []

    async def _append_picker(self, title, options, on_select, on_dismiss):
        self.pickers.append((title, options))
        await on_select("done", "Done")


class _FakeService:
    def list_tools(self):
        return [SimpleNamespace(name="repo_map"), SimpleNamespace(name="search_files")]

    def list_agents(self):
        return [SimpleNamespace(name="research_agent")]


class TestCreateSkillWizard:
    @pytest.mark.asyncio
    async def test_createskill_initializes_shared_keys(self) -> None:
        from citnega.apps.tui.slash_commands.workspace import CreateSkillCommand

        ctrl = _FakeSlashController()
        cmd = CreateSkillCommand(service=_FakeService())
        await cmd.execute([], ctrl)

        assert ctrl._wizard_data["tool_whitelist"] == []
        assert ctrl._wizard_data["sub_agents"] == []

    @pytest.mark.asyncio
    async def test_createskill_flow_reaches_writer_without_keyerror(self) -> None:
        from citnega.apps.tui.slash_commands.workspace import CreateSkillCommand

        ctrl = _FakeSlashController()
        cmd = CreateSkillCommand(service=_FakeService())
        await cmd.execute([], ctrl)
        # Use the installed wizard handler instead of calling _on_name directly
        await ctrl._pending_wizard.on_input("release_readiness", ctrl)
        await cmd._on_desc("optimize release quality", ctrl)

        writer_mock = AsyncMock()
        with patch(
            "citnega.apps.tui.slash_commands.workspace._write_skill_bundle",
            writer_mock,
        ):
            await cmd._on_triggers("release, qa", ctrl)

        writer_mock.assert_awaited_once()


def test_slash_registry_includes_workspace_skill_command() -> None:
    from citnega.apps.tui.controllers.chat_controller import _build_slash_registry

    registry = _build_slash_registry(
        app=MagicMock(),
        service=MagicMock(),
        session_id="s1",
        controller=MagicMock(),
    )

    assert "createskill" in registry
    assert "createworkflow" in registry
    assert "creatementalmodel" in registry
    assert len(registry) == 23  # 21 original + skills + skill
