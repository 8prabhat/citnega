"""Tests for WizardBase._validate_and_store_name() (B1)."""

from __future__ import annotations

import pytest

from citnega.apps.tui.slash_commands.wizard_base import WizardBase


class _FakeCtrl:
    def __init__(self):
        self._wizard_data: dict = {}
        self._pending_wizard = None
        self._messages: list[tuple[str, str]] = []

    async def _append_message(self, role: str, content: str) -> None:
        self._messages.append((role, content))


class ConcreteWizard(WizardBase):
    pass


@pytest.fixture()
def wizard():
    return ConcreteWizard()


async def test_valid_name_stored(wizard) -> None:
    ctrl = _FakeCtrl()
    ctrl._wizard_data = {}
    next_called: list[str] = []

    async def _next(c) -> None:
        next_called.append(c._wizard_data["name"])

    await wizard._validate_and_store_name("my_tool", ctrl, "step", _next)

    assert ctrl._wizard_data["name"] == "my_tool"
    assert ctrl._wizard_data["class_name"] == "MyTool"
    assert next_called == ["my_tool"]


async def test_name_normalized_to_snake_case(wizard) -> None:
    ctrl = _FakeCtrl()
    ctrl._wizard_data = {}
    next_called: list[str] = []

    async def _next(c) -> None:
        next_called.append(c._wizard_data["name"])

    await wizard._validate_and_store_name("My Tool Name", ctrl, "step", _next)
    assert next_called == ["my_tool_name"]


async def test_invalid_name_rejects_and_re_prompts(wizard) -> None:
    ctrl = _FakeCtrl()
    ctrl._wizard_data = {}

    async def _next(c) -> None:
        pass

    await wizard._validate_and_store_name("123invalid!", ctrl, "step", _next)

    assert "name" not in ctrl._wizard_data
    assert ctrl._pending_wizard is not None
    assert any("not a valid" in m[1] for m in ctrl._messages)


async def test_empty_name_rejects(wizard) -> None:
    ctrl = _FakeCtrl()
    ctrl._wizard_data = {}

    async def _next(c) -> None:
        pass

    await wizard._validate_and_store_name("   ", ctrl, "step", _next)
    assert "name" not in ctrl._wizard_data


async def test_start_name_step_installs_wizard(wizard) -> None:
    ctrl = _FakeCtrl()
    ctrl._wizard_data = {}

    async def _next(c) -> None:
        pass

    wizard._start_name_step(ctrl, "my_step", _next, prompt="Enter name:")
    assert ctrl._pending_wizard is not None
    assert ctrl._pending_wizard.step_name == "my_step"
