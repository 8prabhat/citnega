"""
ThinkingStreamParser — parses ``<think>…</think>`` blocks from a token stream.

Models such as DeepSeek R1, Qwen3-thinking, and QwQ embed their
chain-of-thought inside XML-like tags before the visible response.
Because LLM streaming chunks are arbitrary substrings (not whole words),
the open/close tags may be split across multiple chunks.  This parser
handles that correctly with a look-behind buffer.

Usage::

    parser = ThinkingStreamParser()

    # feed one streaming chunk at a time
    for chunk_text in raw_stream:
        for is_thinking, text in parser.feed(chunk_text):
            if is_thinking:
                # emit ThinkingEvent(token=text)
            else:
                # emit TokenEvent(token=text)

    # flush any held-back characters at end of stream
    for is_thinking, text in parser.flush():
        ...

The parser is intentionally stateful and single-use (one instance per
stream).  Do not reuse across turns.
"""

from __future__ import annotations

_OPEN_TAG = "<think>"
_CLOSE_TAG = "</think>"
_MAX_TAG_LEN = max(len(_OPEN_TAG), len(_CLOSE_TAG))


def _safe_flush_pos(text: str, tag: str) -> int:
    """
    Return how many leading characters of *text* can be safely flushed.

    If *text* ends with a non-empty prefix of *tag*, those trailing
    characters must stay in the buffer — they might be the start of the
    tag still being assembled from multiple chunks.

    Returns the number of characters that are safe to flush (0 … len(text)).
    """
    max_check = min(len(tag) - 1, len(text))
    for prefix_len in range(max_check, 0, -1):
        if text.endswith(tag[:prefix_len]):
            return len(text) - prefix_len
    return len(text)


class ThinkingStreamParser:
    """
    Stateful incremental parser for ``<think>…</think>`` tag pairs.

    Yields ``(is_thinking: bool, text: str)`` tuples via ``feed()`` and
    ``flush()``.  Empty strings are never yielded.
    """

    __slots__ = ("_in_thinking", "_pending")

    def __init__(self) -> None:
        self._in_thinking = False
        self._pending = ""

    # ── Public API ────────────────────────────────────────────────────────────

    def feed(self, chunk: str) -> list[tuple[bool, str]]:
        """
        Process one streaming chunk.

        Returns a list of ``(is_thinking, text)`` pairs.  The list may
        be empty if all characters are held in the look-behind buffer.
        """
        self._pending += chunk
        results: list[tuple[bool, str]] = []

        while self._pending:
            tag = _CLOSE_TAG if self._in_thinking else _OPEN_TAG
            pos = self._pending.find(tag)

            if pos == -1:
                # Tag not found — flush what is definitely not a partial tag
                safe = _safe_flush_pos(self._pending, tag)
                if safe > 0:
                    results.append((self._in_thinking, self._pending[:safe]))
                    self._pending = self._pending[safe:]
                break  # rest must wait for more chunks
            else:
                # Tag found — flush everything before it, then toggle mode
                if pos > 0:
                    results.append((self._in_thinking, self._pending[:pos]))
                self._pending = self._pending[pos + len(tag) :]
                self._in_thinking = not self._in_thinking
                # Continue loop — there may be another tag in the remainder

        return [(is_t, t) for (is_t, t) in results if t]  # drop empty strings

    def flush(self) -> list[tuple[bool, str]]:
        """
        Flush all buffered characters at end of stream.

        If the stream ended inside a ``<think>`` block (no closing tag),
        the remaining buffer is emitted as thinking content and the parser
        resets to non-thinking state.
        """
        if not self._pending:
            return []
        result = [(self._in_thinking, self._pending)]
        self._pending = ""
        self._in_thinking = False
        return result

    @property
    def in_thinking(self) -> bool:
        """True if the parser is currently inside a ``<think>`` block."""
        return self._in_thinking
