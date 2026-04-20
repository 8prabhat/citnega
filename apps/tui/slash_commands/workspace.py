"""
Workspace slash commands — /setworkfolder, /refresh, /createtool, /createagent,
/createworkflow, /createskill, /creatementalmodel.

Each create command supports TWO entry modes:

  Wizard mode  — /createtool               (no args)
    Multi-step guided interview; user fills in each field interactively.

  Prompt mode  — /createtool "a tool that scrapes a URL and returns clean text"
    User provides a natural-language description as args.  The LLM extracts
    a structured spec (name, parameters, system prompt, etc.) from that one
    line, displays a preview, then immediately kicks off code generation.
    No wizard steps; zero friction.

Both modes converge on the same code-generation → test → register pipeline.

Mental models (/creatementalmodel) are strategy constraints — not executable
code.  They compile into MentalModelSpec clauses that influence the planning
layer (ordering, risk posture, approval requirements, parallelism budget).
"""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
import re
from typing import TYPE_CHECKING

from citnega.packages.protocol.interfaces.slash_command import ISlashCommand

if TYPE_CHECKING:
    from collections.abc import Callable

    from citnega.apps.tui.controllers.chat_controller import ChatController
    from citnega.packages.protocol.interfaces.application_service import IApplicationService
    from citnega.packages.strategy.mental_models import MentalModelSpec

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
# WizardBase
# ---------------------------------------------------------------------------


class WizardBase:
    """
    Mixin that provides a reusable name-validation step for wizard commands.

    Subclasses can replace their `_on_name` body by having execute() set
    ``ctrl._pending_wizard`` with ``on_input=self._make_name_handler(step, next_fn)``.
    """

    def _start_name_step(
        self,
        ctrl: ChatController,
        step_name: str,
        next_step_fn: Callable,
        prompt: str = "",
    ) -> None:
        ctrl._pending_wizard = WizardState(
            step_name=step_name,
            on_input=self._make_name_handler(step_name, next_step_fn),
            prompt=prompt,
        )

    def _make_name_handler(
        self,
        step_name: str,
        next_step_fn: Callable,
    ) -> Any:
        async def _on_name(text: str, ctrl: ChatController) -> None:
            await self._validate_and_store_name(text, ctrl, step_name, next_step_fn)
        return _on_name

    async def _validate_and_store_name(
        self,
        text: str,
        ctrl: ChatController,
        step_name: str,
        next_step_fn: Callable,
    ) -> None:
        name = text.strip().lower().replace(" ", "_")
        if not name or not name.isidentifier():
            await ctrl._append_message(
                "system",
                f"'{name}' is not a valid Python identifier. Please use snake_case (e.g. my_name).",
            )
            ctrl._pending_wizard = WizardState(
                step_name=step_name,
                on_input=self._make_name_handler(step_name, next_step_fn),
            )
            return
        ctrl._wizard_data["name"] = name
        ctrl._wizard_data["class_name"] = _to_pascal(name)
        await next_step_fn(ctrl)


# ---------------------------------------------------------------------------
# /setworkfolder
# ---------------------------------------------------------------------------


class SetWorkfolderCommand(ISlashCommand):
    name = "setworkfolder"
    help_text = "Set (or show) the workspace folder. Usage: /setworkfolder [path]"

    def __init__(self, service: IApplicationService) -> None:
        self._service = service

    async def execute(self, args: list[str], app_context: ChatController) -> None:
        if not args:
            from citnega.packages.config.loaders import load_settings

            current = load_settings().workspace.workfolder_path or os.getcwd()
            await app_context._append_message(
                "system", f"Current workfolder: {current}\nUsage: /setworkfolder <absolute-path>"
            )
            return

        path_str = " ".join(args).strip().strip("'\"")
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
            f"Subdirectories created: agents/, tools/, workflows/, skills/, mental_models/\n"
            f"Use /createtool, /createagent, /createworkflow, /createskill, /creatementalmodel\n"
            f"to add artifacts, then /refresh to reload them.",
        )


# ---------------------------------------------------------------------------
# /refresh
# ---------------------------------------------------------------------------


class RefreshCommand(ISlashCommand):
    name = "refresh"
    help_text = "Scan workfolder and hot-load new/changed tools, agents, workflows."

    def __init__(self, service: IApplicationService) -> None:
        self._service = service

    async def execute(self, args: list[str], app_context: ChatController) -> None:
        from citnega.packages.config.loaders import load_settings

        settings = load_settings()
        workfolder_str = settings.workspace.workfolder_path or os.getcwd()
        workfolder = Path(workfolder_str)

        if not workfolder.is_dir():
            await app_context._append_message(
                "system",
                f"Workfolder '{workfolder}' does not exist. Use /setworkfolder <path> first.",
            )
            return

        loader = self._service.create_dynamic_loader()

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


class CreateToolCommand(WizardBase, ISlashCommand):
    name = "createtool"
    help_text = (
        "Create a new tool. "
        "Usage: /createtool [\"natural language description\"] "
        "— omit args for step-by-step wizard."
    )

    def __init__(self, service: IApplicationService) -> None:
        self._service = service

    async def execute(self, args: list[str], app_context: ChatController) -> None:
        if args:
            prompt = " ".join(args).strip().strip("\"'")
            await _prompt_driven_create(app_context, self._service, "tool", prompt)
            return

        app_context._wizard_data = {"kind": "tool", "params": []}
        await app_context._append_message(
            "system",
            "Creating a new tool.\n"
            "Tip: you can also run  /createtool \"describe your tool here\"  to skip the wizard.\n\n"
            "Step 1/3 — Enter a snake_case name for your tool (e.g. web_scraper):",
        )
        app_context._pending_wizard = WizardState(
            step_name="tool_name",
            on_input=self._make_name_handler("tool_name", self._after_name),
        )

    async def _after_name(self, ctrl: ChatController) -> None:
        name = ctrl._wizard_data["name"]
        await ctrl._append_message("system", f"Step 2/3 — Enter a description for '{name}':")
        ctrl._pending_wizard = WizardState("tool_desc", self._on_desc)

    async def _on_desc(self, text: str, ctrl: ChatController) -> None:
        ctrl._wizard_data["description"] = text.strip()
        await _ask_param_type_or_done(ctrl, self._on_param_start, self._finalize)

    async def _on_param_start(self, value: str, label: str, ctrl: ChatController) -> None:
        if value == "done":
            await self._finalize(ctrl)
            return
        ctrl._wizard_data["_current_param_type"] = value
        await ctrl._append_message("system", f"Parameter name for type '{value}':")
        ctrl._pending_wizard = WizardState("param_name", self._on_param_name)

    async def _on_param_name(self, text: str, ctrl: ChatController) -> None:
        pname = text.strip().lower().replace(" ", "_")
        ctrl._wizard_data["_current_param_name"] = pname
        await ctrl._append_message("system", f"Brief description for parameter '{pname}':")
        ctrl._pending_wizard = WizardState("param_desc", self._on_param_desc)

    async def _on_param_desc(self, text: str, ctrl: ChatController) -> None:
        ctrl._wizard_data["params"].append(
            {
                "name": ctrl._wizard_data.pop("_current_param_name"),
                "type": ctrl._wizard_data.pop("_current_param_type"),
                "description": text.strip(),
            }
        )
        await _ask_param_type_or_done(ctrl, self._on_param_start, self._finalize)

    async def _finalize(self, ctrl: ChatController) -> None:
        await _generate_and_register(ctrl, self._service)


# ---------------------------------------------------------------------------
# /createagent
# ---------------------------------------------------------------------------


class CreateAgentCommand(WizardBase, ISlashCommand):
    name = "createagent"
    help_text = (
        "Create a new specialist agent. "
        "Usage: /createagent [\"natural language description\"] "
        "— omit args for step-by-step wizard."
    )

    def __init__(self, service: IApplicationService) -> None:
        self._service = service

    async def execute(self, args: list[str], app_context: ChatController) -> None:
        if args:
            prompt = " ".join(args).strip().strip("\"'")
            await _prompt_driven_create(app_context, self._service, "agent", prompt)
            return

        app_context._wizard_data = {"kind": "agent", "tool_whitelist": []}
        await app_context._append_message(
            "system",
            "Creating a new specialist agent.\n"
            "Tip: you can also run  /createagent \"describe your agent here\"  to skip the wizard.\n\n"
            "Step 1/4 — Enter a snake_case name (e.g. research_agent):",
        )
        app_context._pending_wizard = WizardState(
            "agent_name", self._make_name_handler("agent_name", self._after_name)
        )

    async def _after_name(self, ctrl: ChatController) -> None:
        await ctrl._append_message("system", "Step 2/4 — Enter a description:")
        ctrl._pending_wizard = WizardState("agent_desc", self._on_desc)

    async def _on_desc(self, text: str, ctrl: ChatController) -> None:
        ctrl._wizard_data["description"] = text.strip()
        await ctrl._append_message(
            "system",
            "Step 3/4 — Enter a system prompt for this agent\n(or press Enter to use a default):",
        )
        ctrl._pending_wizard = WizardState("agent_prompt", self._on_prompt)

    async def _on_prompt(self, text: str, ctrl: ChatController) -> None:
        ctrl._wizard_data["system_prompt"] = text.strip()
        await _ask_tool_whitelist(ctrl, self._service, self._finalize)

    async def _finalize(self, ctrl: ChatController) -> None:
        await _generate_and_register(ctrl, self._service)


# ---------------------------------------------------------------------------
# /createworkflow
# ---------------------------------------------------------------------------


class CreateWorkflowCommand(WizardBase, ISlashCommand):
    name = "createworkflow"
    help_text = (
        "Create a YAML workflow template for plan execution. "
        "Usage: /createworkflow [\"natural language description\"] "
        "— omit args for step-by-step wizard."
    )

    def __init__(self, service: IApplicationService) -> None:
        self._service = service

    async def execute(self, args: list[str], app_context: ChatController) -> None:
        if args:
            prompt = " ".join(args).strip().strip("\"'")
            await _prompt_driven_workflow(app_context, self._service, prompt)
            return

        app_context._wizard_data = {
            "kind": "workflow",
            "tool_whitelist": [],
            "sub_agents": [],
        }
        await app_context._append_message(
            "system",
            "Creating a new workflow.\n"
            "Tip: you can also run  /createworkflow \"describe your workflow here\"  to skip the wizard.\n\n"
            "Step 1/4 — Enter a snake_case name (e.g. data_pipeline_workflow):",
        )
        app_context._pending_wizard = WizardState(
            "wf_name", self._make_name_handler("wf_name", self._after_name)
        )

    async def _after_name(self, ctrl: ChatController) -> None:
        await ctrl._append_message("system", "Step 2/4 — Describe what this workflow does:")
        ctrl._pending_wizard = WizardState("wf_desc", self._on_desc)

    async def _on_desc(self, text: str, ctrl: ChatController) -> None:
        ctrl._wizard_data["description"] = text.strip()
        await _ask_tool_whitelist(ctrl, self._service, self._on_tools_done)

    async def _on_tools_done(self, ctrl: ChatController) -> None:
        await _ask_sub_agents(ctrl, self._service, self._finalize)

    async def _finalize(self, ctrl: ChatController) -> None:
        await _write_workflow_template(ctrl, self._service)


# ---------------------------------------------------------------------------
# /createskill
# ---------------------------------------------------------------------------


class CreateSkillCommand(WizardBase, ISlashCommand):
    name = "createskill"
    help_text = (
        "Create a SKILL.md planning guidance bundle. "
        "Usage: /createskill [\"natural language description\"] "
        "— omit args for step-by-step wizard."
    )

    def __init__(self, service: IApplicationService) -> None:
        self._service = service

    async def execute(self, args: list[str], app_context: ChatController) -> None:
        if args:
            prompt = " ".join(args).strip().strip("\"'")
            await _prompt_driven_skill(app_context, self._service, prompt)
            return

        app_context._wizard_data = {
            "kind": "skill",
            "tool_whitelist": [],
            "sub_agents": [],
        }
        await app_context._append_message(
            "system",
            "Creating a new skill bundle.\n"
            "Tip: you can also run  /createskill \"describe your skill here\"  to skip the wizard.\n\n"
            "Step 1/4 — Enter a snake_case name (e.g. release_readiness):",
        )
        app_context._pending_wizard = WizardState(
            "skill_name", self._make_name_handler("skill_name", self._after_name)
        )

    async def _after_name(self, ctrl: ChatController) -> None:
        await ctrl._append_message("system", "Step 2/4 — Describe what this skill should optimize:")
        ctrl._pending_wizard = WizardState("skill_desc", self._on_desc)

    async def _on_desc(self, text: str, ctrl: ChatController) -> None:
        ctrl._wizard_data["description"] = text.strip()
        await ctrl._append_message(
            "system",
            "Step 3/4 — Optional comma-separated trigger phrases (or press Enter to skip):",
        )
        ctrl._pending_wizard = WizardState("skill_triggers", self._on_triggers)

    async def _on_triggers(self, text: str, ctrl: ChatController) -> None:
        raw = [item.strip() for item in text.split(",") if item.strip()]
        ctrl._wizard_data["triggers"] = raw
        await _ask_tool_whitelist(ctrl, self._service, self._on_tools_done)

    async def _on_tools_done(self, ctrl: ChatController) -> None:
        await _ask_sub_agents(ctrl, self._service, self._finalize)

    async def _finalize(self, ctrl: ChatController) -> None:
        await _write_skill_bundle(ctrl, self._service)


# ---------------------------------------------------------------------------
# /creatementalmodel
# ---------------------------------------------------------------------------


class CreateMentalModelCommand(WizardBase, ISlashCommand):
    """
    Create a mental-model constraint file in the workfolder.

    Mental models are NOT executable — they are strategy inputs that compile
    into structured MentalModelSpec clauses (ordering, risk, validation,
    approval, parallelism) and influence the planning layer for the session.

    Prompt mode (recommended):
        /creatementalmodel "always validate inputs; never run destructive ops
         without explicit approval; prefer sequential over parallel by default"

    Wizard mode (no args):
        Multi-step: name → constraint text → confirm
    """

    name = "creatementalmodel"
    help_text = (
        "Create a mental-model planning constraint file. "
        "Usage: /creatementalmodel [\"constraint text\"] "
        "— omit args for step-by-step wizard."
    )

    def __init__(self, service: IApplicationService) -> None:
        self._service = service

    async def execute(self, args: list[str], app_context: ChatController) -> None:
        if args:
            text = " ".join(args).strip().strip("\"'")
            await _prompt_driven_mental_model(app_context, self._service, text)
            return

        app_context._wizard_data = {"kind": "mental_model"}
        await app_context._append_message(
            "system",
            "Creating a mental-model constraint file.\n"
            "Mental models influence the planning layer — they are NOT executable code.\n"
            "Examples: ordering rules, risk posture, approval requirements, parallelism limits.\n\n"
            "Tip: you can also run  /creatementalmodel \"your constraints here\"  to skip the wizard.\n\n"
            "Step 1/2 — Enter a snake_case name (e.g. safe_execution_model):",
        )
        app_context._pending_wizard = WizardState(
            "mm_name", self._make_name_handler("mm_name", self._after_name)
        )

    async def _after_name(self, ctrl: ChatController) -> None:
        await ctrl._append_message(
            "system",
            "Step 2/2 — Enter your planning constraints as plain English sentences.\n"
            "Each sentence on its own line (or separated by semicolons).\n"
            "Examples:\n"
            "  Always validate inputs before executing any operation.\n"
            "  Never run file-deletion steps in parallel.\n"
            "  Require explicit approval before writing to production paths.\n"
            "  Prefer conservative risk posture for operations with side effects.",
        )
        ctrl._pending_wizard = WizardState("mm_text", self._on_text)

    async def _on_text(self, text: str, ctrl: ChatController) -> None:
        ctrl._wizard_data["constraint_text"] = text.strip()
        await _write_mental_model(ctrl, self._service)


# ---------------------------------------------------------------------------
# Shared wizard helpers
# ---------------------------------------------------------------------------


async def _ask_param_type_or_done(ctrl: ChatController, on_select, on_done) -> None:
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


async def _ask_tool_whitelist(ctrl: ChatController, service: IApplicationService, on_done) -> None:
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


async def _ask_sub_agents(ctrl: ChatController, service: IApplicationService, on_done) -> None:
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


# ---------------------------------------------------------------------------
# Prompt-driven paths — extract spec from natural language then run pipeline
# ---------------------------------------------------------------------------


async def _prompt_driven_create(
    app_context: ChatController, service: IApplicationService, kind: str, prompt: str
) -> None:
    """
    Prompt mode entry for tool and agent creation.

    Calls the LLM to extract a structured ScaffoldSpec from the user's one-line
    description, shows a preview, then runs the full generate → test → register
    pipeline without any wizard steps.
    """
    await app_context._append_message(
        "system",
        f"Analyzing prompt for {kind} creation…\n  \"{prompt}\"",
    )

    try:
        spec_dict = await _extract_spec_from_prompt(kind, prompt, service)
    except Exception as exc:
        await app_context._append_message(
            "system",
            f"Could not extract spec from prompt: {exc}\n"
            f"Try  /{kind[0:6]}  (no args) to use the wizard instead.",
        )
        return

    name = spec_dict.get("name", "")
    if not name or not name.isidentifier():
        await app_context._append_message(
            "system",
            f"Extracted name '{name}' is not a valid identifier.\n"
            f"Try  /create{kind}  (no args) to use the wizard instead.",
        )
        return

    # Build wizard_data so _generate_and_register can consume it
    app_context._wizard_data = {
        "kind": kind,
        "name": spec_dict["name"],
        "class_name": spec_dict.get("class_name") or _to_pascal(spec_dict["name"]),
        "description": spec_dict.get("description", prompt),
        "params": spec_dict.get("parameters", []),
        "system_prompt": spec_dict.get("system_prompt", ""),
        "tool_whitelist": spec_dict.get("tool_whitelist", []),
        "sub_agents": spec_dict.get("sub_agents", []),
    }

    # Show extracted spec preview
    preview_lines = [
        "Extracted spec:",
        f"  name        : {app_context._wizard_data['name']}",
        f"  class       : {app_context._wizard_data['class_name']}",
        f"  description : {app_context._wizard_data['description']}",
    ]
    if app_context._wizard_data["params"]:
        param_strs = [
            f"    {p['name']} ({p.get('type', 'str')}): {p.get('description', '')}"
            for p in app_context._wizard_data["params"]
        ]
        preview_lines.append("  parameters  :")
        preview_lines.extend(param_strs)
    if app_context._wizard_data["system_prompt"]:
        preview_lines.append(
            f"  system_prompt: {app_context._wizard_data['system_prompt'][:80]}…"
        )
    if app_context._wizard_data["tool_whitelist"]:
        preview_lines.append(f"  tools       : {app_context._wizard_data['tool_whitelist']}")
    preview_lines.append("\nGenerating code…")
    await app_context._append_message("system", "\n".join(preview_lines))

    await _generate_and_register(app_context, service)


async def _prompt_driven_workflow(
    app_context: ChatController, service: IApplicationService, prompt: str
) -> None:
    """Prompt mode entry for workflow YAML template creation."""
    await app_context._append_message(
        "system",
        f"Analyzing prompt for workflow creation…\n  \"{prompt}\"",
    )

    try:
        spec_dict = await _extract_spec_from_prompt("workflow", prompt, service)
    except Exception as exc:
        await app_context._append_message(
            "system",
            f"Could not extract workflow spec: {exc}\n"
            f"Try  /createworkflow  (no args) to use the wizard instead.",
        )
        return

    name = spec_dict.get("name", "")
    if not name or not name.isidentifier():
        await app_context._append_message(
            "system",
            f"Extracted name '{name}' is not a valid identifier.\n"
            f"Try  /createworkflow  (no args) to use the wizard instead.",
        )
        return

    app_context._wizard_data = {
        "kind": "workflow",
        "name": spec_dict["name"],
        "class_name": spec_dict.get("class_name") or _to_pascal(spec_dict["name"]),
        "description": spec_dict.get("description", prompt),
        "tool_whitelist": spec_dict.get("tool_whitelist", []),
        "sub_agents": spec_dict.get("sub_agents", []),
    }

    await app_context._append_message(
        "system",
        f"Extracted workflow spec:\n"
        f"  name       : {app_context._wizard_data['name']}\n"
        f"  description: {app_context._wizard_data['description']}\n"
        f"  tools      : {app_context._wizard_data['tool_whitelist']}\n"
        f"  agents     : {app_context._wizard_data['sub_agents']}\n"
        f"Writing YAML template…",
    )

    await _write_workflow_template(app_context, service)


async def _prompt_driven_skill(
    app_context: ChatController, service: IApplicationService, prompt: str
) -> None:
    """Prompt mode entry for skill bundle creation."""
    await app_context._append_message(
        "system",
        f"Analyzing prompt for skill creation…\n  \"{prompt}\"",
    )

    try:
        spec_dict = await _extract_spec_from_prompt("skill", prompt, service)
    except Exception as exc:
        await app_context._append_message(
            "system",
            f"Could not extract skill spec: {exc}\n"
            f"Try  /createskill  (no args) to use the wizard instead.",
        )
        return

    name = spec_dict.get("name", "")
    if not name or not name.isidentifier():
        await app_context._append_message(
            "system",
            f"Extracted name '{name}' is not a valid identifier.\n"
            f"Try  /createskill  (no args) to use the wizard instead.",
        )
        return

    app_context._wizard_data = {
        "kind": "skill",
        "name": spec_dict["name"],
        "description": spec_dict.get("description", prompt),
        "triggers": spec_dict.get("triggers", []),
        "tool_whitelist": spec_dict.get("preferred_tools", []),
        "sub_agents": spec_dict.get("preferred_agents", []),
        "guidance": spec_dict.get("guidance", []),
    }

    await app_context._append_message(
        "system",
        f"Extracted skill spec:\n"
        f"  name       : {app_context._wizard_data['name']}\n"
        f"  description: {app_context._wizard_data['description']}\n"
        f"  triggers   : {app_context._wizard_data['triggers']}\n"
        f"Writing SKILL.md bundle…",
    )

    await _write_skill_bundle(app_context, service)


async def _prompt_driven_mental_model(
    app_context: ChatController, service: IApplicationService, text: str
) -> None:
    """Prompt mode entry for mental model creation — derive name from content."""
    await app_context._append_message(
        "system",
        f"Compiling mental model from prompt…\n  \"{text[:120]}{'…' if len(text) > 120 else ''}\"",
    )

    # Derive a name from the first clause / first few words
    name = _derive_name_from_text(text)
    app_context._wizard_data = {
        "kind": "mental_model",
        "name": name,
        "constraint_text": text,
    }

    await app_context._append_message(
        "system",
        f"Derived name: {name}\nWriting mental model file…",
    )

    await _write_mental_model(app_context, service)


# ---------------------------------------------------------------------------
# LLM spec extractor — converts natural language → structured ScaffoldSpec dict
# ---------------------------------------------------------------------------

_SPEC_SYSTEM_PROMPT = """\
You are a spec extractor for the citnega AI-agent framework.
Given a natural-language description of an artifact, return ONLY a valid JSON object
with no markdown fences, no prose, no explanation — just the raw JSON.
"""

_SPEC_PROMPTS: dict[str, str] = {
    "tool": """\
Extract a tool spec from this description and return JSON with exactly these fields:
{
  "name": "snake_case_python_identifier",
  "class_name": "PascalCaseName",
  "description": "one clear sentence describing what the tool does",
  "parameters": [
    {"name": "param_name", "type": "str|int|float|bool", "description": "what it is"}
  ]
}
Rules:
- name must be a valid Python identifier in snake_case
- parameters should reflect the inputs the tool needs; if none are obvious use [{{"name":"query","type":"str","description":"Input to the tool."}}]
- description must be one sentence, actionable (starts with a verb)
Description: {prompt}""",

    "agent": """\
Extract an agent spec from this description and return JSON with exactly these fields:
{
  "name": "snake_case_python_identifier",
  "class_name": "PascalCaseName",
  "description": "one clear sentence describing what the agent does",
  "system_prompt": "detailed system prompt that instructs the agent how to behave",
  "tool_whitelist": ["tool_name_1", "tool_name_2"]
}
Rules:
- name must be a valid Python identifier in snake_case, ending in _agent
- system_prompt should be 2–4 sentences of clear behavioral instructions
- tool_whitelist should list tools from: {available_tools} (empty list if none relevant)
Description: {prompt}""",

    "workflow": """\
Extract a workflow spec from this description and return JSON with exactly these fields:
{
  "name": "snake_case_python_identifier",
  "class_name": "PascalCaseName",
  "description": "one clear sentence describing the workflow's goal",
  "tool_whitelist": ["tool_name_1"],
  "sub_agents": ["agent_name_1"]
}
Rules:
- name must be a valid Python identifier in snake_case, ending in _workflow
- Choose tools from: {available_tools}
- Choose agents from: {available_agents}
- If nothing matches leave the lists empty
Description: {prompt}""",

    "skill": """\
Extract a skill spec from this description and return JSON with exactly these fields:
{
  "name": "snake_case_python_identifier",
  "description": "one clear sentence describing what planning behavior this skill optimizes",
  "triggers": ["phrase that activates this skill", "another trigger phrase"],
  "preferred_tools": ["tool_name"],
  "preferred_agents": ["agent_name"],
  "guidance": [
    "- Concrete guidance bullet 1",
    "- Concrete guidance bullet 2",
    "- Concrete guidance bullet 3"
  ]
}
Rules:
- name must be a valid Python identifier in snake_case
- triggers are 1–4 short phrases (3–6 words each) that the planner matches against user intent
- guidance should be 3–6 actionable planning bullets (start with "- ")
Description: {prompt}""",
}


async def _extract_spec_from_prompt(
    kind: str, prompt: str, service: IApplicationService
) -> dict:
    """
    Call the model gateway to extract a structured spec dict from a natural-language prompt.
    Falls back to heuristic extraction if the gateway is unavailable.
    """
    gateway = getattr(service, "_model_gateway", None)

    # Build the extraction prompt
    available_tools = [t.name for t in service.list_tools()] if hasattr(service, "list_tools") else []
    available_agents = [a.name for a in service.list_agents()] if hasattr(service, "list_agents") else []

    template = _SPEC_PROMPTS.get(kind, _SPEC_PROMPTS["tool"])
    user_prompt = template.format(
        prompt=prompt,
        available_tools=available_tools,
        available_agents=available_agents,
    )

    if gateway is not None:
        try:
            from citnega.packages.protocol.models.model_gateway import ModelMessage, ModelRequest

            response = await gateway.generate(
                ModelRequest(
                    messages=[
                        ModelMessage(role="system", content=_SPEC_SYSTEM_PROMPT),
                        ModelMessage(role="user", content=user_prompt),
                    ],
                    stream=False,
                    temperature=0.1,
                )
            )
            raw = response.content.strip()
            # Strip any accidental markdown fences
            raw = re.sub(r"^```(?:json)?\s*\n?", "", raw)
            raw = re.sub(r"\n?```\s*$", "", raw)
            return json.loads(raw)
        except Exception:
            pass  # fall through to heuristic

    return _heuristic_spec(kind, prompt)


def _heuristic_spec(kind: str, prompt: str) -> dict:
    """
    Derive a minimal spec dict from the prompt without an LLM.
    Used as fallback when the model gateway is unavailable.
    """
    # Derive name: take first 4 words, snake_case, strip non-alpha
    words = re.sub(r"[^a-z0-9 ]", "", prompt.lower()).split()[:4]
    name = "_".join(w for w in words if w)[:40] or "generated_artifact"
    # Ensure it ends with an appropriate suffix
    if kind == "agent" and not name.endswith("_agent"):
        name = name.rstrip("_") + "_agent"
    if kind == "workflow" and not name.endswith("_workflow"):
        name = name.rstrip("_") + "_workflow"
    name = name if name.isidentifier() else re.sub(r"[^a-z0-9_]", "_", name)

    base: dict = {
        "name": name,
        "class_name": _to_pascal(name),
        "description": prompt[:200],
    }
    if kind == "tool":
        base["parameters"] = [{"name": "query", "type": "str", "description": "Input to the tool."}]
    elif kind == "agent":
        base["system_prompt"] = f"You are a specialist agent. {prompt}"
        base["tool_whitelist"] = []
    elif kind == "workflow":
        base["tool_whitelist"] = []
        base["sub_agents"] = []
    elif kind == "skill":
        base["triggers"] = []
        base["preferred_tools"] = []
        base["preferred_agents"] = []
        base["guidance"] = [f"- {prompt[:120]}"]
    return base


def _derive_name_from_text(text: str) -> str:
    """Derive a snake_case name from free-form constraint text."""
    words = re.sub(r"[^a-z0-9 ]", "", text.lower()).split()[:5]
    name = "_".join(w for w in words if len(w) > 2)[:40] or "custom_model"
    name = re.sub(r"_+", "_", name).strip("_")
    return name if name.isidentifier() else "custom_mental_model"


# ---------------------------------------------------------------------------
# Core generation pipeline (tool + agent)
# ---------------------------------------------------------------------------


async def _generate_and_register(ctrl: ChatController, service: IApplicationService) -> None:
    """
    Final pipeline — shared by wizard mode and prompt mode:

      1. Switch TUI to "coding" state (ContextBar + CodingBlock).
      2. Generate code with the LLM (streaming tokens to CodingBlock).
      3. Test the generated code (run _execute with mock inputs).
      4. If tests fail: retry up to 2 times, feeding the error back.
      5. Write the file, load it, register the callable.
      6. Reset TUI to "idle".
    """
    from textual.containers import VerticalScroll

    from citnega.apps.tui.widgets.coding_block import CodingBlock
    from citnega.packages.config.loaders import load_settings
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

    _set_run_state(ctrl, "coding")

    coding_block = CodingBlock(title=name, kind=kind)
    try:
        scroll = ctrl._app.screen.query_one("#chat-scroll", VerticalScroll)
        await scroll.mount(coding_block)
        ctrl._app.call_after_refresh(scroll.scroll_end)
    except Exception:
        coding_block = None

    async def _on_chunk(token: str) -> None:
        if coding_block is not None:
            coding_block.append_token(token)
            with contextlib.suppress(Exception):
                ctrl._app.call_after_refresh(scroll.scroll_end)

    async def _on_status(msg: str) -> None:
        if coding_block is not None:
            coding_block.set_status(msg)
            coding_block.clear_code()
        await ctrl._append_message("system", msg)

    loader = service.create_dynamic_loader()
    generator = ScaffoldGenerator(model_gateway=getattr(service, "_model_gateway", None))
    tester = CallableTester()

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

    settings = load_settings()
    workfolder = Path(settings.workspace.workfolder_path or os.getcwd())
    writer = WorkspaceWriter(workfolder)
    writer.ensure_dirs()

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


# ---------------------------------------------------------------------------
# Workflow YAML template writer
# ---------------------------------------------------------------------------


async def _write_workflow_template(ctrl: ChatController, service: IApplicationService) -> None:
    """Write a workflow YAML template — produces plan-execution template, not Python."""
    from citnega.packages.config.loaders import load_settings
    from citnega.packages.workspace.writer import WorkspaceWriter

    try:
        import yaml  # type: ignore[import-untyped]
    except Exception as exc:
        await ctrl._append_message("system", f"Workflow template generation requires PyYAML: {exc}")
        return

    data = ctrl._wizard_data
    name = data["name"]
    description = data.get("description", "").strip() or f"{name} workflow"
    capabilities = list(dict.fromkeys([*data.get("tool_whitelist", []), *data.get("sub_agents", [])]))
    if not capabilities:
        await ctrl._append_message(
            "system",
            "No tools or agents selected. Please include at least one capability for the workflow.",
        )
        return

    steps = []
    for index, capability in enumerate(capabilities, start=1):
        step_id = f"step{index}_{capability.replace('-', '_')}"
        steps.append(
            {
                "step_id": step_id,
                "capability_id": capability,
                "task": "Execute {objective}",
                "depends_on": [] if index == 1 else [steps[index - 2]["step_id"]],
                "can_run_in_parallel": False,
                "execution_target": "local",
            }
        )

    template = {
        "name": name,
        "description": description,
        "variables": {"objective": "High-level objective provided at compile time."},
        "supported_modes": ["plan", "code", "explore", "research", "review", "operate"],
        "max_parallelism": 1,
        "steps": steps,
    }
    source = yaml.safe_dump(template, sort_keys=False, allow_unicode=False)

    settings = load_settings()
    workfolder = Path(settings.workspace.workfolder_path or os.getcwd())
    writer = WorkspaceWriter(workfolder)
    writer.ensure_dirs()
    written_path = writer.write_workflow_template(name, source)

    service.invalidate_capability_cache()

    await ctrl._append_message(
        "system",
        f"Workflow template '{name}' created successfully.\nFile: {written_path}\n"
        f"Steps: {len(steps)} (capabilities: {', '.join(capabilities)})",
    )


# ---------------------------------------------------------------------------
# Skill bundle writer
# ---------------------------------------------------------------------------


async def _write_skill_bundle(ctrl: ChatController, service: IApplicationService) -> None:
    """Write a SKILL.md bundle with structured front matter and guidance body."""
    from citnega.packages.config.loaders import load_settings
    from citnega.packages.workspace.writer import WorkspaceWriter

    data = ctrl._wizard_data
    name = data["name"]
    description = data.get("description", "").strip() or name
    triggers = data.get("triggers", [])
    preferred_tools = data.get("tool_whitelist", [])
    preferred_agents = data.get("sub_agents", [])
    extra_guidance = data.get("guidance", [])

    front_matter = [
        "---",
        f"name: {name}",
        f"description: {description}",
        f"triggers: {triggers if triggers else []}",
        f"preferred_tools: {preferred_tools if preferred_tools else []}",
        f"preferred_agents: {preferred_agents if preferred_agents else []}",
        "supported_modes: [chat, plan, explore, research, code, review, operate]",
        "tags: []",
        "---",
        "",
    ]
    body = [
        f"# Skill: {name}",
        "",
        description,
        "",
        "## Guidance",
    ]
    if extra_guidance:
        body.extend(extra_guidance)
    else:
        body.extend([
            "- Use this skill to influence planning strategy and callable choice.",
            "- Prefer deterministic tools before broad reasoning steps when feasible.",
            "- Apply conservative risk posture unless explicitly directed otherwise.",
        ])

    source = "\n".join(front_matter + body).strip() + "\n"

    settings = load_settings()
    workfolder = Path(settings.workspace.workfolder_path or os.getcwd())
    writer = WorkspaceWriter(workfolder)
    writer.ensure_dirs()
    written_path = writer.write_skill(name, source)

    service.invalidate_capability_cache()

    await ctrl._append_message(
        "system",
        f"Skill bundle '{name}' created successfully.\nFile: {written_path}\n"
        f"Triggers: {triggers if triggers else '(none — matched by planner heuristic)'}",
    )


# ---------------------------------------------------------------------------
# Mental model writer
# ---------------------------------------------------------------------------


async def _write_mental_model(ctrl: ChatController, service: IApplicationService) -> None:
    """
    Compile and write a mental-model constraint file.

    Runs compile_mental_model() to parse the text into structured clauses,
    writes a Markdown file to workfolder/mental_models/<name>.md, and
    applies the compiled spec to the current session's strategy layer.
    """
    from citnega.packages.config.loaders import load_settings
    from citnega.packages.strategy.mental_models import compile_mental_model
    from citnega.packages.workspace.writer import WorkspaceWriter

    data = ctrl._wizard_data
    name = data["name"]
    raw_text = data.get("constraint_text", "").strip()

    if not raw_text:
        await ctrl._append_message("system", "No constraint text provided. Mental model not created.")
        return

    # Compile to structured spec for preview
    try:
        _emitter = getattr(service, "_emitter", None)
        _session_id = getattr(ctrl, "_session_id", "")
        spec = compile_mental_model(
            raw_text,
            session_id=_session_id,
            emitter=_emitter,
        )
    except Exception as exc:
        await ctrl._append_message("system", f"Failed to compile mental model: {exc}")
        return

    # Build the .md file
    clause_lines = [f"  - [{c.clause_type}] {c.text}" for c in spec.clauses]
    md_content = "\n".join([
        "---",
        f"name: {name}",
        f"risk_posture: {spec.risk_posture}",
        f"recommended_parallelism: {spec.recommended_parallelism}",
        "---",
        "",
        f"# Mental Model: {name}",
        "",
        "## Constraints",
        "",
        raw_text,
        "",
        "## Compiled Clauses",
        f"Risk posture: {spec.risk_posture}",
        f"Recommended parallelism: {spec.recommended_parallelism}",
        "",
        *clause_lines,
    ]) + "\n"

    settings = load_settings()
    workfolder = Path(settings.workspace.workfolder_path or os.getcwd())
    writer = WorkspaceWriter(workfolder)
    writer.ensure_dirs()

    # Write to mental_models/ subdir (create it if needed)
    mm_dir = Path(workfolder) / "mental_models"
    mm_dir.mkdir(parents=True, exist_ok=True)
    mm_path = mm_dir / f"{name}.md"
    mm_path.write_text(md_content, encoding="utf-8")

    # Apply to current session if possible
    _apply_mental_model_to_session(ctrl, service, spec)

    clause_summary = "\n".join(f"  {i+1}. [{c.clause_type}] {c.text}" for i, c in enumerate(spec.clauses))
    await ctrl._append_message(
        "system",
        f"Mental model '{name}' created and applied to current session.\n"
        f"File: {mm_path}\n\n"
        f"Compiled clauses ({len(spec.clauses)}):\n{clause_summary}\n\n"
        f"Risk posture: {spec.risk_posture}  |  "
        f"Recommended parallelism: {spec.recommended_parallelism}",
    )


def _apply_mental_model_to_session(ctrl: ChatController, service: IApplicationService, spec: MentalModelSpec) -> None:
    """
    Apply compiled MentalModelSpec clauses to the active session's StrategySpec
    and persist via ApplicationService.update_session_strategy().
    """
    import asyncio

    session_id = getattr(ctrl, "_session_id", None)
    if session_id is None:
        return

    if not callable(getattr(service, "update_session_strategy", None)):
        return

    from citnega.packages.strategy.models import StrategySpec

    # Build an updated StrategySpec — start from existing or create fresh.
    loop = None
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        pass

    async def _update() -> None:
        try:
            session = await service.get_session(session_id)
            existing_strategy = session.strategy_spec if session else None
            if existing_strategy is None:
                existing_strategy = StrategySpec()
            clauses = list(existing_strategy.mental_model_clauses or [])
            clauses.extend(spec.clauses)
            updated = existing_strategy.model_copy(update={
                "mental_model_clauses": clauses,
                **({"risk_posture": spec.risk_posture} if spec.risk_posture != "balanced" else {}),
                **({"parallelism_budget": spec.recommended_parallelism} if spec.recommended_parallelism > 1 else {}),
            })
            await service.update_session_strategy(session_id, updated)
        except Exception as exc:
            from citnega.packages.observability.logging_setup import runtime_logger
            runtime_logger.warning("apply_mental_model_failed", session_id=session_id, error=str(exc))

    if loop is not None and loop.is_running():
        loop.create_task(_update())
    else:
        asyncio.run(_update())


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _set_run_state(ctrl: ChatController, state: str) -> None:
    """Update the ContextBar run_state safely (no-op if TUI unavailable)."""
    try:
        from citnega.apps.tui.widgets.context_bar import ContextBar

        ctrl._app.screen.query_one(ContextBar).state = state
    except Exception:
        pass


def _to_pascal(snake: str) -> str:
    """Convert snake_case to PascalCase.  e.g. web_scraper_tool → WebScraperTool"""
    return "".join(word.capitalize() for word in snake.split("_"))
