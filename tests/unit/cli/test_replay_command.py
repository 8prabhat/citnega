"""
FR-OBS-001 — Event replay tool tests.

Tests: happy path, missing log, empty log, --json, --critical-only, --event-log-dir.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from citnega.apps.cli.commands.replay import app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_jsonl(path: Path, events: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(ev) for ev in events) + "\n",
        encoding="utf-8",
    )


def _make_events(*types: str) -> list[dict]:
    return [
        {"event_type": t, "timestamp": f"2024-01-01T10:00:0{i}.000Z"}
        for i, t in enumerate(types)
    ]


def _patch_resolver(log_path: Path | None):
    """Patch PathResolver so it returns *log_path* for any run_id."""
    resolver = MagicMock()
    resolver.event_log_path.return_value = log_path
    return patch(
        "citnega.packages.storage.path_resolver.PathResolver",
        return_value=resolver,
    )


# ---------------------------------------------------------------------------
# Basic happy path
# ---------------------------------------------------------------------------


class TestReplayHappyPath:
    def test_human_output_contains_run_id(self, tmp_path: Path) -> None:
        log = tmp_path / "run-abc.jsonl"
        _write_jsonl(log, _make_events("RunStateEvent", "RunCompleteEvent"))

        runner = CliRunner()
        result = runner.invoke(app, ["--run-id", "run-abc", "--event-log-dir", str(tmp_path)])

        assert result.exit_code == 0
        assert "run-abc" in result.output

    def test_human_output_shows_state_transition(self, tmp_path: Path) -> None:
        log = tmp_path / "run-1.jsonl"
        _write_jsonl(
            log,
            [
                {
                    "event_type": "RunStateEvent",
                    "timestamp": "2024-01-01T10:00:00.000Z",
                    "from_state": "PENDING",
                    "to_state": "RUNNING",
                }
            ],
        )

        runner = CliRunner()
        result = runner.invoke(app, ["--run-id", "run-1", "--event-log-dir", str(tmp_path)])

        assert result.exit_code == 0
        assert "PENDING" in result.output
        assert "RUNNING" in result.output

    def test_human_output_shows_complete(self, tmp_path: Path) -> None:
        log = tmp_path / "run-2.jsonl"
        _write_jsonl(
            log,
            [
                {
                    "event_type": "RunCompleteEvent",
                    "timestamp": "2024-01-01T10:00:00.000Z",
                    "final_state": "COMPLETED",
                }
            ],
        )

        runner = CliRunner()
        result = runner.invoke(app, ["--run-id", "run-2", "--event-log-dir", str(tmp_path)])

        assert result.exit_code == 0
        assert "COMPLETE" in result.output
        assert "COMPLETED" in result.output

    def test_human_output_shows_callable_start_end(self, tmp_path: Path) -> None:
        log = tmp_path / "run-3.jsonl"
        _write_jsonl(
            log,
            [
                {
                    "event_type": "CallableStartEvent",
                    "timestamp": "2024-01-01T10:00:00.000Z",
                    "callable_name": "my_tool",
                },
                {
                    "event_type": "CallableEndEvent",
                    "timestamp": "2024-01-01T10:00:01.000Z",
                    "callable_name": "my_tool",
                },
            ],
        )

        runner = CliRunner()
        result = runner.invoke(app, ["--run-id", "run-3", "--event-log-dir", str(tmp_path)])

        assert result.exit_code == 0
        assert "START" in result.output
        assert "END" in result.output
        assert "my_tool" in result.output

    def test_token_events_printed_inline(self, tmp_path: Path) -> None:
        log = tmp_path / "run-4.jsonl"
        _write_jsonl(
            log,
            [
                {"event_type": "TokenEvent", "timestamp": "2024-01-01T10:00:00.000Z", "token": "Hello"},
                {"event_type": "TokenEvent", "timestamp": "2024-01-01T10:00:00.001Z", "token": " world"},
            ],
        )

        runner = CliRunner()
        result = runner.invoke(app, ["--run-id", "run-4", "--event-log-dir", str(tmp_path)])

        assert result.exit_code == 0
        assert "Hello" in result.output
        assert "world" in result.output


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


class TestReplayErrors:
    def test_missing_log_exits_nonzero(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            app, ["--run-id", "no-such-run", "--event-log-dir", str(tmp_path)]
        )

        assert result.exit_code != 0

    def test_empty_log_exits_nonzero(self, tmp_path: Path) -> None:
        log = tmp_path / "empty-run.jsonl"
        log.write_text("", encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(
            app, ["--run-id", "empty-run", "--event-log-dir", str(tmp_path)]
        )

        assert result.exit_code != 0

    def test_resolver_failure_exits_nonzero(self) -> None:
        """When PathResolver raises, it should exit nonzero (no log found)."""
        with patch(
            "citnega.packages.storage.path_resolver.PathResolver",
            side_effect=ImportError("no storage"),
        ):
            runner = CliRunner()
            result = runner.invoke(app, ["--run-id", "run-xyz"])

        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# --json flag
# ---------------------------------------------------------------------------


class TestReplayJsonOutput:
    def test_json_flag_emits_json_lines(self, tmp_path: Path) -> None:
        log = tmp_path / "run-j.jsonl"
        _write_jsonl(log, _make_events("RunStateEvent", "RunCompleteEvent"))

        runner = CliRunner()
        result = runner.invoke(
            app, ["--run-id", "run-j", "--json", "--event-log-dir", str(tmp_path)]
        )

        assert result.exit_code == 0
        # Lines starting with '{' are JSON events (header line goes to stderr)
        json_lines = [ln for ln in result.output.strip().splitlines() if ln.startswith("{")]
        assert len(json_lines) >= 2
        for line in json_lines:
            obj = json.loads(line)
            assert "event_type" in obj

    def test_json_flag_preserves_all_fields(self, tmp_path: Path) -> None:
        log = tmp_path / "run-jf.jsonl"
        event = {"event_type": "RunStateEvent", "from_state": "A", "to_state": "B", "extra": 42}
        _write_jsonl(log, [event])

        runner = CliRunner()
        result = runner.invoke(
            app, ["--run-id", "run-jf", "--json", "--event-log-dir", str(tmp_path)]
        )

        assert result.exit_code == 0
        json_lines = [ln for ln in result.output.strip().splitlines() if ln.startswith("{")]
        assert len(json_lines) == 1
        parsed = json.loads(json_lines[0])
        assert parsed["extra"] == 42
        assert parsed["from_state"] == "A"


# ---------------------------------------------------------------------------
# --critical-only flag
# ---------------------------------------------------------------------------


class TestReplayCriticalOnly:
    def test_critical_only_filters_non_critical(self, tmp_path: Path) -> None:
        log = tmp_path / "run-c.jsonl"
        events = [
            {"event_type": "SomeNoisyEvent", "timestamp": "2024-01-01T10:00:00.000Z"},
            {
                "event_type": "RunCompleteEvent",
                "timestamp": "2024-01-01T10:00:01.000Z",
                "final_state": "COMPLETED",
            },
        ]
        _write_jsonl(log, events)

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["--run-id", "run-c", "--critical-only", "--event-log-dir", str(tmp_path)],
        )

        assert result.exit_code == 0
        assert "SomeNoisyEvent" not in result.output
        assert "COMPLETE" in result.output

    def test_critical_only_keeps_approval_events(self, tmp_path: Path) -> None:
        log = tmp_path / "run-ca.jsonl"
        _write_jsonl(
            log,
            [
                {
                    "event_type": "ApprovalRequestEvent",
                    "timestamp": "2024-01-01T10:00:00.000Z",
                    "action": "pending",
                },
            ],
        )

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["--run-id", "run-ca", "--critical-only", "--event-log-dir", str(tmp_path)],
        )

        assert result.exit_code == 0
        assert "APPROVAL" in result.output

    def test_critical_only_with_json_filters_too(self, tmp_path: Path) -> None:
        log = tmp_path / "run-cj.jsonl"
        events = [
            {"event_type": "NoiseEvent"},
            {"event_type": "RouterDecisionEvent", "selected_target": "agent_x"},
        ]
        _write_jsonl(log, events)

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "--run-id",
                "run-cj",
                "--critical-only",
                "--json",
                "--event-log-dir",
                str(tmp_path),
            ],
        )

        assert result.exit_code == 0
        lines = [ln for ln in result.output.strip().splitlines() if ln.startswith("{")]
        assert len(lines) == 1
        obj = json.loads(lines[0])
        assert obj["event_type"] == "RouterDecisionEvent"


# ---------------------------------------------------------------------------
# PathResolver integration
# ---------------------------------------------------------------------------


class TestReplayPathResolver:
    def test_uses_resolver_when_no_override(self, tmp_path: Path) -> None:
        log = tmp_path / "run-pr.jsonl"
        _write_jsonl(log, _make_events("RunCompleteEvent"))

        with _patch_resolver(log):
            runner = CliRunner()
            result = runner.invoke(app, ["--run-id", "run-pr"])

        assert result.exit_code == 0

    def test_override_takes_precedence_over_resolver(self, tmp_path: Path) -> None:
        log = tmp_path / "run-ov.jsonl"
        _write_jsonl(log, _make_events("RunCompleteEvent"))

        # Resolver would return a non-existent path; override should win
        with _patch_resolver(tmp_path / "nonexistent" / "run-ov.jsonl"):
            runner = CliRunner()
            result = runner.invoke(
                app, ["--run-id", "run-ov", "--event-log-dir", str(tmp_path)]
            )

        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Malformed lines
# ---------------------------------------------------------------------------


class TestReplayMalformedLines:
    def test_malformed_lines_are_skipped(self, tmp_path: Path) -> None:
        log = tmp_path / "run-mal.jsonl"
        log.write_text(
            '{"event_type": "RunCompleteEvent", "final_state": "COMPLETED"}\n'
            "NOT VALID JSON\n"
            '{"event_type": "RunStateEvent"}\n',
            encoding="utf-8",
        )

        runner = CliRunner()
        result = runner.invoke(
            app, ["--run-id", "run-mal", "--event-log-dir", str(tmp_path)]
        )

        # Still exits 0 — bad lines are warned, not fatal
        assert result.exit_code == 0
