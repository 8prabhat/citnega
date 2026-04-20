"""Tests for MatrixTool runner detection and command building."""

from __future__ import annotations

from pathlib import Path

import pytest

from citnega.packages.tools.builtin.test_matrix import MatrixTool


@pytest.fixture()
def tool() -> MatrixTool:
    return MatrixTool.__new__(MatrixTool)


def _create_files(tmp_path: Path, *names: str) -> None:
    for name in names:
        (tmp_path / name).touch()


class TestDetectRunner:
    def test_detects_go(self, tmp_path: Path, tool: MatrixTool) -> None:
        _create_files(tmp_path, "go.mod")
        assert tool._detect_runner(tmp_path) == "go"

    def test_detects_cargo(self, tmp_path: Path, tool: MatrixTool) -> None:
        _create_files(tmp_path, "Cargo.toml")
        assert tool._detect_runner(tmp_path) == "cargo"

    def test_detects_jest(self, tmp_path: Path, tool: MatrixTool) -> None:
        _create_files(tmp_path, "package.json")
        assert tool._detect_runner(tmp_path) == "jest"

    def test_detects_maven_pom(self, tmp_path: Path, tool: MatrixTool) -> None:
        _create_files(tmp_path, "pom.xml")
        assert tool._detect_runner(tmp_path) == "maven"

    def test_detects_maven_gradle(self, tmp_path: Path, tool: MatrixTool) -> None:
        _create_files(tmp_path, "build.gradle")
        assert tool._detect_runner(tmp_path) == "maven"

    def test_defaults_pytest(self, tmp_path: Path, tool: MatrixTool) -> None:
        assert tool._detect_runner(tmp_path) == "pytest"

    def test_go_takes_priority_over_package_json(self, tmp_path: Path, tool: MatrixTool) -> None:
        _create_files(tmp_path, "go.mod", "package.json")
        assert tool._detect_runner(tmp_path) == "go"


class TestBuildRunnerCommand:
    def test_pytest_command(self, tmp_path: Path, tool: MatrixTool) -> None:
        cmd = tool._build_runner_command("pytest", "tests/unit/test_foo.py", "-q", tmp_path)
        assert "pytest" in cmd
        assert "tests/unit/test_foo.py" in cmd

    def test_jest_command(self, tmp_path: Path, tool: MatrixTool) -> None:
        cmd = tool._build_runner_command("jest", "src/foo.test.js", "", tmp_path)
        assert "npx jest" in cmd
        assert "src/foo.test.js" in cmd

    def test_go_command(self, tmp_path: Path, tool: MatrixTool) -> None:
        cmd = tool._build_runner_command("go", "", "", tmp_path)
        assert "go test" in cmd

    def test_cargo_command(self, tmp_path: Path, tool: MatrixTool) -> None:
        cmd = tool._build_runner_command("cargo", "", "", tmp_path)
        assert "cargo test" in cmd

    def test_maven_command(self, tmp_path: Path, tool: MatrixTool) -> None:
        cmd = tool._build_runner_command("maven", "", "", tmp_path)
        assert "mvn test" in cmd

    def test_unknown_runner_falls_back_to_pytest(self, tmp_path: Path, tool: MatrixTool) -> None:
        cmd = tool._build_runner_command("unknown", "tests/test_x.py", "", tmp_path)
        assert "pytest" in cmd

    def test_pytest_uses_venv_if_available(self, tmp_path: Path, tool: MatrixTool) -> None:
        venv_pytest = tmp_path / ".venv" / "bin" / "pytest"
        venv_pytest.parent.mkdir(parents=True)
        venv_pytest.touch()
        cmd = tool._build_runner_command("pytest", "tests/test_x.py", "", tmp_path)
        assert str(venv_pytest) in cmd
