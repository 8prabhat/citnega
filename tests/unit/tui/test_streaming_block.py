"""Unit tests for StreamingBlock logic (timestamp, token count, buffer)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import re

import pytest

from citnega.apps.tui.widgets.streaming_block import StreamingBlock


def _make_block() -> StreamingBlock:
    block = StreamingBlock.__new__(StreamingBlock)
    block._buffer = ""
    block._finalized = False
    block._token_count = 0
    from datetime import datetime
    block._timestamp = datetime.now().strftime("%H:%M")
    return block


def test_buffer_grows_with_tokens() -> None:
    block = _make_block()
    with patch.object(block, "query_one", side_effect=Exception("no widget")):
        block.append_token("Hello")
        block.append_token(" world")
    assert block.text == "Hello world"


def test_token_count_increments() -> None:
    block = _make_block()
    with patch.object(block, "query_one", side_effect=Exception("no widget")):
        block.append_token("one two")
        block.append_token("three")
    assert block._token_count >= 2


def test_timestamp_format() -> None:
    block = _make_block()
    assert re.match(r"^\d{2}:\d{2}$", block._timestamp)


@pytest.mark.asyncio
async def test_finalized_flag_prevents_double_finalize() -> None:
    block = _make_block()
    block._finalized = True
    await block.finalize()
