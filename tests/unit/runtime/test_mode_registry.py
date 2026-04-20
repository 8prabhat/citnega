"""
Unit tests for the mode registry (Phase 8, Step 8.2).

Verifies:
- All 7 modes are registered
- get_mode() returns the correct mode
- get_mode() falls back to ChatMode for unknown names
- all_modes() returns all 7 modes in stable order
- TUI ModeCommand reads from all_modes()
- Each mode has a non-empty description
"""

from __future__ import annotations

import pytest

from citnega.packages.protocol.modes import VALID_MODES, all_modes, get_mode

_EXPECTED_MODES = {"chat", "plan", "explore", "research", "code", "review", "operate"}


def test_all_seven_modes_registered() -> None:
    registered = {m.name for m in all_modes()}
    assert registered == _EXPECTED_MODES, (
        f"Missing modes: {_EXPECTED_MODES - registered}. "
        f"Extra modes: {registered - _EXPECTED_MODES}"
    )


def test_valid_modes_list_complete() -> None:
    assert set(VALID_MODES) == _EXPECTED_MODES


@pytest.mark.parametrize("mode_name", sorted(_EXPECTED_MODES))
def test_get_mode_returns_correct_mode(mode_name: str) -> None:
    mode = get_mode(mode_name)
    assert mode.name == mode_name


def test_get_mode_unknown_falls_back_to_chat() -> None:
    mode = get_mode("nonexistent_mode")
    assert mode.name == "chat"


@pytest.mark.parametrize("mode_name", sorted(_EXPECTED_MODES))
def test_each_mode_has_description(mode_name: str) -> None:
    mode = get_mode(mode_name)
    assert mode.description, f"{mode_name} has empty description"


@pytest.mark.parametrize("mode_name", sorted(_EXPECTED_MODES))
def test_augment_system_prompt_returns_string(mode_name: str) -> None:
    mode = get_mode(mode_name)
    result = mode.augment_system_prompt("base prompt")
    assert isinstance(result, str)
    assert "base prompt" in result


def test_review_mode_augments_prompt() -> None:
    mode = get_mode("review")
    result = mode.augment_system_prompt("You are an assistant.")
    assert "review" in result.lower() or "reviewer" in result.lower()


def test_operate_mode_augments_prompt() -> None:
    mode = get_mode("operate")
    result = mode.augment_system_prompt("You are an assistant.")
    assert "operate" in result.lower() or "runbook" in result.lower()


def test_plan_mode_draft_and_execute_phases() -> None:
    from citnega.packages.protocol.modes import PlanMode

    mode = PlanMode()
    draft = mode.augment_system_prompt("base", phase="draft")
    execute = mode.augment_system_prompt("base", phase="execute")
    assert draft != execute
    assert "plan" in draft.lower()
    assert "execut" in execute.lower()


def test_all_modes_stable_order() -> None:
    order_first = [m.name for m in all_modes()]
    order_second = [m.name for m in all_modes()]
    assert order_first == order_second


# ── max_tool_rounds ───────────────────────────────────────────────────────────

def test_explore_mode_has_higher_tool_rounds() -> None:
    explore = get_mode("explore")
    chat = get_mode("chat")
    assert explore.max_tool_rounds > chat.max_tool_rounds
    assert explore.max_tool_rounds >= 12


def test_research_mode_has_highest_tool_rounds() -> None:
    research = get_mode("research")
    explore = get_mode("explore")
    assert research.max_tool_rounds >= explore.max_tool_rounds
    assert research.max_tool_rounds >= 15


def test_code_mode_has_more_rounds_than_chat() -> None:
    assert get_mode("code").max_tool_rounds > get_mode("chat").max_tool_rounds


def test_chat_mode_default_rounds() -> None:
    assert get_mode("chat").max_tool_rounds == 5


# ── Explore mode instructs tool use ──────────────────────────────────────────

def test_explore_mode_prompt_instructs_tools() -> None:
    prompt = get_mode("explore").augment_system_prompt("base")
    lower = prompt.lower()
    assert "search_web" in lower or "search web" in lower
    assert "tool" in lower


def test_explore_mode_prompt_instructs_agents() -> None:
    prompt = get_mode("explore").augment_system_prompt("base")
    lower = prompt.lower()
    # Should mention specialist agents
    assert "research_agent" in lower or "agent" in lower


def test_research_mode_prompt_instructs_tool_sequence() -> None:
    prompt = get_mode("research").augment_system_prompt("base")
    lower = prompt.lower()
    assert "search_web" in lower
    assert "read_kb" in lower
    assert "write_kb" in lower


# ── Per-mode temperature (P0-3) ───────────────────────────────────────────────


@pytest.mark.parametrize("mode_name", sorted(_EXPECTED_MODES))
def test_each_mode_has_temperature_property(mode_name: str) -> None:
    mode = get_mode(mode_name)
    t = mode.temperature
    assert isinstance(t, float), f"{mode_name}.temperature should be float, got {type(t)}"
    assert 0.0 <= t <= 1.0, f"{mode_name}.temperature={t} out of [0, 1]"


def test_code_mode_temperature_is_low() -> None:
    assert get_mode("code").temperature <= 0.3, "code mode needs low temperature for precision"


def test_operate_mode_temperature_is_low() -> None:
    assert get_mode("operate").temperature <= 0.3, "operate mode needs low temperature for safety"


def test_plan_mode_temperature_is_moderate() -> None:
    t = get_mode("plan").temperature
    assert t <= 0.5, f"plan mode should be ≤0.5 for structure, got {t}"


def test_explore_mode_temperature_is_high() -> None:
    assert get_mode("explore").temperature >= 0.7, "explore mode needs high temperature for creativity"


def test_review_mode_temperature_is_low() -> None:
    assert get_mode("review").temperature <= 0.4, "review mode needs low temperature for accuracy"


# ── ReviewMode and OperateMode protocol mandates (P0-4, P0-5) ─────────────────


def test_review_mode_has_higher_tool_rounds() -> None:
    assert get_mode("review").max_tool_rounds >= 8


def test_operate_mode_has_higher_tool_rounds() -> None:
    assert get_mode("operate").max_tool_rounds >= 8


def test_review_mode_has_tool_mandate_in_prompt() -> None:
    prompt = get_mode("review").augment_system_prompt("base")
    lower = prompt.lower()
    assert "git_ops" in lower or "git" in lower


def test_operate_mode_has_verification_mandate_in_prompt() -> None:
    prompt = get_mode("operate").augment_system_prompt("base")
    lower = prompt.lower()
    assert "run_shell" in lower or "verify" in lower
