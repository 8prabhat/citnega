"""Unit tests for ContextBar content rendering via _build_bar_content."""

from __future__ import annotations

from citnega.apps.tui.widgets.context_bar import _build_bar_content


def _build(**kwargs) -> str:
    defaults = dict(
        model="test-model",
        mode="direct",
        think="off",
        folder="/tmp/work",
        state="idle",
        session_name="",
        tokens_used=0,
        tokens_max=0,
        spin_char="⠋",
        session_id="",
        framework="",
    )
    defaults.update(kwargs)
    return _build_bar_content(**defaults)


def test_model_appears_in_output() -> None:
    assert "gemma4-26b" in _build(model="gemma4-26b")


def test_mode_appears_in_output() -> None:
    assert "plan" in _build(mode="plan")


def test_token_bar_low_shows_light_shade() -> None:
    content = _build(tokens_used=1000, tokens_max=8192)
    assert "░" in content


def test_token_bar_medium_shows_medium_shade() -> None:
    content = _build(tokens_used=5000, tokens_max=8192)
    assert "▒" in content


def test_token_bar_high_shows_dark_shade() -> None:
    content = _build(tokens_used=7000, tokens_max=8192)
    assert "▓" in content


def test_no_token_bar_when_max_zero() -> None:
    content = _build(tokens_used=0, tokens_max=0)
    assert "░" not in content and "▒" not in content and "▓" not in content


def test_session_name_appears_when_set() -> None:
    assert "my-session" in _build(session_name="my-session")


def test_session_name_absent_when_empty() -> None:
    content = _build(session_name="")
    assert "◈" in content


def test_active_state_uses_spinner() -> None:
    content = _build(state="executing", spin_char="⠙")
    assert "⠙" in content


def test_idle_state_uses_label() -> None:
    content = _build(state="idle")
    assert "idle" in content


def test_think_off_hidden_from_bar() -> None:
    content = _build(think="off")
    assert "think:off" not in content


def test_think_on_shown_in_bar() -> None:
    content = _build(think="on")
    assert "think:on" in content


def test_session_id_shown_as_badge_when_no_name() -> None:
    content = _build(session_id="abc12345def", session_name="")
    assert "#abc12345" in content


def test_framework_shown_when_non_direct() -> None:
    content = _build(framework="adk")
    assert "/adk" in content


def test_framework_direct_hidden() -> None:
    content = _build(framework="direct")
    assert "/direct" not in content
