"""GitLogTool — structured git history, blame, show, and diff."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType


class GitLogInput(BaseModel):
    operation: Literal["log", "blame", "show", "diff"] = "log"
    path: str = "."            # repo root or file for blame
    ref: str = ""              # commit/branch/tag for show/diff
    base_ref: str = ""         # base ref for diff (e.g. "main")
    limit: int = 20            # max commits for log
    json_output: bool = True


class GitLogOutput(BaseModel):
    operation: str
    data: Any          # list[dict] for log/blame/diff, str for show
    raw: str = ""      # always populated; useful for debugging


def _run_git(args: list[str], cwd: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {args[0]} failed: {result.stderr.strip()}")
    return result.stdout


class GitLogTool(BaseCallable):
    name = "git_log"
    description = (
        "Query git history. Operations: log (recent commits), blame (line authorship), "
        "show (commit details/diff), diff (compare refs). Returns structured JSON by default."
    )
    callable_type = CallableType.TOOL
    input_schema = GitLogInput
    output_schema = GitLogOutput

    async def _execute(self, input_data: GitLogInput, context: object) -> GitLogOutput:
        cwd = str(Path(input_data.path).resolve())

        if input_data.operation == "log":
            fmt = '{"hash":"%H","short":"%h","author":"%an","date":"%ai","subject":"%s"}'
            raw = _run_git(["log", f"--format={fmt}", f"-{input_data.limit}"], cwd)
            if input_data.json_output:
                entries = [json.loads(line) for line in raw.splitlines() if line.strip()]
                return GitLogOutput(operation="log", data=entries, raw=raw)
            return GitLogOutput(operation="log", data=raw, raw=raw)

        elif input_data.operation == "blame":
            raw = _run_git(["blame", "--porcelain", input_data.path], cwd)
            if input_data.json_output:
                return GitLogOutput(operation="blame", data=_parse_blame(raw), raw=raw)
            return GitLogOutput(operation="blame", data=raw, raw=raw)

        elif input_data.operation == "show":
            ref = input_data.ref or "HEAD"
            raw = _run_git(["show", ref], cwd)
            return GitLogOutput(operation="show", data=raw, raw=raw)

        elif input_data.operation == "diff":
            base = input_data.base_ref or "HEAD~1"
            ref = input_data.ref or "HEAD"
            raw = _run_git(["diff", base, ref, "--stat", "--unified=3"], cwd)
            if input_data.json_output:
                return GitLogOutput(operation="diff", data=_parse_diff_stat(raw), raw=raw)
            return GitLogOutput(operation="diff", data=raw, raw=raw)

        raise ValueError(f"Unknown operation: {input_data.operation!r}")


def _parse_blame(raw: str) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for line in raw.splitlines():
        if line.startswith("\t"):
            if current:
                current["code"] = line[1:]
                lines.append(current)
                current = {}
        elif " " in line:
            key, _, value = line.partition(" ")
            if len(key) == 40 and all(c in "0123456789abcdef" for c in key):
                current = {"hash": key}
            else:
                current[key] = value
    return lines


def _parse_diff_stat(raw: str) -> list[dict[str, Any]]:
    results = []
    for line in raw.splitlines():
        line = line.strip()
        if "|" in line:
            parts = line.split("|")
            if len(parts) == 2:
                fname = parts[0].strip()
                changes = parts[1].strip()
                additions = changes.count("+")
                deletions = changes.count("-")
                results.append({"file": fname, "additions": additions, "deletions": deletions})
    return results
