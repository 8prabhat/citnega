"""Unit tests for ChatController wizard intercept logic."""

from __future__ import annotations

import asyncio

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
