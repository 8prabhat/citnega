"""Performance: RepoMapTool scan of a medium Python repo must complete in < 3s."""

from __future__ import annotations

import asyncio
from pathlib import Path
import time

from citnega.packages.tools.builtin.repo_map import RepoMapInput, RepoMapTool


def _build_medium_repo(root: Path, n_files: int = 50) -> None:
    """Create a synthetic Python repo with n_files modules."""
    src = root / "src"
    src.mkdir()
    tests = root / "tests"
    tests.mkdir()
    for i in range(n_files // 2):
        module = src / f"module_{i}.py"
        module.write_text(
            f"\"\"\"Module {i}.\"\"\"\n\n"
            f"class Class{i}:\n"
            f"    def method(self) -> str:\n"
            f"        return 'result_{i}'\n\n"
            f"def func_{i}(x: int) -> int:\n"
            f"    return x * {i}\n",
            encoding="utf-8",
        )
    for i in range(n_files // 2):
        test_file = tests / f"test_module_{i}.py"
        test_file.write_text(
            f"from src.module_{i} import func_{i}\n\n"
            f"def test_func_{i}():\n"
            f"    assert func_{i}(1) == {i}\n",
            encoding="utf-8",
        )
    (root / "README.md").write_text("# Test repo\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        "[project]\nname = 'test'\nversion = '0.1.0'\n",
        encoding="utf-8",
    )


class TestRepoMapLatency:
    """RepoMapTool latency on a medium Python repo."""

    def test_50_file_repo_under_3s(self, tmp_path: Path) -> None:
        _build_medium_repo(tmp_path, n_files=50)
        tool = RepoMapTool.__new__(RepoMapTool)

        async def run():
            from citnega.packages.protocol.callables.context import CallContext
            from citnega.packages.protocol.callables.types import CallableType
            from citnega.packages.protocol.models.sessions import SessionConfig

            ctx = CallContext(
                run_id="perf-run",
                session_id="perf-sess",
                turn_id="perf-turn",
                session_config=SessionConfig(
                    session_id="perf-sess",
                    name="perf",
                    framework="direct",
                    default_model_id="x",
                ),
                callable_type=CallableType.TOOL,
            )
            return await tool._execute(RepoMapInput(root_path=str(tmp_path)), ctx)

        start = time.monotonic()
        result = asyncio.run(run())
        elapsed = time.monotonic() - start

        assert result.root_path  # scan completed
        assert elapsed < 3.0, f"repo_map took {elapsed:.2f}s for 50-file repo (limit: 3s)"

    def test_100_file_repo_under_5s(self, tmp_path: Path) -> None:
        _build_medium_repo(tmp_path, n_files=100)
        tool = RepoMapTool.__new__(RepoMapTool)

        async def run():
            from citnega.packages.protocol.callables.context import CallContext
            from citnega.packages.protocol.callables.types import CallableType
            from citnega.packages.protocol.models.sessions import SessionConfig

            ctx = CallContext(
                run_id="perf-run",
                session_id="perf-sess",
                turn_id="perf-turn",
                session_config=SessionConfig(
                    session_id="perf-sess",
                    name="perf",
                    framework="direct",
                    default_model_id="x",
                ),
                callable_type=CallableType.TOOL,
            )
            return await tool._execute(RepoMapInput(root_path=str(tmp_path)), ctx)

        start = time.monotonic()
        result = asyncio.run(run())
        elapsed = time.monotonic() - start

        assert result.root_path
        assert elapsed < 5.0, f"repo_map took {elapsed:.2f}s for 100-file repo (limit: 5s)"
