"""
CodeAgent — specialist for coding, debugging, and codebase operations.

Orchestrates a multi-step coding pipeline:
  1. Understand the codebase structure (list_dir, search_files)
  2. Read relevant files for context (read_file)
  3. Make targeted changes (edit_file, write_file)
  4. Verify changes (run_shell for tests/linting)
  5. Track changes (git_ops for status/diff)

The agent is invoked by the main runner LLM when a task requires
filesystem operations or code execution.  It runs autonomously and
returns a comprehensive response with what it found and changed.

llm_direct_access = True — the top-level LLM can call this agent directly
when in code mode (or when file/shell work is needed in any mode).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.agents.specialists._specialist_base import SpecialistBase, SpecialistOutput
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class CodeAgentInput(BaseModel):
    task: str = Field(description="Coding task description (what to read, write, fix, or run).")
    working_dir: str = Field(
        default="",
        description="Root directory for the task. Defaults to cwd if empty.",
    )
    files: list[str] = Field(
        default_factory=list,
        description="Specific file paths relevant to the task (optional — agent will discover if empty).",
    )


class CodeAgent(SpecialistBase):
    """
    Coding specialist that can read, write, edit, search, run, and version-control files.

    Use for:
      - Reading and explaining code
      - Writing new files or functions
      - Editing existing files (find/replace)
      - Running tests, linting, or build commands
      - Searching a codebase for symbols or patterns
      - Git status, diff, commit operations
    """

    name = "code_agent"
    description = (
        "Coding specialist: reads, writes, edits files; searches codebases; runs shell "
        "commands (tests, lint, build); performs git operations. "
        "Use for any task that requires touching the filesystem or running code."
    )
    callable_type = CallableType.SPECIALIST
    input_schema = CodeAgentInput
    output_schema = SpecialistOutput
    policy = CallablePolicy(
        timeout_seconds=180.0,
        requires_approval=False,  # individual tools handle their own approval
        network_allowed=True,
        max_depth_allowed=4,
    )

    SYSTEM_PROMPT = (
        "You are a senior software engineer with deep expertise in reading, writing, "
        "and debugging code across all major languages and frameworks.\n\n"
        "When given a coding task:\n"
        "1. **Explore first** — use list_dir and search_files to understand the project layout.\n"
        "2. **Read before writing** — always read_file before editing so you have exact context.\n"
        "3. **Minimal edits** — prefer edit_file (exact find/replace) over rewriting whole files.\n"
        "4. **Verify** — run tests/linting with run_shell after changes when applicable.\n"
        "5. **Summarise** — finish with a concise summary of what was found/changed and why.\n\n"
        "Follow existing code style. Do not introduce unnecessary abstractions or features. "
        "Every edit must have a clear reason tied to the user's task."
    )

    TOOL_WHITELIST = [
        "read_file",
        "write_file",
        "edit_file",
        "list_dir",
        "search_files",
        "run_shell",
        "git_ops",
        "get_datetime",
    ]

    async def _execute(self, input: CodeAgentInput, context: CallContext) -> SpecialistOutput:
        tool_calls_made: list[str] = []
        context_parts: list[str] = []

        child_ctx = context.child(self.name, self.callable_type)

        # ── 1. Optionally list the working directory for orientation ───────────
        if not input.files and input.working_dir:
            list_tool = self._get_tool("list_dir")
            if list_tool:
                from citnega.packages.tools.builtin.list_dir import ListDirInput

                res = await list_tool.invoke(
                    ListDirInput(dir_path=input.working_dir, recursive=False, max_items=80),
                    child_ctx,
                )
                if res.success and res.output:
                    context_parts.append(
                        f"Directory listing ({input.working_dir}):\n{res.get_output_field('result')}"
                    )
                    tool_calls_made.append("list_dir")

        # ── 2. Read explicitly provided files ─────────────────────────────────
        for fp in input.files[:5]:  # cap at 5 to avoid context overflow
            read_tool = self._get_tool("read_file")
            if read_tool:
                from citnega.packages.tools.builtin.read_file import ReadFileInput

                res = await read_tool.invoke(
                    ReadFileInput(file_path=fp, max_bytes=32 * 1024),
                    child_ctx,
                )
                if res.success and res.output:
                    context_parts.append(
                        f"File: {fp}\n```\n{res.get_output_field('result')}\n```"
                    )
                    tool_calls_made.append("read_file")

        # ── 3. Call the model with all gathered context ────────────────────────
        context_block = "\n\n".join(context_parts)
        prompt = input.task
        if context_block:
            prompt = (
                f"Context gathered from the filesystem:\n\n{context_block}\n\n"
                f"---\n\nTask: {input.task}"
            )

        response = await self._call_model(prompt, context)

        return SpecialistOutput(
            response=response,
            tool_calls_made=tool_calls_made,
        )
