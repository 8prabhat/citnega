"""
Token counters for the Model Gateway.

TiktokenCounter    — uses tiktoken if available (best accuracy for OpenAI models).
CharApproxCounter  — character-based heuristic (~4 chars/token); zero dependencies.
CompositeCounter   — tries tiktoken first, falls back to CharApproxCounter.

The gateway uses CompositeCounter by default so it works offline and
without optional tiktoken dependency.
"""

from __future__ import annotations

from citnega.packages.protocol.interfaces.token_counter import ITokenCounter
from citnega.packages.protocol.models.model_gateway import ModelMessage


# ---------------------------------------------------------------------------
# CharApproxCounter — always available, no dependencies
# ---------------------------------------------------------------------------

class CharApproxCounter(ITokenCounter):
    """
    Approximates token count as ``ceil(len(text) / 4)``.

    Error margin ±20% vs. tiktoken — sufficient for budget checks.
    """

    def count(self, text: str) -> int:
        return max(1, (len(text) + 3) // 4)

    def count_messages(self, messages: list[ModelMessage]) -> int:
        total = 0
        for msg in messages:
            # Role prefix overhead: ~4 tokens per message
            total += 4 + self.count(msg.content)
            if msg.name:
                total += self.count(msg.name)
        return total


# ---------------------------------------------------------------------------
# TiktokenCounter — tiktoken required
# ---------------------------------------------------------------------------

class TiktokenCounter(ITokenCounter):
    """
    Token counter using tiktoken (OpenAI's tokenizer).

    Falls back to CharApproxCounter for unknown encodings.
    """

    def __init__(self, encoding_name: str = "cl100k_base") -> None:
        try:
            import tiktoken  # type: ignore[import]
            self._enc = tiktoken.get_encoding(encoding_name)
        except ImportError:
            self._enc = None

    def count(self, text: str) -> int:
        if self._enc is None:
            return max(1, (len(text) + 3) // 4)
        return len(self._enc.encode(text, disallowed_special=()))

    def count_messages(self, messages: list[ModelMessage]) -> int:
        total = 0
        for msg in messages:
            total += 4  # per-message overhead
            total += self.count(msg.content)
            if msg.name:
                total += self.count(msg.name) + 1
        total += 2  # reply priming
        return total


# ---------------------------------------------------------------------------
# CompositeCounter — tries tiktoken, falls back gracefully
# ---------------------------------------------------------------------------

class CompositeTokenCounter(ITokenCounter):
    """
    Tries TiktokenCounter first; uses CharApproxCounter if tiktoken is
    not installed or the encoding is unavailable.
    """

    def __init__(self, model_id: str = "") -> None:
        # Map model families to tiktoken encodings
        encoding = "cl100k_base"
        if "gpt-4" in model_id or "gpt-3.5" in model_id or "text-" in model_id:
            encoding = "cl100k_base"
        elif "davinci" in model_id or "curie" in model_id:
            encoding = "r50k_base"

        try:
            counter = TiktokenCounter(encoding)
            if counter._enc is None:
                raise ImportError
            self._inner: ITokenCounter = counter
        except (ImportError, Exception):
            self._inner = CharApproxCounter()

    def count(self, text: str) -> int:
        return self._inner.count(text)

    def count_messages(self, messages: list[ModelMessage]) -> int:
        return self._inner.count_messages(messages)
