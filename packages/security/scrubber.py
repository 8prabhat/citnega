"""
LogScrubber — strips sensitive fields from log records before writing.

Applied as a structlog processor on every log record. Also used by the
EventEmitter before writing event JSONL.

Denylist field names (case-insensitive):
  api_key, token, secret, password, authorization, credential, bearer, auth

High-entropy string detection: strings >20 chars in denied fields → REDACTED.
"""

from __future__ import annotations

from collections.abc import Mapping
import math
import re
import string
from typing import Any

_REDACTED = "***REDACTED***"

# Field name patterns that should never appear in logs
_DENIED_FIELD_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"api[_-]?key",
        r"secret",
        r"password",
        r"passphrase",
        r"token",
        r"authorization",
        r"credential",
        r"bearer",
        r"\bauth\b",
    ]
]

_HIGH_ENTROPY_MIN_LENGTH = 20


def _is_denied_field(name: str) -> bool:
    return any(p.search(name) for p in _DENIED_FIELD_PATTERNS)


def _entropy(s: str) -> float:
    """Shannon entropy of a string (bits per character)."""
    if not s:
        return 0.0
    freq = {c: s.count(c) / len(s) for c in set(s)}
    return -sum(p * math.log2(p) for p in freq.values())


_PRINTABLE_CHARS = set(string.printable)


def _looks_like_secret(value: str) -> bool:
    """Heuristic: long, high-entropy string of printable characters."""
    return (
        isinstance(value, str)
        and len(value) >= _HIGH_ENTROPY_MIN_LENGTH
        and all(c in _PRINTABLE_CHARS for c in value)
        and _entropy(value) > 3.5  # bits; random base64 ≈ 6 bits
    )


def _scrub_value(value: Any, field_name: str = "") -> Any:
    """
    Recursively scrub a value.

    If ``field_name`` is in the denylist and the value is a non-empty string,
    always redact. Otherwise, redact only if it looks like a secret.
    """
    if isinstance(value, str):
        if _is_denied_field(field_name) and value:
            return _REDACTED
        if _looks_like_secret(value) and _is_denied_field(field_name):
            return _REDACTED
        return value
    if isinstance(value, Mapping):
        return {k: _scrub_value(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        scrubbed = [_scrub_value(item) for item in value]
        return type(value)(scrubbed)
    return value


def scrub_dict(record: dict[str, Any]) -> dict[str, Any]:
    """Scrub a flat or nested dict in-place (returns a new dict)."""
    return {k: _scrub_value(v, str(k)) for k, v in record.items()}


class LogScrubber:
    """
    Structlog processor that redacts sensitive fields.

    Usage::

        structlog.configure(
            processors=[
                LogScrubber(),
                ...
            ]
        )
    """

    def __call__(
        self,
        logger: Any,
        method: str,
        event_dict: dict[str, Any],
    ) -> dict[str, Any]:
        return scrub_dict(event_dict)
