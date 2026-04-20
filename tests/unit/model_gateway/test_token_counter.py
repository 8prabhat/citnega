"""
Unit tests for token counter implementations.

Covers:
- CharApproxCounter: basic count, message counting, edge cases
- TiktokenCounter: falls back gracefully when tiktoken is unavailable
- CompositeTokenCounter: picks correct backend
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# ── CharApproxCounter ──────────────────────────────────────────────────────────


def test_char_approx_count_basic():
    from citnega.packages.model_gateway.token_counter import CharApproxCounter

    c = CharApproxCounter()
    assert c.count("abcd") == 1        # 4 chars = 1 token
    assert c.count("abcde") == 2       # 5 chars → ceil(5/4) = 2
    assert c.count("a" * 40) == 10     # 40 chars = 10 tokens
    assert c.count("") == 1            # minimum 1


def test_char_approx_count_empty_returns_one():
    from citnega.packages.model_gateway.token_counter import CharApproxCounter

    c = CharApproxCounter()
    assert c.count("") == 1


def test_char_approx_count_messages():
    from unittest.mock import MagicMock

    from citnega.packages.model_gateway.token_counter import CharApproxCounter

    c = CharApproxCounter()
    msg = MagicMock()
    msg.content = "Hello"
    msg.name = None
    # 4 (overhead) + count("Hello") = 4 + 2 = 6
    result = c.count_messages([msg])
    assert result == 4 + c.count("Hello")


def test_char_approx_count_messages_with_name():
    from unittest.mock import MagicMock

    from citnega.packages.model_gateway.token_counter import CharApproxCounter

    c = CharApproxCounter()
    msg = MagicMock()
    msg.content = "Hello"
    msg.name = "Alice"
    result = c.count_messages([msg])
    # 4 + count("Hello") + count("Alice")
    expected = 4 + c.count("Hello") + c.count("Alice")
    assert result == expected


def test_char_approx_count_multiple_messages():
    from unittest.mock import MagicMock

    from citnega.packages.model_gateway.token_counter import CharApproxCounter

    c = CharApproxCounter()
    msgs = []
    for i in range(3):
        m = MagicMock()
        m.content = "test"
        m.name = None
        msgs.append(m)
    # 3 * (4 + 1) = 15
    result = c.count_messages(msgs)
    assert result == 3 * (4 + c.count("test"))


# ── TiktokenCounter ────────────────────────────────────────────────────────────


def test_tiktoken_counter_falls_back_when_unavailable():
    """When tiktoken is not installed, TiktokenCounter uses char approximation."""
    from citnega.packages.model_gateway.token_counter import TiktokenCounter

    with patch.dict("sys.modules", {"tiktoken": None}):
        c = TiktokenCounter()
        # Should fall back to char approx
        assert c._enc is None
        result = c.count("Hello world")
        assert result >= 1


def test_tiktoken_counter_with_mock_enc():
    """TiktokenCounter uses enc.encode() when available."""
    from citnega.packages.model_gateway.token_counter import TiktokenCounter

    mock_enc = MagicMock()
    mock_enc.encode.return_value = [1, 2, 3, 4, 5]  # 5 tokens

    c = TiktokenCounter.__new__(TiktokenCounter)
    c._enc = mock_enc

    result = c.count("any text")
    assert result == 5
    mock_enc.encode.assert_called_once_with("any text", disallowed_special=())


def test_tiktoken_count_messages_with_mock():
    from unittest.mock import MagicMock

    from citnega.packages.model_gateway.token_counter import TiktokenCounter

    mock_enc = MagicMock()
    # Each encode call returns 3 tokens
    mock_enc.encode.return_value = [1, 2, 3]

    c = TiktokenCounter.__new__(TiktokenCounter)
    c._enc = mock_enc

    msg = MagicMock()
    msg.content = "Hello"
    msg.name = None
    # 4 (overhead) + 3 (encode result) + 2 (reply priming) = 9
    result = c.count_messages([msg])
    assert result == 4 + 3 + 2


def test_tiktoken_count_messages_with_name():
    from unittest.mock import MagicMock

    from citnega.packages.model_gateway.token_counter import TiktokenCounter

    mock_enc = MagicMock()
    mock_enc.encode.return_value = [1, 2]  # 2 tokens for any text

    c = TiktokenCounter.__new__(TiktokenCounter)
    c._enc = mock_enc

    msg = MagicMock()
    msg.content = "Hello"
    msg.name = "Alice"
    # 4 + count(content) + count(name) + 1 (name bonus) + 2 (reply)
    result = c.count_messages([msg])
    assert result == 4 + 2 + 2 + 1 + 2


# ── CompositeTokenCounter ──────────────────────────────────────────────────────


def test_composite_uses_char_approx_without_tiktoken():
    from citnega.packages.model_gateway.token_counter import (
        CharApproxCounter,
        CompositeTokenCounter,
    )

    with patch.dict("sys.modules", {"tiktoken": None}):
        c = CompositeTokenCounter()
        assert isinstance(c._inner, CharApproxCounter)


def test_composite_count_delegates_to_inner():
    from citnega.packages.model_gateway.token_counter import CompositeTokenCounter

    c = CompositeTokenCounter()
    result = c.count("Hello world")
    assert result >= 1


def test_composite_count_messages_delegates():
    from unittest.mock import MagicMock

    from citnega.packages.model_gateway.token_counter import CompositeTokenCounter

    c = CompositeTokenCounter()
    msg = MagicMock()
    msg.content = "test"
    msg.name = None
    result = c.count_messages([msg])
    assert result >= 1


def test_composite_gpt4_model_uses_cl100k():
    """GPT-4 model ID maps to cl100k_base encoding."""
    from citnega.packages.model_gateway.token_counter import CompositeTokenCounter

    # This just tests that it doesn't crash — tiktoken may or may not be installed
    c = CompositeTokenCounter(model_id="gpt-4-turbo")
    result = c.count("Test sentence")
    assert result >= 1
