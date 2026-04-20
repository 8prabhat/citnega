"""
Integration test fixtures.

live_app: minimal real ApplicationService with SQLite in a tmp dir.
git_repo: real git repo for git_ops / ambient context tests.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


@pytest.fixture
async def live_app(tmp_path: Path):
    """Spin up a minimal real ApplicationService with SQLite in tmp_path."""
    from citnega.packages.bootstrap.bootstrap import create_application

    async with create_application(
        db_path=tmp_path / "test.db",
        app_home=tmp_path,
        skip_provider_health_check=True,
    ) as app:
        yield app


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a real git repo for git_ops / ambient context tests."""
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path, check=True, capture_output=True,
    )
    return tmp_path
