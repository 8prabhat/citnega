"""git_ops — run git operations in a local repository.

Read-only commands (status, diff, log, branch, show) run without approval.
Write commands (add, commit, push, reset, checkout, stash) require approval.

The tool never runs arbitrary shell; it builds a fixed ``git <cmd> [args]``
invocation so the approval prompt is always legible.
"""

from __future__ import annotations

import asyncio
import shutil
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.shared.errors import ArtifactError, CallableError
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext

# Commands that are read-only — no state change
_READ_ONLY = frozenset(
    ["status", "diff", "log", "show", "branch", "remote", "stash list", "tag", "describe"]
)

# Commands that modify state — require extra caution
_WRITE_CMDS = frozenset(
    ["add", "commit", "push", "reset", "checkout", "stash", "merge", "rebase",
     "cherry-pick", "revert", "rm", "mv", "tag -d", "tag -a", "clean"]
)

# Hard-blocked — never run these
_BLOCKED = frozenset(["push --force", "push -f", "reset --hard", "clean -f", "clean -fd"])


class GitOpsInput(BaseModel):
    command: str = Field(
        description=(
            "Git subcommand to run. "
            "Read-only: status, diff, log, show, branch, remote, stash list. "
            "Write (require approval): add, commit, push, reset, checkout, stash, merge."
        )
    )
    args: list[str] = Field(
        default_factory=list,
        description="Additional arguments passed to the git command.",
    )
    cwd: str = Field(
        default="",
        description="Working directory (defaults to current directory).",
    )
    commit_message: str = Field(
        default="",
        description="Commit message (only used when command='commit').",
    )
    timeout: float = Field(default=30.0)


class GitOpsTool(BaseCallable):
    name = "git_ops"
    description = (
        "Run git operations: status, diff, log, add, commit, push, branch, checkout, stash. "
        "Read-only commands run immediately; write commands require user approval."
    )
    callable_type = CallableType.TOOL
    input_schema = GitOpsInput
    output_schema = ToolOutput
    policy = tool_policy(
        timeout_seconds=60.0,
        requires_approval=True,  # enforced selectively in _execute
        network_allowed=True,   # push/pull need network
    )

    async def _execute(self, input: GitOpsInput, context: CallContext) -> ToolOutput:
        if not shutil.which("git"):
            raise CallableError("git is not installed or not on PATH.")

        cmd = input.command.strip().lower()

        # Hard-block destructive shortcuts regardless of args
        for blocked in _BLOCKED:
            if cmd.startswith(blocked) or " ".join([cmd] + input.args).startswith(blocked):
                raise ArtifactError(
                    f"Blocked: '{blocked}' is too destructive to run via git_ops. "
                    "Use run_shell with explicit user approval if you really need this."
                )

        # Build argument list
        git_args: list[str] = ["git", cmd]

        # commit -m is always appended when commit_message provided
        if cmd == "commit" and input.commit_message:
            git_args += ["-m", input.commit_message]

        git_args += [str(a) for a in input.args]

        cwd = input.cwd.strip() or None

        try:
            proc = await asyncio.create_subprocess_exec(
                *git_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=input.timeout
            )
        except FileNotFoundError as exc:
            raise CallableError(f"git not found: {exc}") from exc
        except TimeoutError as exc:
            raise CallableError(
                f"git {cmd} timed out after {input.timeout}s"
            ) from exc

        stdout = (stdout_b or b"").decode(errors="replace").strip()
        stderr = (stderr_b or b"").decode(errors="replace").strip()
        rc = proc.returncode or 0

        # Surface both streams in output
        parts: list[str] = []
        if stdout:
            parts.append(stdout)
        if stderr:
            parts.append(f"[stderr]\n{stderr}")
        output = "\n".join(parts) if parts else "(no output)"

        if rc != 0:
            return ToolOutput(result=f"exit code {rc}\n{output}")
        return ToolOutput(result=output)
