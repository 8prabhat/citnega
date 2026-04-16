"""quality_gate — run a configurable sequence of repository quality checks."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import os
from pathlib import Path
import time
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.shared.errors import CallableError
from citnega.packages.tools.builtin._tool_base import tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


@dataclass(frozen=True)
class _NamedCommand:
    name: str
    command: str


class QualityGateInput(BaseModel):
    working_dir: str = Field(
        default="",
        description="Directory to run checks in. Empty means current working directory.",
    )
    profile: str = Field(
        default="quick",
        description="'quick' | 'standard' | 'strict'. Ignored when commands are provided.",
    )
    commands: list[str] = Field(
        default_factory=list,
        description="Optional explicit commands. When provided, profile defaults are skipped.",
    )
    per_command_timeout_seconds: float = Field(
        default=120.0,
        description="Timeout applied to each command individually.",
    )
    output_tail_chars: int = Field(
        default=2000,
        description="How many trailing characters of stdout/stderr to keep per command.",
    )


class QualityCheckResult(BaseModel):
    name: str
    command: str
    return_code: int
    passed: bool
    duration_ms: int
    stdout_tail: str = ""
    stderr_tail: str = ""


class QualityGateOutput(BaseModel):
    passed: bool
    profile: str
    working_dir: str
    total_checks: int
    passed_checks: int
    failed_checks: int
    checks: list[QualityCheckResult]
    summary: str


class QualityGateTool(BaseCallable):
    name = "quality_gate"
    description = (
        "Run an opinionated quality gate (ruff/mypy/pytest) or custom check commands "
        "and return structured pass/fail results."
    )
    callable_type = CallableType.TOOL
    input_schema = QualityGateInput
    output_schema = QualityGateOutput
    policy = tool_policy(
        timeout_seconds=900.0,
        requires_approval=False,
        network_allowed=False,
        max_output_bytes=1024 * 1024,
    )

    async def _execute(self, input: QualityGateInput, context: CallContext) -> QualityGateOutput:
        cwd = Path(input.working_dir or os.getcwd()).expanduser().resolve()
        if not cwd.exists() or not cwd.is_dir():
            raise CallableError(f"Working directory is invalid: {cwd}")

        named_commands = self._resolve_commands(input)
        if not named_commands:
            raise CallableError("No quality-check commands resolved.")

        checks: list[QualityCheckResult] = []
        for named in named_commands:
            checks.append(
                await self._run_one(
                    named=named,
                    cwd=cwd,
                    timeout_s=max(1.0, input.per_command_timeout_seconds),
                    tail_chars=max(200, input.output_tail_chars),
                )
            )

        passed_checks = sum(1 for c in checks if c.passed)
        failed = [c for c in checks if not c.passed]
        failed_names = ", ".join(c.name for c in failed)
        overall_passed = len(failed) == 0
        summary = (
            f"Quality gate passed ({passed_checks}/{len(checks)} checks)."
            if overall_passed
            else f"Quality gate failed ({passed_checks}/{len(checks)} checks passed). "
            f"Failing checks: {failed_names}."
        )

        return QualityGateOutput(
            passed=overall_passed,
            profile=input.profile,
            working_dir=str(cwd),
            total_checks=len(checks),
            passed_checks=passed_checks,
            failed_checks=len(checks) - passed_checks,
            checks=checks,
            summary=summary,
        )

    def _resolve_commands(self, input: QualityGateInput) -> list[_NamedCommand]:
        if input.commands:
            return [
                _NamedCommand(name=f"custom_{idx+1}", command=cmd)
                for idx, cmd in enumerate(input.commands)
                if cmd.strip()
            ]

        profile = input.profile.lower().strip()
        if profile == "quick":
            return [
                _NamedCommand("ruff", self._cmd_ruff()),
            ]
        if profile == "standard":
            return [
                _NamedCommand("ruff", self._cmd_ruff()),
                _NamedCommand("pytest", self._cmd_pytest()),
            ]
        if profile == "strict":
            return [
                _NamedCommand("ruff", self._cmd_ruff()),
                _NamedCommand("mypy", self._cmd_mypy()),
                _NamedCommand("pytest", self._cmd_pytest()),
            ]
        raise CallableError(
            f"Unknown quality_gate profile: {input.profile!r}. "
            "Expected quick|standard|strict."
        )

    @staticmethod
    def _prefer_venv(bin_name: str) -> str:
        candidate = Path(".venv") / "bin" / bin_name
        return str(candidate) if candidate.exists() else bin_name

    def _cmd_ruff(self) -> str:
        return f"{self._prefer_venv('ruff')} check apps packages tests"

    def _cmd_mypy(self) -> str:
        return f"{self._prefer_venv('mypy')} packages apps --ignore-missing-imports"

    def _cmd_pytest(self) -> str:
        return f"{self._prefer_venv('pytest')} -q"

    async def _run_one(
        self,
        *,
        named: _NamedCommand,
        cwd: Path,
        timeout_s: float,
        tail_chars: int,
    ) -> QualityCheckResult:
        started = time.monotonic()
        proc: asyncio.subprocess.Process | None = None
        stdout = ""
        stderr = ""
        rc = 1

        try:
            proc = await asyncio.create_subprocess_shell(
                named.command,
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

        duration_ms = int((time.monotonic() - started) * 1000)
        return QualityCheckResult(
            name=named.name,
            command=named.command,
            return_code=rc,
            passed=rc == 0,
            duration_ms=duration_ms,
            stdout_tail=stdout[-tail_chars:],
            stderr_tail=stderr[-tail_chars:],
        )
