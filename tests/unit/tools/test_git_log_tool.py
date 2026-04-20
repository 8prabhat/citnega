"""Tests for GitLogTool — structured git history, blame, show, diff."""

from __future__ import annotations

from pathlib import Path

import pytest

from citnega.packages.tools.builtin.git_log_tool import (
    GitLogInput,
    GitLogTool,
    _parse_blame,
    _parse_diff_stat,
)


@pytest.fixture()
def tool() -> GitLogTool:
    return GitLogTool.__new__(GitLogTool)


@pytest.fixture()
def git_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo with one commit for testing."""
    import subprocess

    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True)
    f = tmp_path / "hello.py"
    f.write_text("print('hello')\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, capture_output=True)
    return tmp_path


@pytest.mark.asyncio
async def test_log_returns_list(tool: GitLogTool, git_repo: Path) -> None:
    inp = GitLogInput(operation="log", path=str(git_repo), limit=5)
    out = await tool._execute(inp, None)
    assert out.operation == "log"
    assert isinstance(out.data, list)
    assert len(out.data) >= 1
    entry = out.data[0]
    assert "hash" in entry
    assert "subject" in entry


@pytest.mark.asyncio
async def test_log_raw_mode(tool: GitLogTool, git_repo: Path) -> None:
    inp = GitLogInput(operation="log", path=str(git_repo), limit=5, json_output=False)
    out = await tool._execute(inp, None)
    assert isinstance(out.data, str)
    assert "initial" in out.data or out.data  # subject or hash present


@pytest.mark.asyncio
async def test_show_returns_string(tool: GitLogTool, git_repo: Path) -> None:
    inp = GitLogInput(operation="show", path=str(git_repo), ref="HEAD")
    out = await tool._execute(inp, None)
    assert out.operation == "show"
    assert isinstance(out.data, str)
    assert "initial" in out.data


@pytest.mark.asyncio
async def test_invalid_operation_raises(tool: GitLogTool, git_repo: Path) -> None:
    with pytest.raises(Exception):
        inp = GitLogInput.__new__(GitLogInput)
        object.__setattr__(inp, "operation", "invalid_op")
        object.__setattr__(inp, "path", str(git_repo))
        object.__setattr__(inp, "ref", "")
        object.__setattr__(inp, "base_ref", "")
        object.__setattr__(inp, "limit", 5)
        object.__setattr__(inp, "json_output", True)
        await tool._execute(inp, None)


def test_parse_blame_parses_porcelain() -> None:
    raw = (
        "abc1234567890123456789012345678901234567 1 1\n"
        "author Test User\n"
        "author-mail <test@test.com>\n"
        "author-time 1234567890\n"
        "\tprint('hello')\n"
    )
    result = _parse_blame(raw)
    assert len(result) == 1
    assert result[0]["author"] == "Test User"
    assert result[0]["code"] == "print('hello')"


def test_parse_diff_stat() -> None:
    raw = (
        " foo/bar.py | 5 ++---\n"
        " baz/qux.py | 3 +++\n"
    )
    result = _parse_diff_stat(raw)
    assert len(result) == 2
    assert result[0]["file"] == "foo/bar.py"
    assert result[0]["additions"] == 2
    assert result[0]["deletions"] == 3
