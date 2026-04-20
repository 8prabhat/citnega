"""Tests for RepoMapTool multi-stack detection."""

from __future__ import annotations

from pathlib import Path

import pytest

from citnega.packages.tools.builtin.repo_map import RepoMapTool


@pytest.fixture()
def tool() -> RepoMapTool:
    return RepoMapTool.__new__(RepoMapTool)


def _create_files(tmp_path: Path, *names: str) -> None:
    for name in names:
        (tmp_path / name).touch()


def test_detects_python_stack(tmp_path: Path, tool: RepoMapTool) -> None:
    _create_files(tmp_path, "pyproject.toml")
    stacks = tool._detect_stacks(tmp_path)
    assert "python" in stacks


def test_detects_node_stack(tmp_path: Path, tool: RepoMapTool) -> None:
    _create_files(tmp_path, "package.json")
    stacks = tool._detect_stacks(tmp_path)
    assert "node" in stacks


def test_detects_go_stack(tmp_path: Path, tool: RepoMapTool) -> None:
    _create_files(tmp_path, "go.mod")
    stacks = tool._detect_stacks(tmp_path)
    assert "go" in stacks


def test_detects_rust_stack(tmp_path: Path, tool: RepoMapTool) -> None:
    _create_files(tmp_path, "Cargo.toml")
    stacks = tool._detect_stacks(tmp_path)
    assert "rust" in stacks


def test_detects_multiple_stacks(tmp_path: Path, tool: RepoMapTool) -> None:
    _create_files(tmp_path, "pyproject.toml", "package.json")
    stacks = tool._detect_stacks(tmp_path)
    assert "python" in stacks
    assert "node" in stacks


def test_empty_directory_no_stacks(tmp_path: Path, tool: RepoMapTool) -> None:
    stacks = tool._detect_stacks(tmp_path)
    assert stacks == []


def test_detects_dotnet_stack(tmp_path: Path, tool: RepoMapTool) -> None:
    (tmp_path / "MyApp.csproj").touch()
    stacks = tool._detect_stacks(tmp_path)
    assert "dotnet" in stacks


def test_detects_ruby_stack(tmp_path: Path, tool: RepoMapTool) -> None:
    _create_files(tmp_path, "Gemfile")
    stacks = tool._detect_stacks(tmp_path)
    assert "ruby" in stacks
