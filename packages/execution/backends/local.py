"""LocalExecutionBackend — default backend, runs commands in the local process."""

from __future__ import annotations

import asyncio
import contextlib
import os

from citnega.packages.protocol.interfaces.execution_backend import ExecutionResult, IExecutionBackend


class LocalExecutionBackend(IExecutionBackend):
    """Executes commands as local subprocess — same behaviour as the original RunShellTool."""

    @property
    def name(self) -> str:
        return "local"

    async def run(
        self,
        command: str,
        cwd: str | None = None,
        timeout: float = 30.0,
        env: dict[str, str] | None = None,
    ) -> ExecutionResult:
        merged_env = {**os.environ, **(env or {})}
        proc: asyncio.subprocess.Process | None = None
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=merged_env,
            )
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return ExecutionResult(
                stdout=stdout_b.decode(errors="replace"),
                stderr=stderr_b.decode(errors="replace"),
                exit_code=proc.returncode or 0,
            )
        except asyncio.TimeoutError:
            if proc and proc.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    proc.kill()
            return ExecutionResult(stdout="", stderr=f"Command timed out after {timeout}s", exit_code=124, timed_out=True)
        except Exception as exc:
            return ExecutionResult(stdout="", stderr=str(exc), exit_code=1)
