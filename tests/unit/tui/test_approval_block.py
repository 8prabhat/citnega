"""Unit tests for ApprovalBlock keyboard shortcut logic."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from citnega.apps.tui.widgets.approval_block import ApprovalBlock


def _make_block(approval_id: str = "ap-1") -> ApprovalBlock:
    block = ApprovalBlock.__new__(ApprovalBlock)
    block._approval_id = approval_id
    block._callable_name = "read_file"
    block._input_summary = "file_path=/tmp/test.txt"
    block._resolved = False
    return block


def test_resolve_approve_sets_resolved() -> None:
    block = _make_block()
    posted = []
    with (
        patch.object(block, "_collapse"),
        patch.object(block, "post_message", side_effect=posted.append),
    ):
        block._resolve(approved=True)

    assert block._resolved is True
    assert len(posted) == 1
    msg = posted[0]
    assert isinstance(msg, ApprovalBlock.Resolved)
    assert msg.approved is True
    assert msg.approval_id == "ap-1"


def test_resolve_deny_sets_resolved() -> None:
    block = _make_block()
    posted = []
    with (
        patch.object(block, "_collapse"),
        patch.object(block, "post_message", side_effect=posted.append),
    ):
        block._resolve(approved=False)

    assert block._resolved is True
    assert posted[0].approved is False


def test_double_resolve_ignored_via_on_key() -> None:
    """on_key guards against double-resolve by checking _resolved flag first."""
    block = _make_block()
    block._resolved = True
    posted = []
    with patch.object(block, "post_message", side_effect=posted.append):
        key_event = MagicMock()
        key_event.key = "y"
        block.on_key(key_event)
    assert len(posted) == 0


def test_on_key_y_approves() -> None:
    block = _make_block()
    resolved_calls: list[dict] = []

    def _fake_resolve(*, approved: bool) -> None:
        resolved_calls.append({"approved": approved})

    with patch.object(block, "_resolve", side_effect=_fake_resolve):
        key_event = MagicMock()
        key_event.key = "y"
        block.on_key(key_event)

    assert resolved_calls == [{"approved": True}]
    key_event.stop.assert_called_once()


def test_on_key_n_denies() -> None:
    block = _make_block()
    resolved_calls: list[dict] = []

    def _fake_resolve(*, approved: bool) -> None:
        resolved_calls.append({"approved": approved})

    with patch.object(block, "_resolve", side_effect=_fake_resolve):
        key_event = MagicMock()
        key_event.key = "n"
        block.on_key(key_event)

    assert resolved_calls == [{"approved": False}]


def test_on_key_escape_denies() -> None:
    block = _make_block()
    resolved_calls: list[dict] = []

    def _fake_resolve(*, approved: bool) -> None:
        resolved_calls.append({"approved": approved})

    with patch.object(block, "_resolve", side_effect=_fake_resolve):
        key_event = MagicMock()
        key_event.key = "escape"
        block.on_key(key_event)

    assert resolved_calls == [{"approved": False}]


def test_on_key_a_approves() -> None:
    block = _make_block()
    resolved_calls: list[dict] = []

    def _fake_resolve(*, approved: bool) -> None:
        resolved_calls.append({"approved": approved})

    with patch.object(block, "_resolve", side_effect=_fake_resolve):
        key_event = MagicMock()
        key_event.key = "a"
        block.on_key(key_event)

    assert resolved_calls == [{"approved": True}]
