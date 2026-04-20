"""DockerExecutionBackend — executes commands inside a hardened Docker container."""

from __future__ import annotations

import asyncio
import contextlib
import shlex
from typing import TYPE_CHECKING

from citnega.packages.protocol.interfaces.execution_backend import ExecutionResult, IExecutionBackend

if TYPE_CHECKING:
    from citnega.packages.config.settings import DockerSettings


class DockerExecutionBackend(IExecutionBackend):
    """
    Runs shell commands inside a Docker container with security constraints:
    - network disabled (configurable)
    - read-only root filesystem with /tmp tmpfs
    - all capabilities dropped
    - non-root user (nobody)
    - memory, CPU, and PID limits
    """

    def __init__(self, settings: DockerSettings) -> None:
        self._settings = settings

    @property
    def name(self) -> str:
        return "docker"

    async def run(
        self,
        command: str,
        cwd: str | None = None,
        timeout: float = 30.0,
        env: dict[str, str] | None = None,
    ) -> ExecutionResult:
        s = self._settings
        parts: list[str] = ["docker", "run", "--rm"]

        # Volume mount
        if cwd:
            parts += ["-v", f"{cwd}:{s.workdir}", "--workdir", s.workdir]
        else:
            parts += ["--workdir", s.workdir]

        # Network
        parts += ["--network", "none" if s.network_disabled else "bridge"]

        # Resource limits
        parts += ["--memory", s.memory_limit, "--cpus", str(s.cpu_limit)]
        parts += ["--pids-limit", str(s.pids_limit)]

        # Security flags
        parts += ["--cap-drop", "ALL", "--user", "nobody"]
        if s.read_only:
            parts += ["--read-only", "--tmpfs", "/tmp"]

        # Environment
        for k, v in (env or {}).items():
            parts += ["-e", f"{k}={v}"]

        # Image and command
        parts += [s.image, "sh", "-c", command]

        docker_cmd = " ".join(shlex.quote(p) for p in parts)
        proc: asyncio.subprocess.Process | None = None
        try:
            proc = await asyncio.create_subprocess_shell(
                docker_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return ExecutionResult(
                stdout=out_b.decode(errors="replace"),
                stderr=err_b.decode(errors="replace"),
                exit_code=proc.returncode or 0,
            )
        except asyncio.TimeoutError:
            if proc and proc.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    proc.kill()
            return ExecutionResult(stdout="", stderr="Docker execution timed out", exit_code=124, timed_out=True)
        except Exception as exc:
            return ExecutionResult(stdout="", stderr=f"Docker error: {exc}", exit_code=1)
