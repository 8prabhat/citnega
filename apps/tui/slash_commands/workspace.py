"""
Workspace slash commands — /setworkfolder, /refresh, /createtool, /createagent, /createworkflow.

These commands let users:
  - Set the workfolder where user-created artifacts live (/setworkfolder).
  - Hot-reload any new/changed files without restarting (/refresh).
  - Interactively generate a tool, agent, or workflow via a multi-step wizard
    (/createtool, /createagent, /createworkflow).

The wizards use ChatController._pending_wizard to intercept the next plain-text
user input instead of sending it to the LLM.  Each step sets a new WizardState
so the flow continues until all information is collected.

WizardState is intentionally minimal:
  - ``step_name``  — human-readable label for the current question
  - ``on_input``   — async callable(text, controller) called with user's answer
  - ``prompt``     — question text already shown to the user (informational only)
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from citnega.packages.protocol.interfaces.slash_command import ISlashCommand

if TYPE_CHECKING:
    from collections.abc import Callable

# ---------------------------------------------------------------------------
# WizardState
# ---------------------------------------------------------------------------


class WizardState:
    """
    Represents a single pending wizard step.

    When ``ChatController._pending_wizard`` is set to a ``WizardState``,
    the *next* plain-text user message is routed to ``on_input`` instead of
    being forwarded to the LLM.
    """

    def __init__(
        self,
        step_name: str,
        on_input: Callable,
        prompt: str = "",
    ) -> None:
        self.step_name = step_name
        self.on_input = on_input
        self.prompt = prompt


# ---------------------------------------------------------------------------
# /setworkfolder
# ---------------------------------------------------------------------------


class SetWorkfolderCommand(ISlashCommand):
    name = "setworkfolder"
    help_text = "Set (or show) the workspace folder. Usage: /setworkfolder [path]"

    def __init__(self, service: Any) -> None:
        self._service = service

    async def execute(self, args: list[str], app_context: Any) -> None:
        if not args:
            # Show current workfolder
            from citnega.packages.config.loaders import load_settings

            current = load_settings().workspace.workfolder_path or os.getcwd()
            await app_context._append_message(
                "system", f"Current workfolder: {current}\nUsage: /setworkfolder <absolute-path>"
            )
            return

        path_str = " ".join(args).strip().strip("'\"")  # strip surrounding quotes
        path = Path(path_str).expanduser().resolve()

        if not path.exists():
            try:
                path.mkdir(parents=True, exist_ok=True)
                await app_context._append_message("system", f"Created directory: {path}")
            except Exception as exc:
                await app_context._append_message(
                    "system", f"Could not create directory '{path}': {exc}"
                )
                return

        if not path.is_dir():
            await app_context._append_message("system", f"'{path}' is not a directory.")
            return

        # Persist the path and create workspace subdirectories
        try:
            self._service.save_workspace_path(str(path))
        except Exception as exc:
            await app_context._append_message(
                "system", f"Warning: could not persist workfolder path: {exc}"
            )

        from citnega.packages.workspace.writer import WorkspaceWriter

        writer = WorkspaceWriter(path)
        writer.ensure_dirs()

        app_context._update_context_bar(folder=str(path))
        await app_context._append_message(
            "system",
            f"Workfolder set to: {path}\n"
            f"Subdirectories created: agents/, tools/, workflows/\n"
            f"Use /createtool, /createagent, /createworkflow to add new artifacts,\n"
            f"then /refresh to reload them.",
        )


# ---------------------------------------------------------------------------
# /refresh
# ---------------------------------------------------------------------------


class RefreshCommand(ISlashCommand):
    name = "refresh"
    help_text = "Scan workfolder and hot-load new/changed tools, agents, workflows."

    def __init__(self, service: Any) -> None:
        self._service = service

    async def execute(self, args: list[str], app_context: Any) -> None:
        from citnega.packages.config.loaders import load_settings
        from citnega.packages.workspace.loader import DynamicLoader

        settings = load_settings()
        workfolder_str = settings.workspace.workfolder_path or os.getcwd()
        workfolder = Path(workfolder_str)

        if not workfolder.is_dir():
            await app_context._append_message(
                "system",
                f"Workfolder '{workfolder}' does not exist. Use /setworkfolder <path> first.",
            )
            return

        loader = DynamicLoader(
            enforcer=getattr(self._service, "_enforcer", None),
            emitter=getattr(self._service, "_emitter", None),
            tracer=getattr(self._service, "_tracer", None),
            tool_registry=getattr(self._service, "_tool_registry", {}),
        )

        try:
            result = await self._service.hot_reload_workfolder(workfolder, loader)
        except Exception as exc:
            await app_context._append_message("system", f"Refresh failed: {exc}")
            return

        registered = result.get("registered", [])
        errors = result.get("errors", [])

        lines = [f"Refreshed workfolder: {workfolder}"]
        if registered:
            lines.append(f"Loaded ({len(registered)}): {', '.join(registered)}")
        else:
            lines.append("No new callables found.")
        if errors:
            lines.append("Errors:")
            lines.extend(f"  {e}" for e in errors)

        await app_context._append_message("system", "\n".join(lines))


# ---------------------------------------------------------------------------
# /createtool
# ---------------------------------------------------------------------------


class CreateToolCommand(ISlashCommand):
    name = "createtool"
    help_text = "Interactively create a new tool in the workfolder."

    def __init__(self, service: Any) -> None:
        self._service = service

    async def execute(self, args: list[str], app_context: Any) -> None:
        app_context._wizard_data = {"kind": "tool", "params": []}
        await app_context._append_message(
            "system",
            "Creating a new tool.\n"
            "Step 1/3 — Enter a snake_case name for your tool (e.g. web_scraper):",
        )
        app_context._pending_wizard = WizardState(
            step_name="tool_name",
            on_input=self._on_name,
        )

    async def _on_name(self, text: str, ctrl: Any) -> None:
        name = text.strip().lower().replace(" ", "_")
        if not name.isidentifier():
            await ctrl._append_message(
                "system",
                f"'{name}' is not a valid Python identifier. Please use snake_case (e.g. my_tool).",
            )
            ctrl._pending_wizard = WizardState("tool_name", self._on_name)
            return
        ctrl._wizard_data["name"] = name
        ctrl._wizard_data["class_name"] = _to_pascal(name)
        await ctrl._append_message("system", f"Step 2/3 — Enter a description for '{name}':")
        ctrl._pending_wizard = WizardState("tool_desc", self._on_desc)

    async def _on_desc(self, text: str, ctrl: Any) -> None:
        ctrl._wizard_data["description"] = text.strip()
        await _ask_param_type_or_done(ctrl, self._on_param_start, self._finalize)

    async def _on_param_start(self, value: str, label: str, ctrl: Any) -> None:
        if value == "done":
            await self._finalize(ctrl)
            return
        ctrl._wizard_data["_current_param_type"] = value
        await ctrl._append_message("system", f"Parameter name for type '{value}':")
        ctrl._pending_wizard = WizardState("param_name", self._on_param_name)

    async def _on_param_name(self, text: str, ctrl: Any) -> None:
        pname = text.strip().lower().replace(" ", "_")
        ctrl._wizard_data["_current_param_name"] = pname
        await ctrl._append_message("system", f"Brief description for parameter '{pname}':")
        ctrl._pending_wizard = WizardState("param_desc", self._on_param_desc)

    async def _on_param_desc(self, text: str, ctrl: Any) -> None:
        ctrl._wizard_data["params"].append(
            {
                "name": ctrl._wizard_data.pop("_current_param_name"),
                "type": ctrl._wizard_data.pop("_current_param_type"),
                "description": text.strip(),
            }
        )
        await _ask_param_type_or_done(ctrl, self._on_param_start, self._finalize)

    async def _finalize(self, ctrl: Any) -> None:
        await _generate_and_register(ctrl, self._service)


# ---------------------------------------------------------------------------
# /createagent
# ---------------------------------------------------------------------------


class CreateAgentCommand(ISlashCommand):
    name = "createagent"
    help_text = "Interactively create a new specialist agent in the workfolder."

    def __init__(self, service: Any) -> None:
        self._service = service

    async def execute(self, args: list[str], app_context: Any) -> None:
        app_context._wizard_data = {"kind": "agent", "tool_whitelist": []}
        await app_context._append_message(
            "system",
            "Creating a new specialist agent.\n"
            "Step 1/4 — Enter a snake_case name (e.g. research_agent):",
        )
        app_context._pending_wizard = WizardState("agent_name", self._on_name)

    async def _on_name(self, text: str, ctrl: Any) -> None:
        name = text.strip().lower().replace(" ", "_")
        if not name.isidentifier():
            await ctrl._append_message("system", "Invalid identifier. Please use snake_case.")
            ctrl._pending_wizard = WizardState("agent_name", self._on_name)
            return
        ctrl._wizard_data["name"] = name
        ctrl._wizard_data["class_name"] = _to_pascal(name)
        await ctrl._append_message("system", "Step 2/4 — Enter a description:")
        ctrl._pending_wizard = WizardState("agent_desc", self._on_desc)

    async def _on_desc(self, text: str, ctrl: Any) -> None:
        ctrl._wizard_data["description"] = text.strip()
        await ctrl._append_message(
            "system",
            "Step 3/4 — Enter a system prompt for this agent\n(or press Enter to use a default):",
        )
        ctrl._pending_wizard = WizardState("agent_prompt", self._on_prompt)

    async def _on_prompt(self, text: str, ctrl: Any) -> None:
        ctrl._wizard_data["system_prompt"] = text.strip()
        await _ask_tool_whitelist(ctrl, self._service, self._finalize)

    async def _finalize(self, ctrl: Any) -> None:
        await _generate_and_register(ctrl, self._service)


# ---------------------------------------------------------------------------
# /createworkflow
# ---------------------------------------------------------------------------


class CreateWorkflowCommand(ISlashCommand):
    name = "createworkflow"
    help_text = "Interactively create a workflow that orchestrates agents and tools."

    def __init__(self, service: Any) -> None:
        self._service = service

    async def execute(self, args: list[str], app_context: Any) -> None:
        app_context._wizard_data = {
            "kind": "workflow",
            "tool_whitelist": [],
            "sub_agents": [],
        }
        await app_context._append_message(
            "system",
            "Creating a new workflow.\n"
            "Step 1/4 — Enter a snake_case name (e.g. data_pipeline_workflow):",
        )
        app_context._pending_wizard = WizardState("wf_name", self._on_name)

    async def _on_name(self, text: str, ctrl: Any) -> None:
        name = text.strip().lower().replace(" ", "_")
        if not name.isidentifier():
            await ctrl._append_message("system", "Invalid identifier. Please use snake_case.")
            ctrl._pending_wizard = WizardState("wf_name", self._on_name)
            return
        ctrl._wizard_data["name"] = name
        ctrl._wizard_data["class_name"] = _to_pascal(name)
        await ctrl._append_message("system", "Step 2/4 — Describe what this workflow does:")
        ctrl._pending_wizard = WizardState("wf_desc", self._on_desc)

    async def _on_desc(self, text: str, ctrl: Any) -> None:
        ctrl._wizard_data["description"] = text.strip()
        await _ask_tool_whitelist(ctrl, self._service, self._on_tools_done)

    async def _on_tools_done(self, ctrl: Any) -> None:
        # After tools, ask for sub-agents
        await _ask_sub_agents(ctrl, self._service, self._finalize)

    async def _finalize(self, ctrl: Any) -> None:
        await _generate_and_register(ctrl, self._service)


# ---------------------------------------------------------------------------
# Shared wizard helpers
# ---------------------------------------------------------------------------


async def _ask_param_type_or_done(ctrl: Any, on_select, on_done) -> None:
    """Show a type picker; call on_select(value, label, ctrl) or on_done(ctrl)."""
    type_options = [
        ("str", "str   — text"),
        ("int", "int   — integer number"),
        ("float", "float — decimal number"),
        ("bool", "bool  — true/false"),
        ("done", "Done  — no more parameters"),
    ]

    async def _on_pick(value: str, label: str) -> None:
        if value == "done":
            await on_done(ctrl)
        else:
            await on_select(value, label, ctrl)

    await ctrl._append_picker(
        title="Step 3 — Add a parameter? (select type or Done)",
        options=type_options,
        on_select=_on_pick,
        on_dismiss=lambda: on_done(ctrl),
    )


async def _ask_tool_whitelist(ctrl: Any, service: Any, on_done) -> None:
    """Show a multi-select picker for tool whitelist; sentinel = 'done'."""
    tools = service.list_tools()
    if not tools:
        await ctrl._append_message("system", "No tools registered yet — skipping tool whitelist.")
        await on_done(ctrl)
        return

    options = [
        (t.name, f"{'[added] ' if t.name in ctrl._wizard_data['tool_whitelist'] else ''}{t.name}")
        for t in tools
    ] + [("done", "Done — finish tool selection")]

    async def _on_pick(value: str, label: str) -> None:
        if value == "done":
            await on_done(ctrl)
        else:
            if value not in ctrl._wizard_data["tool_whitelist"]:
                ctrl._wizard_data["tool_whitelist"].append(value)
            await _ask_tool_whitelist(ctrl, service, on_done)

    await ctrl._append_picker(
        title="Select tools for this agent (pick one at a time, then Done):",
        options=options,
        on_select=_on_pick,
        on_dismiss=lambda: on_done(ctrl),
    )


async def _ask_sub_agents(ctrl: Any, service: Any, on_done) -> None:
    """Show a multi-select picker for sub-agents; sentinel = 'done'."""
    agents = service.list_agents()
    if not agents:
        await ctrl._append_message(
            "system", "No agents registered yet — skipping sub-agent selection."
        )
        await on_done(ctrl)
        return

    options = [
        (
            a.name,
            f"{'[added] ' if a.name in ctrl._wizard_data.get('sub_agents', []) else ''}{a.name}",
        )
        for a in agents
    ] + [("done", "Done — finish agent selection")]

    async def _on_pick(value: str, label: str) -> None:
        if value == "done":
            await on_done(ctrl)
        else:
            sub = ctrl._wizard_data.setdefault("sub_agents", [])
            if value not in sub:
                sub.append(value)
            await _ask_sub_agents(ctrl, service, on_done)

    await ctrl._append_picker(
        title="Select sub-agents for this workflow (pick one at a time, then Done):",
        options=options,
        on_select=_on_pick,
        on_dismiss=lambda: on_done(ctrl),
    )


async def _generate_and_register(ctrl: Any, service: Any) -> None:
    """
    Final wizard step — full pipeline:

      1. Switch TUI to "coding" mode (StatusBar + CodingBlock).
      2. Generate code with the LLM (streaming tokens to CodingBlock).
      3. Test the generated code (run _execute with mock inputs).
      4. If tests fail: retry up to 2 times, feeding the error back to the LLM.
      5. Write the file, load it, register the callable.
      6. Reset TUI to "idle".
    """
    from textual.containers import VerticalScroll

    from citnega.apps.tui.widgets.coding_block import CodingBlock
    from citnega.packages.config.loaders import load_settings
    from citnega.packages.workspace.loader import DynamicLoader
    from citnega.packages.workspace.scaffold import ScaffoldGenerator
    from citnega.packages.workspace.templates import ScaffoldSpec
    from citnega.packages.workspace.tester import CallableTester
    from citnega.packages.workspace.writer import WorkspaceWriter

    data = ctrl._wizard_data
    kind = data["kind"]
    name = data["name"]
    class_name = data["class_name"]

    spec = ScaffoldSpec(
        kind=kind,
        class_name=class_name,
        name=name,
        description=data.get("description", ""),
        parameters=data.get("params", []),
        system_prompt=data.get("system_prompt", ""),
        tool_whitelist=data.get("tool_whitelist", []),
        sub_agents=data.get("sub_agents", []),
    )

    # ── Set TUI to "coding" mode ───────────────────────────────────────────────
    _set_run_state(ctrl, "coding")

    # Mount the CodingBlock into the chat scroll
    coding_block = CodingBlock(title=name, kind=kind)
    try:
        scroll = ctrl._app.screen.query_one("#chat-scroll", VerticalScroll)
        await scroll.mount(coding_block)
        ctrl._app.call_after_refresh(scroll.scroll_end)
    except Exception:
        coding_block = None  # TUI not available (tests / CLI) — degrade gracefully

    async def _on_chunk(token: str) -> None:
        if coding_block is not None:
            coding_block.append_token(token)
            with contextlib.suppress(Exception):
                ctrl._app.call_after_refresh(scroll.scroll_end)

    async def _on_status(msg: str) -> None:
        if coding_block is not None:
            coding_block.set_status(msg)
            coding_block.clear_code()
        # Also echo status as a system message for accessibility
        await ctrl._append_message("system", msg)

    # ── Shared deps ────────────────────────────────────────────────────────────
    loader = DynamicLoader(
        enforcer=getattr(service, "_enforcer", None),
        emitter=getattr(service, "_emitter", None),
        tracer=getattr(service, "_tracer", None),
        tool_registry=getattr(service, "_tool_registry", {}),
    )
    generator = ScaffoldGenerator(model_gateway=getattr(service, "_model_gateway", None))
    tester = CallableTester()

    # ── Generate → test → retry ────────────────────────────────────────────────
    try:
        source, _instance, test_result = await generator.generate_with_retry(
            spec=spec,
            tester=tester,
            loader=loader,
            on_chunk=_on_chunk,
            on_status=_on_status,
            max_retries=2,
        )
    except Exception as exc:
        if coding_block is not None:
            coding_block.set_result_fail(f"Generation pipeline failed: {exc}")
        await ctrl._append_message("system", f"Generation failed: {exc}")
        _set_run_state(ctrl, "idle")
        return

    # ── Check final test result ────────────────────────────────────────────────
    if test_result is not None and not test_result.passed:
        msg = (
            f"Code was generated but tests did not pass after all retries.\n"
            f"Error:\n{test_result.error[:600]}\n\n"
            f"The file will still be written so you can edit it manually.\n"
            f"Use /refresh after fixing."
        )
        if coding_block is not None:
            coding_block.set_result_fail("Tests failed — file written for manual edit")
        await ctrl._append_message("system", msg)
        # Fall through: write the best attempt to disk anyway

    # ── Resolve workfolder ─────────────────────────────────────────────────────
    settings = load_settings()
    workfolder = Path(settings.workspace.workfolder_path or os.getcwd())
    writer = WorkspaceWriter(workfolder)
    writer.ensure_dirs()

    # ── Write file ─────────────────────────────────────────────────────────────
    try:
        if kind == "tool":
            written_path = writer.write_tool(class_name, source)
        elif kind == "agent":
            written_path = writer.write_agent(class_name, source)
        else:
            written_path = writer.write_workflow(class_name, source)
    except Exception as exc:
        if coding_block is not None:
            coding_block.set_result_fail(f"Write failed: {exc}")
        await ctrl._append_message("system", f"Failed to write file: {exc}")
        _set_run_state(ctrl, "idle")
        return

    # ── Load & register ────────────────────────────────────────────────────────
    try:
        loaded = loader.load_directory(written_path.parent)
        if name in loaded:
            service.register_callable(loaded[name])
        else:
            msg = (
                f"File written to {written_path} but '{name}' could not be loaded.\n"
                f"Check the file for import errors, then run /refresh."
            )
            if coding_block is not None:
                coding_block.set_result_fail("Import failed — check file and /refresh")
            await ctrl._append_message("system", msg)
            _set_run_state(ctrl, "idle")
            return
    except Exception as exc:
        if coding_block is not None:
            coding_block.set_result_fail(f"Registration failed: {exc}")
        await ctrl._append_message(
            "system",
            f"File written to {written_path} but registration failed: {exc}\n"
            f"Use /refresh to retry.",
        )
        _set_run_state(ctrl, "idle")
        return

    # ── Success ────────────────────────────────────────────────────────────────
    test_note = ""
    if test_result is not None and test_result.passed:
        test_note = f"\nTests passed in {test_result.duration_ms} ms."

    if coding_block is not None:
        coding_block.set_result_pass(f"'{name}' registered successfully!{test_note}")

    await ctrl._append_message(
        "system",
        f"{kind.capitalize()} '{name}' created, tested, and registered successfully!\n"
        f"File: {written_path}{test_note}\n"
        f"Use /agent tools  or  /agent agents  to confirm it appears in the list.",
    )

    _set_run_state(ctrl, "idle")


def _set_run_state(ctrl: Any, state: str) -> None:
    """Update the StatusBar run_state safely (no-op if TUI unavailable)."""
    try:
        from citnega.apps.tui.widgets.status_bar import StatusBar

        ctrl._app.screen.query_one(StatusBar).run_state = state
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _to_pascal(snake: str) -> str:
    """Convert snake_case to PascalCase.  e.g. web_scraper_tool → WebScraperTool"""
    return "".join(word.capitalize() for word in snake.split("_"))
