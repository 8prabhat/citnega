"""Performance: SearchFilesTool must scan a 1000-file tree in < 500ms."""

from __future__ import annotations

import asyncio
from pathlib import Path
import time

from citnega.packages.tools.builtin.search_files import SearchFilesInput, SearchFilesTool


def _build_large_tree(root: Path, n_files: int = 1000) -> None:
    """Create n_files spread across subdirectories."""
    per_dir = 50
    n_dirs = (n_files + per_dir - 1) // per_dir
    created = 0
    for d in range(n_dirs):
        subdir = root / f"dir_{d}"
        subdir.mkdir(exist_ok=True)
        for f in range(per_dir):
            if created >= n_files:
                break
            (subdir / f"file_{f}.py").write_text(
                f"# file {created}\nVALUE = {created}\n",
                encoding="utf-8",
            )
            created += 1


class TestSearchFilesLatency:
    """SearchFilesTool latency on a large file tree."""

    def test_1000_file_tree_under_500ms(self, tmp_path: Path) -> None:
        _build_large_tree(tmp_path, n_files=1000)
        tool = SearchFilesTool.__new__(SearchFilesTool)

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
            return await tool._execute(
                SearchFilesInput(root_path=str(tmp_path), pattern="VALUE"),
                ctx,
            )

        start = time.monotonic()
        result = asyncio.run(run())
        elapsed_ms = (time.monotonic() - start) * 1000

        assert hasattr(result, "result")  # ToolOutput.result contains the output text
        assert elapsed_ms < 500.0, (
            f"search_files took {elapsed_ms:.1f}ms for 1000-file tree (limit: 500ms)"
        )

    def test_glob_only_under_200ms(self, tmp_path: Path) -> None:
        """Pure glob (no content search) should be faster."""
        _build_large_tree(tmp_path, n_files=500)
        tool = SearchFilesTool.__new__(SearchFilesTool)

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
            return await tool._execute(
                SearchFilesInput(root_path=str(tmp_path), pattern="nonexistent_zzz", glob_filter="**/*.py"),
                ctx,
            )

        start = time.monotonic()
        asyncio.run(run())
        elapsed_ms = (time.monotonic() - start) * 1000

        assert elapsed_ms < 200.0, (
            f"search_files (glob-only) took {elapsed_ms:.1f}ms for 500-file tree (limit: 200ms)"
        )
