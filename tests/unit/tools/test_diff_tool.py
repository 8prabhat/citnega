"""Tests for DiffTool."""

from __future__ import annotations

import pytest

from citnega.packages.tools.builtin.diff_tool import DiffInput, DiffTool


@pytest.fixture()
def tool():
    return DiffTool.__new__(DiffTool)


async def test_identical_strings_reports_no_diff(tool) -> None:
    result = await tool._execute(DiffInput(text_a="hello\n", text_b="hello\n"), context=None)
    assert result.is_identical
    assert result.additions == 0
    assert result.deletions == 0


async def test_added_line_counted(tool) -> None:
    result = await tool._execute(
        DiffInput(text_a="line1\n", text_b="line1\nline2\n"), context=None
    )
    assert not result.is_identical
    assert result.additions >= 1
    assert result.deletions == 0


async def test_deleted_line_counted(tool) -> None:
    result = await tool._execute(
        DiffInput(text_a="line1\nline2\n", text_b="line1\n"), context=None
    )
    assert result.deletions >= 1
    assert result.additions == 0


async def test_diff_text_is_unified_format(tool) -> None:
    result = await tool._execute(
        DiffInput(text_a="old\n", text_b="new\n", label_a="old.txt", label_b="new.txt"),
        context=None,
    )
    assert "---" in result.diff_text
    assert "+++" in result.diff_text
    assert "-old" in result.diff_text
    assert "+new" in result.diff_text


async def test_file_mode(tool, tmp_path) -> None:
    file_a = tmp_path / "a.txt"
    file_b = tmp_path / "b.txt"
    file_a.write_text("alpha\n")
    file_b.write_text("beta\n")

    result = await tool._execute(
        DiffInput(file_a=str(file_a), file_b=str(file_b)), context=None
    )
    assert not result.is_identical
    assert result.additions >= 1
    assert result.deletions >= 1
