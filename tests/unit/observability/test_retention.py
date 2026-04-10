"""Unit tests for log retention."""

from __future__ import annotations

import gzip
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from citnega.packages.observability.retention import _rotate_sync


def _log_file(log_dir: Path, days_ago: int) -> Path:
    date = (datetime.now(tz=timezone.utc) - timedelta(days=days_ago)).date().isoformat()
    p = log_dir / f"{date}.jsonl"
    p.write_text('{"event": "test"}\n')
    return p


class TestRotateSync:
    def test_old_log_compressed(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "app"
        log_dir.mkdir()
        f = _log_file(log_dir, 2)
        _rotate_sync(log_dir, retention_days=30)
        gz = f.with_suffix(".jsonl.gz")
        assert gz.exists()
        assert not f.exists()

    def test_today_log_not_touched(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "app"
        log_dir.mkdir()
        today = datetime.now(tz=timezone.utc).date().isoformat()
        f = log_dir / f"{today}.jsonl"
        f.write_text('{"event": "today"}\n')
        _rotate_sync(log_dir, retention_days=30)
        assert f.exists()

    def test_old_log_deleted_after_retention(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "app"
        log_dir.mkdir()
        f = _log_file(log_dir, 40)
        _rotate_sync(log_dir, retention_days=30)
        assert not f.exists()
        assert not f.with_suffix(".jsonl.gz").exists()

    def test_compressed_file_readable(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "app"
        log_dir.mkdir()
        f = _log_file(log_dir, 2)
        original_content = f.read_bytes()
        _rotate_sync(log_dir, retention_days=30)
        gz = f.with_suffix(".jsonl.gz")
        with gzip.open(gz, "rb") as fh:
            recovered = fh.read()
        assert recovered == original_content

    def test_empty_dir_no_error(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "app"
        log_dir.mkdir()
        _rotate_sync(log_dir, retention_days=30)  # should not raise

    def test_nonexistent_dir_no_error(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "nonexistent"
        _rotate_sync(log_dir, retention_days=30)  # should not raise
