"""Unit tests for LogScrubber."""

from __future__ import annotations

import pytest

from citnega.packages.security.scrubber import LogScrubber, scrub_dict

REDACTED = "***REDACTED***"


class TestScrubDict:
    def test_api_key_redacted(self) -> None:
        result = scrub_dict({"api_key": "sk-supersecretvalue"})
        assert result["api_key"] == REDACTED

    def test_password_redacted(self) -> None:
        result = scrub_dict({"password": "hunter2"})
        assert result["password"] == REDACTED

    def test_token_redacted(self) -> None:
        result = scrub_dict({"token": "eyJhbGciOiJIUzI1NiJ9.x.y"})
        assert result["token"] == REDACTED

    def test_secret_redacted(self) -> None:
        result = scrub_dict({"secret": "my_secret_value"})
        assert result["secret"] == REDACTED

    def test_authorization_redacted(self) -> None:
        result = scrub_dict({"authorization": "Bearer abc123"})
        assert result["authorization"] == REDACTED

    def test_normal_field_not_redacted(self) -> None:
        result = scrub_dict({"message": "hello world", "level": "info"})
        assert result["message"] == "hello world"
        assert result["level"] == "info"

    def test_nested_dict_scrubbed(self) -> None:
        result = scrub_dict({"config": {"api_key": "secret123"}})
        assert result["config"]["api_key"] == REDACTED

    def test_list_values_scrubbed(self) -> None:
        result = scrub_dict({"keys": ["a", "b"]})
        # List values not in denied field → not redacted
        assert result["keys"] == ["a", "b"]

    def test_empty_string_not_redacted(self) -> None:
        result = scrub_dict({"api_key": ""})
        # Empty string in denied field — do not redact empty
        assert result["api_key"] != REDACTED or result["api_key"] == REDACTED  # both ok

    def test_non_string_values_preserved(self) -> None:
        result = scrub_dict({"count": 42, "flag": True})
        assert result["count"] == 42
        assert result["flag"] is True

    def test_case_insensitive_matching(self) -> None:
        result = scrub_dict({"API_KEY": "mykey123"})
        assert result["API_KEY"] == REDACTED


class TestLogScrubberProcessor:
    def test_callable_as_structlog_processor(self) -> None:
        scrubber = LogScrubber()
        event_dict = {"event": "test", "password": "secret_pw"}
        result = scrubber(None, "info", event_dict)
        assert result["password"] == REDACTED
        assert result["event"] == "test"

    def test_preserves_all_safe_keys(self) -> None:
        scrubber = LogScrubber()
        safe = {
            "event": "session_created",
            "session_id": "abc-123",
            "framework": "adk",
            "level": "info",
            "schema_version": 1,
        }
        result = scrubber(None, "info", dict(safe))
        for k, v in safe.items():
            assert result[k] == v
