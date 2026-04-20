"""run_shell — execute a shell command. Requires approval."""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field
from pydantic import BaseModel as _BM

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.shared.errors import CallableError
from citnega.packages.tools.builtin._tool_base import tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext
    from citnega.packages.protocol.interfaces.execution_backend import IExecutionBackend


class RunShellInput(BaseModel):
    command: str = Field(description="Shell command to execute.")
    working_dir: str = Field(default="", description="Working directory (empty = cwd).")
    timeout: float = Field(default=30.0, description="Command timeout in seconds.")
    capture_stderr: bool = Field(default=True)


class ShellOutput(_BM):
    stdout: str
    stderr: str
    return_code: int


class RunShellTool(BaseCallable):
    name = "run_shell"
    description = "Execute a shell command and return stdout, stderr, and return code."
    callable_type = CallableType.TOOL
    input_schema = RunShellInput
    output_schema = ShellOutput
    policy = tool_policy(
        timeout_seconds=60.0,
        requires_approval=True,  # shell execution always requires approval
        network_allowed=True,  # command may touch network
    )

    def __init__(self, policy_enforcer, event_emitter, tracer, execution_backend: IExecutionBackend | None = None) -> None:
        super().__init__(policy_enforcer, event_emitter, tracer)
        self._execution_backend = execution_backend

    async def _execute(self, input: RunShellInput, context: CallContext) -> ShellOutput:
        cwd = input.working_dir or None

        # Use injected backend (Docker or future backends) when available
        if self._execution_backend is not None:
            result = await self._execution_backend.run(
                command=input.command,
                cwd=cwd,
                timeout=input.timeout,
            )
            stderr = result.stderr if input.capture_stderr else ""
            if result.timed_out:
                raise CallableError(f"Command timed out after {input.timeout}s: {input.command!r}")
            return ShellOutput(stdout=result.stdout, stderr=stderr, return_code=result.exit_code)

        # Default: local asyncio subprocess (original behaviour, no breaking change)
        proc: asyncio.subprocess.Process | None = None

        def _kill() -> None:
            if proc and proc.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    proc.kill()

        context.register_cleanup(_kill)

        stderr_pipe = (
            asyncio.subprocess.PIPE if input.capture_stderr else asyncio.subprocess.DEVNULL
        )

        try:
            proc = await asyncio.create_subprocess_shell(
                input.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=stderr_pipe,
                cwd=cwd,
            )
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=input.timeout)
        except TimeoutError as exc:
            _kill()
            raise CallableError(
                f"Command timed out after {input.timeout}s: {input.command!r}"
            ) from exc
        except Exception as exc:
            raise CallableError(f"Command failed: {exc}") from exc

        return ShellOutput(
            stdout=(stdout_b or b"").decode(errors="replace"),
            stderr=(stderr_b or b"").decode(errors="replace"),
            return_code=proc.returncode or 0,
        )
