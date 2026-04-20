"""test_matrix — discover and optionally execute categorized test suites."""

from __future__ import annotations

import asyncio
from collections import defaultdict
import os
from pathlib import Path
import time
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.shared.errors import CallableError
from citnega.packages.tools.builtin._cache_utils import (
    cache_file,
    file_tree_signature,
    git_state_fingerprint,
    load_json_cache,
    stable_hash,
    write_json_cache,
)
from citnega.packages.tools.builtin._tool_base import tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class MatrixRunResult(BaseModel):
    bucket: str
    command: str
    return_code: int
    duration_ms: int
    stdout_tail: str = ""
    stderr_tail: str = ""


class MatrixInput(BaseModel):
    root_path: str = Field(
        default="",
        description="Repository root. Empty means current working directory.",
    )
    execute: bool = Field(
        default=False,
        description="When true, runs one test command per discovered bucket.",
    )
    runner: str = Field(
        default="auto",
        description="Test runner: auto, pytest, jest, go, cargo, maven. auto detects from repo.",
    )
    include_buckets: list[str] = Field(
        default_factory=list,
        description="Optional subset of buckets to execute (e.g. ['unit', 'integration']).",
    )
    pytest_args: str = Field(
        default="-q",
        description="Additional arguments passed to the test runner when execute=true.",
    )
    max_tests: int = Field(
        default=4000,
        description="Maximum number of test files to include in discovery.",
    )
    command_timeout_seconds: float = Field(
        default=180.0,
        description="Per-bucket timeout for execution commands.",
    )
    output_tail_chars: int = Field(
        default=1200,
        description="How many trailing chars of stdout/stderr to preserve per run.",
    )
    use_cache: bool = Field(
        default=True,
        description="When execute=false, reuse cached discovery results if repository state is unchanged.",
    )
    cache_ttl_seconds: int = Field(
        default=300,
        description="Cache entry TTL in seconds. 0 disables expiration.",
    )


class MatrixOutput(BaseModel):
    root_path: str
    discovered_tests: int
    buckets: dict[str, int]
    sample_tests: dict[str, list[str]]
    executed: bool
    runs: list[MatrixRunResult]
    cache_hit: bool = False
    summary: str


class MatrixTool(BaseCallable):
    name = "test_matrix"
    description = (
        "Discover tests and bucket them by suite type (unit/integration/etc.), "
        "with optional per-bucket pytest execution."
    )
    callable_type = CallableType.TOOL
    input_schema = MatrixInput
    output_schema = MatrixOutput
    policy = tool_policy(
        timeout_seconds=900.0,
        requires_approval=False,
        network_allowed=False,
        max_output_bytes=1024 * 1024,
    )

    async def _execute(self, input: MatrixInput, context: CallContext) -> MatrixOutput:
        root = Path(input.root_path or os.getcwd()).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            raise CallableError(f"Invalid repository root: {root}")

        tests_root = root / "tests"
        if not tests_root.exists():
            raise CallableError(f"No tests directory found at: {tests_root}")

        cache_path: Path | None = None
        if input.use_cache and not input.execute:
            cache_path = cache_file(root, self.name, self._cache_key(root, input))
            cached = load_json_cache(cache_path, ttl_seconds=max(0, input.cache_ttl_seconds))
            if cached:
                try:
                    out = MatrixOutput.model_validate(cached)
                    return out.model_copy(
                        update={
                            "cache_hit": True,
                            "summary": f"{out.summary} (cache hit)",
                        }
                    )
                except Exception:
                    pass

        bucket_files: dict[str, list[str]] = defaultdict(list)
        discovered = 0

        for path in tests_root.rglob("test_*.py"):
            if discovered >= max(1, input.max_tests):
                break
            rel = path.relative_to(root)
            bucket = self._bucket_for(rel)
            bucket_files[bucket].append(str(rel))
            discovered += 1

        buckets = {k: len(v) for k, v in sorted(bucket_files.items())}
        sample_tests = {k: v[:5] for k, v in sorted(bucket_files.items())}

        runs: list[MatrixRunResult] = []
        if input.execute and bucket_files:
            selected = (
                [b for b in input.include_buckets if b in bucket_files]
                if input.include_buckets
                else list(bucket_files.keys())
            )
            runner = self._detect_runner(root) if input.runner == "auto" else input.runner
            for bucket in selected:
                targets = " ".join(bucket_files[bucket][:40])
                cmd = self._build_runner_command(runner, targets, input.pytest_args, root).strip()
                runs.append(
                    await self._run_command(
                        bucket=bucket,
                        command=cmd,
                        cwd=root,
                        timeout_s=max(1.0, input.command_timeout_seconds),
                        tail_chars=max(200, input.output_tail_chars),
                    )
                )

        if discovered == 0:
            summary = "No tests discovered."
        elif not input.execute:
            summary = (
                f"Discovered {discovered} tests across {len(buckets)} buckets. "
                "Execution skipped (execute=false)."
            )
        else:
            failed = sum(1 for r in runs if r.return_code != 0)
            summary = (
                f"Discovered {discovered} tests across {len(buckets)} buckets. "
                f"Executed {len(runs)} bucket runs; failures={failed}."
            )

        out = MatrixOutput(
            root_path=str(root),
            discovered_tests=discovered,
            buckets=buckets,
            sample_tests=sample_tests,
            executed=input.execute,
            runs=runs,
            summary=summary,
        )
        if cache_path is not None:
            write_json_cache(cache_path, out.model_dump())
        return out

    def _cache_key(self, root: Path, input: MatrixInput) -> str:
        fingerprint = git_state_fingerprint(root) or self._tests_fingerprint(root, input.max_tests)
        return stable_hash(
            {
                "tool": self.name,
                "root": str(root),
                "execute": False,
                "max_tests": input.max_tests,
                "fingerprint": fingerprint,
            }
        )

    def _tests_fingerprint(self, root: Path, max_tests: int) -> str:
        tests_root = root / "tests"
        if not tests_root.exists():
            return "no-tests-root"
        return file_tree_signature(
            root=tests_root,
            max_files=max(1, max_tests),
            matcher=lambda candidate: candidate.is_file() and candidate.name.startswith("test_") and candidate.suffix == ".py",
            exclude_dirs={".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"},
        )

    def _bucket_for(self, rel_path: Path) -> str:
        parts = set(rel_path.parts)
        if "integration" in parts:
            return "integration"
        if "unit" in parts:
            return "unit"
        if "tui" in parts:
            return "tui"
        if "adapters" in parts:
            return "adapters"
        if "workspace" in parts:
            return "workspace"
        return "other"

    @staticmethod
    def _detect_runner(root: Path) -> str:
        """Detect the appropriate test runner from repository markers."""
        if (root / "go.mod").exists():
            return "go"
        if (root / "Cargo.toml").exists():
            return "cargo"
        if (root / "package.json").exists():
            return "jest"
        if (root / "pom.xml").exists() or (root / "build.gradle").exists():
            return "maven"
        return "pytest"

    @staticmethod
    def _build_runner_command(runner: str, targets: str, extra_args: str, root: Path) -> str:
        """Build the test execution command for the given runner."""
        if runner == "pytest":
            venv_pytest = root / ".venv" / "bin" / "pytest"
            cmd = str(venv_pytest) if venv_pytest.exists() else "pytest"
            return f"{cmd} {extra_args} {targets}"
        if runner == "jest":
            return f"npx jest {extra_args} {targets}"
        if runner == "go":
            return f"go test ./... {extra_args}"
        if runner == "cargo":
            return f"cargo test {extra_args}"
        if runner == "maven":
            return f"mvn test {extra_args}"
        # fallback
        venv_pytest = root / ".venv" / "bin" / "pytest"
        cmd = str(venv_pytest) if venv_pytest.exists() else "pytest"
        return f"{cmd} {extra_args} {targets}"

    @staticmethod
    def _pytest_cmd() -> str:
        candidate = Path(".venv") / "bin" / "pytest"
        return str(candidate) if candidate.exists() else "pytest"

    async def _run_command(
        self,
        *,
        bucket: str,
        command: str,
        cwd: Path,
        timeout_s: float,
        tail_chars: int,
    ) -> MatrixRunResult:
        started = time.monotonic()
        proc: asyncio.subprocess.Process | None = None
        stdout = ""
        stderr = ""
        rc = 1

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=str(cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
            stdout = (out_b or b"").decode(errors="replace")
            stderr = (err_b or b"").decode(errors="replace")
            rc = proc.returncode or 0
        except TimeoutError:
            if proc and proc.returncode is None:
                proc.kill()
            rc = 124
            stderr = f"Timed out after {timeout_s:.1f}s"
        except Exception as exc:
            rc = 1
            stderr = f"Execution failed: {exc}"

        return MatrixRunResult(
            bucket=bucket,
            command=command,
            return_code=rc,
            duration_ms=int((time.monotonic() - started) * 1000),
            stdout_tail=stdout[-tail_chars:],
            stderr_tail=stderr[-tail_chars:],
        )
