"""Built-in slash commands for the TUI."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from citnega.packages.protocol.interfaces.slash_command import ISlashCommand

if TYPE_CHECKING:
    from citnega.apps.tui.controllers.chat_controller import ChatController
    from citnega.packages.protocol.interfaces.application_service import IApplicationService


class HelpCommand(ISlashCommand):
    name = "help"
    help_text = "Show available slash commands."

    async def execute(self, args: list[str], app_context: ChatController) -> None:
        lines = ["Available commands:"]
        for cmd_name, cmd in app_context._slash_commands.items():
            lines.append(f"  /{cmd_name:<12} {cmd.help_text}")
        await app_context._append_message("system", "\n".join(lines))


class CancelCommand(ISlashCommand):
    name = "cancel"
    help_text = "Cancel the currently running turn."

    def __init__(self, service: IApplicationService) -> None:
        self._service = service

    async def execute(self, args: list[str], app_context: ChatController) -> None:
        # Find the current run_id from the consumer worker
        consumer = app_context._consumer
        if consumer is None:
            await app_context._append_message("system", "No active run to cancel.")
            return
        run_id = consumer._run_id
        try:
            await self._service.cancel_run(run_id)
            await app_context._append_message("system", f"Run {run_id[:8]} cancelled.")
        except Exception as exc:
            await app_context._append_message("system", f"Cancel failed: {exc}")


class ClearCommand(ISlashCommand):
    name = "clear"
    help_text = "Clear the chat window."

    async def execute(self, args: list[str], app_context: ChatController) -> None:
        screen = app_context._app.screen
        screen.action_clear_chat()


class ModelCommand(ISlashCommand):
    name = "model"
    help_text = "Show or switch the active model. Usage: /model [model_id]"

    def __init__(self, service: IApplicationService) -> None:
        self._service = service

    async def execute(self, args: list[str], app_context: ChatController) -> None:
        models = self._service.list_models()
        session_id = getattr(app_context, "_session_id", None)
        active_id = self._service.get_session_model(session_id) if session_id else None

        if not args:
            # ── Interactive picker ─────────────────────────────────────────
            if not models:
                await app_context._append_message(
                    "system", "No models available. Check packages/model_gateway/models.yaml."
                )
                return

            options = [
                (
                    m.model_id,
                    f"{'* ' if m.model_id == active_id else '  '}"
                    f"{m.model_id}  (priority={m.priority})",
                )
                for m in models
            ]

            async def _on_select(value: str, label: str) -> None:
                await self._switch_model(app_context, session_id, value)

            await app_context._append_picker(
                title=f"Select model  [active: {active_id or 'none'}]",
                options=options,
                on_select=_on_select,
            )
            # Also show the manual hint as plain text
            model_ids = [m.model_id for m in models]
            await app_context._append_message(
                "system",
                f"Tip: you can also type  /model <model_id>  directly.\n"
                f"Available: {', '.join(model_ids)}",
            )
            return

        # ── Manual / scripted path: /model <model_id> ─────────────────────
        await self._switch_model(app_context, session_id, args[0])

    async def _switch_model(self, app_context: ChatController, session_id: str | None, model_id: str) -> None:
        models = self._service.list_models()
        model_ids = [m.model_id for m in models]
        if model_id not in model_ids:
            await app_context._append_message(
                "system", f"Unknown model '{model_id}'.\nAvailable: {', '.join(model_ids)}"
            )
            return
        if not session_id:
            await app_context._append_message("system", "No active session.")
            return
        try:
            await self._service.set_session_model(session_id, model_id)
            await app_context._append_message("system", f"Switched to model: {model_id}")
            app_context._update_context_bar(model=model_id)
        except Exception as exc:
            await app_context._append_message("system", f"Model switch failed: {exc}")


class ModeCommand(ISlashCommand):
    name = "mode"
    help_text = (
        "Show or switch session mode. Usage: "
        "/mode [chat|plan|explore|research|code|review|operate]"
    )

    def __init__(self, service: IApplicationService) -> None:
        self._service = service

    async def execute(self, args: list[str], app_context: ChatController) -> None:
        from citnega.packages.protocol.modes import all_modes

        session_id = getattr(app_context, "_session_id", None)
        current = self._service.get_session_mode(session_id) if session_id else "chat"

        if not args:
            # ── Interactive picker ─────────────────────────────────────────
            options = [
                (
                    m.name,
                    f"{'* ' if m.name == current else '  '}{m.name:<10}  — {m.description}",
                )
                for m in all_modes()
            ]

            async def _on_select(value: str, label: str) -> None:
                await self._switch_mode(app_context, session_id, value)

            await app_context._append_picker(
                title=f"Select mode  [active: {current}]",
                options=options,
                on_select=_on_select,
            )
            await app_context._append_message(
                "system",
                f"Tip: you can also type  /mode <name>  directly.\n"
                f"Available: {', '.join(m.name for m in all_modes())}",
            )
            return

        # ── Manual path: /mode <name> ──────────────────────────────────────
        await self._switch_mode(app_context, session_id, args[0].lower())

    async def _switch_mode(self, app_context: ChatController, session_id: str | None, requested: str) -> None:
        from citnega.packages.protocol.modes import all_modes, get_mode

        valid = [m.name for m in all_modes()]
        if requested not in valid:
            await app_context._append_message(
                "system", f"Unknown mode '{requested}'. Available: {', '.join(valid)}"
            )
            return
        if not session_id:
            await app_context._append_message("system", "No active session.")
            return
        try:
            await self._service.set_session_mode(session_id, requested)
            mode_obj = get_mode(requested)
            label = mode_obj.display_label or "[CHAT]"
            app_context._update_context_bar(mode=requested)
            await app_context._append_message(
                "system", f"{label} Mode active — {mode_obj.description}"
            )
        except Exception as exc:
            await app_context._append_message("system", f"Mode switch failed: {exc}")


class ThinkCommand(ISlashCommand):
    name = "think"
    help_text = "Toggle thinking tokens. Usage: /think [on|off|auto]"

    def __init__(self, service: IApplicationService) -> None:
        self._service = service

    async def execute(self, args: list[str], app_context: ChatController) -> None:
        session_id = getattr(app_context, "_session_id", None)
        if not session_id:
            await app_context._append_message("system", "No active session.")
            return

        if not args:
            # Show current state
            override = self._service.get_session_thinking(session_id)
            if override is None:
                status = "auto (model default from models.yaml)"
            elif override:
                status = "on (forced)"
            else:
                status = "off (forced)"
            await app_context._append_message(
                "system", f"Thinking: {status}\n\nUsage: /think on | /think off | /think auto"
            )
            return

        arg = args[0].lower()
        if arg == "on":
            value: bool | None = True
        elif arg == "off":
            value = False
        elif arg == "auto":
            value = None
        else:
            await app_context._append_message(
                "system", f"Unknown option '{arg}'. Use: /think on | /think off | /think auto"
            )
            return

        try:
            await self._service.set_session_thinking(session_id, value)
            label = {True: "on", False: "off", None: "auto"}[value]
            app_context._update_context_bar(think=label)
            await app_context._append_message("system", f"Thinking set to: {label}")
        except Exception as exc:
            await app_context._append_message("system", f"Failed: {exc}")


class ApproveCommand(ISlashCommand):
    name = "approve"
    help_text = "Approve a pending tool call. Usage: /approve <approval_id> [--deny]"

    def __init__(self, service: IApplicationService) -> None:
        self._service = service

    async def execute(self, args: list[str], app_context: ChatController) -> None:
        if not args:
            await app_context._append_message("system", "Usage: /approve <approval_id> [--deny]")
            return
        approval_id = args[0]
        deny = "--deny" in args
        try:
            await self._service.respond_to_approval(approval_id, approved=not deny)
            verb = "denied" if deny else "approved"
            await app_context._append_message("system", f"Approval {approval_id[:8]} {verb}.")
        except Exception as exc:
            await app_context._append_message("system", f"Approval error: {exc}")


class AgentCommand(ISlashCommand):
    name = "agent"
    help_text = "List available agents and tools. Usage: /agent [agents|tools]"

    def __init__(self, service: IApplicationService) -> None:
        self._service = service

    async def execute(self, args: list[str], app_context: ChatController) -> None:
        sub = args[0].lower() if args else "all"

        if sub in ("all", "agents"):
            agents = self._service.list_agents()
            if agents:
                lines = [f"Agents ({len(agents)}):"]
                for a in sorted(agents, key=lambda m: m.name):
                    lines.append(f"  {a.name:<30} {a.description or ''}")
            else:
                lines = ["No agents registered."]

            if sub == "all":
                lines.append("")

        if sub in ("all", "tools"):
            tools = self._service.list_tools()
            if tools:
                if sub == "all":
                    lines.append(f"Tools ({len(tools)}):")
                else:
                    lines = [f"Tools ({len(tools)}):"]
                for t in sorted(tools, key=lambda m: m.name):
                    lines.append(f"  {t.name:<30} {t.description or ''}")
            else:
                if sub == "tools":
                    lines = ["No tools registered."]
                else:
                    lines.append("No tools registered.")

        if sub not in ("all", "agents", "tools"):
            await app_context._append_message("system", "Usage: /agent [agents|tools]")
            return

        await app_context._append_message("system", "\n".join(lines))


class NewSessionCommand(ISlashCommand):
    name = "new"
    help_text = "Clear the current chat and start a fresh session."

    def __init__(self, service: IApplicationService) -> None:
        self._service = service

    async def execute(self, args: list[str], app_context: ChatController) -> None:
        import uuid

        from citnega.packages.protocol.models.sessions import SessionConfig

        try:
            framework = "direct"
            default_model_id = ""
            try:
                frameworks = self._service.list_frameworks()
                if isinstance(frameworks, list) and frameworks and isinstance(frameworks[0], str):
                    framework = frameworks[0]
            except Exception:
                pass
            try:
                models = self._service.list_models()
                if isinstance(models, list) and models and isinstance(models[0].model_id, str):
                    default_model_id = models[0].model_id
            except Exception:
                pass

            cfg = SessionConfig(
                session_id=str(uuid.uuid4()),
                name="new-session",
                framework=framework,
                default_model_id=default_model_id,
            )
            session = await self._service.create_session(cfg)
            # Update context
            app_context._session_id = session.config.session_id
            app_context._app._session_id = session.config.session_id

            # Clear the chat window
            screen = app_context._app.screen
            screen.action_clear_chat()

            app_context._update_context_bar(session_id=session.config.session_id)
            await app_context._append_message(
                "system",
                f"New session started: {session.config.session_id[:8]}…\n"
                "Previous session is still available via /sessions.",
            )
        except Exception as exc:
            await app_context._append_message("system", f"Failed to create session: {exc}")


class SessionsCommand(ISlashCommand):
    name = "sessions"
    help_text = "Show all sessions or switch to one. Usage: /sessions [session_id]"

    def __init__(self, service: IApplicationService) -> None:
        self._service = service

    async def execute(self, args: list[str], app_context: ChatController) -> None:
        try:
            sessions = await self._service.list_sessions()
        except Exception as exc:
            await app_context._append_message("system", f"Failed to list sessions: {exc}")
            return

        if args:
            # ── Manual path: /sessions <id_prefix> ────────────────────────
            target_prefix = args[0].lower()
            match = next(
                (s for s in sessions if s.config.session_id.startswith(target_prefix)),
                None,
            )
            if match is None:
                await app_context._append_message(
                    "system", f"No session matching '{target_prefix}'."
                )
                return
            await self._switch_session(app_context, match)
            return

        # ── Interactive picker ─────────────────────────────────────────────
        current = getattr(app_context, "_session_id", None)

        _NEW_SESSION_SENTINEL = "__new__"

        options = [(_NEW_SESSION_SENTINEL, "  + New session")]

        if sessions:
            from citnega.apps.tui.screens.session_picker import _format_age
            sessions.sort(key=lambda s: s.last_active_at or "", reverse=True)
            for s in sessions:
                age = _format_age(s.last_active_at) if s.last_active_at else "?"
                marker = "* " if s.config.session_id == current else "  "
                label = f"{marker}{s.config.name:<28}  {s.config.session_id[:8]}  {age}"
                options.append((s.config.session_id, label))

        async def _on_select(value: str, label: str) -> None:
            if value == _NEW_SESSION_SENTINEL:
                await NewSessionCommand(self._service).execute([], app_context)
                return
            target = next((s for s in sessions if s.config.session_id == value), None)
            if target:
                await self._switch_session(app_context, target)

        await app_context._append_picker(
            title=f"Sessions  [{len(sessions)} saved]",
            options=options,
            on_select=_on_select,
        )

    async def _switch_session(self, app_context: ChatController, session) -> None:
        from textual.containers import VerticalScroll

        sid = session.config.session_id
        app_context._session_id = sid
        app_context._app._session_id = sid

        # ── Hard-clear chat with await so removal is complete before
        #    we start mounting history.
        screen = app_context._app.screen
        try:
            scroll = screen.query_one("#chat-scroll", VerticalScroll)
            await scroll.remove_children()
        except Exception:
            scroll = None

        app_context._update_context_bar(session_id=sid)

        # ── Load message history of the selected session ──────────────────
        messages_loaded = 0
        raw_messages = []
        try:
            raw_messages = self._service.get_conversation_messages(sid)
            for msg in raw_messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if not content:
                    continue
                if role in ("user", "assistant"):
                    await app_context._append_message(role, content)
                    messages_loaded += 1
                elif role == "system" and content.startswith("[Compacted"):
                    await app_context._append_message("system", content)
                    messages_loaded += 1
        except Exception:
            pass

        # ── Restore tool call / agent call history inline ─────────────────
        if scroll is not None:
            try:
                from citnega.apps.tui.widgets.agent_call_block import AgentCallBlock
                from citnega.apps.tui.widgets.tool_call_block import ToolCallBlock

                tool_history = self._service.get_session_tool_history(sid)
                for entry in tool_history[-50:]:  # show last 50
                    ct = entry.get("callable_type", "tool")
                    is_agent = ct in ("specialist", "core")
                    if is_agent:
                        block = AgentCallBlock(
                            agent_name=entry.get("name", "?"),
                            input_summary=entry.get("input_summary", ""),
                        )
                    else:
                        block = ToolCallBlock(
                            tool_name=entry.get("name", "?"),
                            input_summary=entry.get("input_summary", ""),
                        )
                    await scroll.mount(block)
                    if entry.get("success", True):
                        block.set_result(entry.get("output_summary", ""))
                    else:
                        block.set_error(entry.get("output_summary", ""))
            except Exception:
                pass

        # ── Seed SmartInput arrow-key history ─────────────────────────────
        try:
            from citnega.apps.tui.widgets.smart_input import SmartInput

            smart = screen.query_one("#chat-input", SmartInput)
            user_msgs = [
                m["content"]
                for m in raw_messages
                if m.get("role") == "user" and m.get("content")
            ]
            smart.seed_history(user_msgs)
        except Exception:
            pass

        # ── Restore placeholder if chat is still empty ────────────────────
        if scroll is not None and messages_loaded == 0 and not scroll.query("#empty-hint"):
            try:
                from citnega.apps.tui.widgets.welcome_banner import WelcomeBanner
                await scroll.mount(WelcomeBanner(id="empty-hint"))
            except Exception:
                pass

        await app_context._append_message(
            "system", f"Switched to: {session.config.name}  [{sid[:8]}…]"
        )


class CompactCommand(ISlashCommand):
    name = "compact"
    help_text = "Compact the conversation history. Usage: /compact [keep_recent_count]"

    def __init__(self, service: IApplicationService) -> None:
        self._service = service

    async def execute(self, args: list[str], app_context: ChatController) -> None:
        session_id = getattr(app_context, "_session_id", None)
        if not session_id:
            await app_context._append_message("system", "No active session.")
            return

        keep_recent: int | None = None
        if args:
            try:
                keep_recent = int(args[0])
            except ValueError:
                await app_context._append_message("system", "Usage: /compact [keep_recent_count]")
                return

        await app_context._append_message("system", "Compacting conversation…")
        try:
            archived = await self._service.compact_conversation(session_id, keep_recent)
            if archived == 0:
                await app_context._append_message(
                    "system", "Nothing to compact (conversation is already short)."
                )
            else:
                stats = self._service.get_conversation_stats(session_id)
                await app_context._append_message(
                    "system",
                    f"Compacted {archived} messages.\n"
                    f"Remaining: {stats['message_count']} messages "
                    f"(~{stats['token_estimate']} tokens).",
                )
        except Exception as exc:
            await app_context._append_message("system", f"Compact failed: {exc}")


class RenameCommand(ISlashCommand):
    name = "rename"
    help_text = "Rename the current session. Usage: /rename <new_name>"

    def __init__(self, service: IApplicationService) -> None:
        self._service = service

    async def execute(self, args: list[str], app_context: ChatController) -> None:
        session_id = getattr(app_context, "_session_id", None)
        if not session_id:
            await app_context._append_message("system", "No active session.")
            return
        if not args:
            await app_context._append_message("system", "Usage: /rename <new_name>")
            return
        new_name = " ".join(args).strip()
        if not new_name:
            await app_context._append_message("system", "New name must not be empty.")
            return
        try:
            await self._service.rename_session(session_id, new_name)
            app_context._update_context_bar(session_name=new_name)
            await app_context._append_message(
                "system", f"Session renamed to: {new_name!r}"
            )
        except Exception as exc:
            await app_context._append_message("system", f"Rename failed: {exc}")


class DeleteSessionCommand(ISlashCommand):
    name = "delete"
    help_text = "Delete the current session and start a new one. Usage: /delete [--yes]"

    def __init__(self, service: IApplicationService) -> None:
        self._service = service

    async def execute(self, args: list[str], app_context: ChatController) -> None:
        session_id = getattr(app_context, "_session_id", None)
        if not session_id:
            await app_context._append_message("system", "No active session to delete.")
            return

        skip_confirm = "--yes" in args or "-y" in args

        if not skip_confirm:
            await app_context._append_message(
                "system",
                f"Delete session {session_id[:8]}…? Type  /delete --yes  to confirm.",
            )
            return

        try:
            await self._service.delete_session(session_id)
            await app_context._append_message(
                "system", f"Session {session_id[:8]}… deleted."
            )
            # Start a fresh session automatically
            await NewSessionCommand(self._service).execute([], app_context)
        except Exception as exc:
            await app_context._append_message("system", f"Delete failed: {exc}")


class ShowSessionCommand(ISlashCommand):
    name = "show"
    help_text = "Show details for the current session."

    def __init__(self, service: IApplicationService) -> None:
        self._service = service

    async def execute(self, args: list[str], app_context: ChatController) -> None:
        session_id = getattr(app_context, "_session_id", None)
        if not session_id:
            await app_context._append_message("system", "No active session.")
            return
        try:
            session = await self._service.get_session(session_id)
            if session is None:
                await app_context._append_message("system", "Session not found.")
                return
            lines = [
                f"id:        {session.config.session_id}",
                f"name:      {session.config.name}",
                f"framework: {session.config.framework}",
                f"model:     {session.config.default_model_id}",
                f"state:     {session.state.value}",
                f"runs:      {session.run_count}",
                f"created:   {session.created_at.isoformat()}",
                f"active:    {session.last_active_at.isoformat()}",
            ]
            await app_context._append_message("system", "\n".join(lines))
        except Exception as exc:
            await app_context._append_message("system", f"Show failed: {exc}")


_SKILL_GROUPS: dict[str, list[str]] = {
    "Core":                ["security_review", "code_review", "research_protocol", "debug_session", "deploy_checklist"],
    "Business & Finance":  ["requirements_gathering", "stakeholder_report", "variance_analysis", "audit_protocol"],
    "Data & ML":           ["eda_protocol", "dashboard_design", "ml_experiment", "model_review", "model_deployment"],
    "Operations & SRE":    ["incident_response", "postmortem"],
    "Risk & Legal":        ["risk_assessment", "control_testing", "contract_review", "legal_research_protocol"],
}


class SkillsCommand(ISlashCommand):
    name = "skills"
    help_text = "List all available built-in skills grouped by domain."

    async def execute(self, args: list[str], app_context: ChatController) -> None:
        from citnega.packages.skills.builtins import BUILTIN_SKILL_INDEX

        lines = ["Built-in skills  (use /skill <name> to activate)\n"]
        listed: set[str] = set()

        for group, names in _SKILL_GROUPS.items():
            lines.append(f"◆ {group}")
            for name in names:
                s = BUILTIN_SKILL_INDEX.get(name)
                if not s:
                    continue
                listed.add(name)
                modes = ", ".join(s.get("supported_modes", []))
                lines.append(f"  {name:<26} {s['description'][:55]}")
                lines.append(f"  {'':26} modes: [{modes}]")
            lines.append("")

        # Any skills not in a named group
        remaining = [s for s in BUILTIN_SKILL_INDEX if s not in listed]
        if remaining:
            lines.append("◆ Other")
            for name in remaining:
                s = BUILTIN_SKILL_INDEX[name]
                lines.append(f"  {name:<26} {s['description'][:55]}")

        await app_context._append_message("system", "\n".join(lines))


class SkillCommand(ISlashCommand):
    name = "skill"
    help_text = "Activate or show a skill. Usage: /skill <name> | /skill list"

    async def execute(self, args: list[str], app_context: ChatController) -> None:
        from citnega.packages.skills.builtins import BUILTIN_SKILL_INDEX

        if not args or args[0] in ("list", "ls"):
            names = list(BUILTIN_SKILL_INDEX.keys())
            await app_context._append_message(
                "system",
                f"Built-in skills: {', '.join(names)}\n"
                "Usage: /skill <name>  to activate one, or /skills to see descriptions.",
            )
            return

        skill_name = args[0].lower().strip()
        skill_dict = BUILTIN_SKILL_INDEX.get(skill_name)
        if skill_dict is None:
            # Fuzzy match: find skills whose name contains the query or vice-versa
            candidates = [n for n in BUILTIN_SKILL_INDEX if skill_name in n or n.startswith(skill_name)]
            if not candidates:
                # Fallback: any skill where any word in the name matches
                words = skill_name.replace("-", "_").split("_")
                candidates = [n for n in BUILTIN_SKILL_INDEX if any(w in n for w in words if len(w) > 2)]
            if len(candidates) == 1:
                skill_name = candidates[0]
                skill_dict = BUILTIN_SKILL_INDEX[skill_name]
            else:
                suggestion = f"\nDid you mean: {', '.join(candidates)}?" if candidates else ""
                await app_context._append_message(
                    "system",
                    f"Unknown skill '{args[0]}'.{suggestion}\n"
                    f"Available: {', '.join(BUILTIN_SKILL_INDEX.keys())}",
                )
                return

        # Show the skill body so the user knows what protocol is now active
        body = skill_dict.get("body", "")
        triggers = ", ".join(skill_dict.get("triggers", []))
        await app_context._append_message(
            "system",
            f"Skill '{skill_name}' is now active for this session.\n\n"
            f"{body}\n\nTriggers: {triggers}",
        )


# ── /setup ────────────────────────────────────────────────────────────────────


class SetupCommand(ISlashCommand):
    """
    Interactive setup wizard — API keys, local models, default model, full settings.

    Usage:
      /setup             → show top-level picker
      /setup api         → go directly to API key picker
      /setup ollama      → go directly to local model setup
      /setup model       → go directly to default model picker
    """

    name = "setup"
    help_text = "Interactive setup: API keys, local model server, default model."

    def __init__(self, service: IApplicationService) -> None:
        self._service = service

    async def execute(self, args: list[str], ctrl: ChatController) -> None:
        shortcut = args[0].lower() if args else ""
        if shortcut in ("api", "apikey", "keys"):
            await self._step_api_picker(ctrl)
        elif shortcut in ("ollama", "local", "lm", "lmstudio"):
            await self._step_local_model(ctrl)
        elif shortcut in ("model", "default"):
            await self._step_default_model(ctrl)
        else:
            await self._step_top(ctrl)

    # ── Top-level picker ──────────────────────────────────────────────────────

    async def _step_top(self, ctrl: ChatController) -> None:
        options = [
            ("api",    "  API Keys    — Anthropic, OpenAI, Gemini, OpenRouter"),
            ("ollama", "  Local Model — Ollama / LM Studio endpoint"),
            ("model",  "  Default Model — choose which model is used by default"),
            ("full",   "  Full Settings — open the F2 settings panel"),
        ]

        async def on_select(value: str, label: str) -> None:
            if value == "api":
                await self._step_api_picker(ctrl)
            elif value == "ollama":
                await self._step_local_model(ctrl)
            elif value == "model":
                await self._step_default_model(ctrl)
            elif value == "full":
                from citnega.apps.tui.screens.settings_screen import SettingsScreen
                svc = getattr(ctrl._app, "_service", None)
                ctrl._app.push_screen(SettingsScreen(service=svc))

        await ctrl._append_picker(
            title="⚙ Setup — What would you like to configure?",
            options=options,
            on_select=on_select,
        )

    # ── API key setup ─────────────────────────────────────────────────────────

    async def _step_api_picker(self, ctrl: ChatController) -> None:
        _PROVIDERS = [
            ("ANTHROPIC_API_KEY",          "  Anthropic  (claude-* models)"),
            ("OPENAI_API_KEY",             "  OpenAI  (gpt-* models)"),
            ("GEMINI_API_KEY",             "  Google Gemini  (gemini-* models)"),
            ("CITNEGA_OPENROUTER_API_KEY", "  OpenRouter  (multi-provider hub)"),
            ("GROQ_API_KEY",               "  Groq  (fast inference)"),
            ("other",                      "  Other — custom env var name"),
        ]

        def _status(env_var: str) -> str:
            return " [set]" if os.environ.get(env_var) else ""

        options = [
            (env_var, label + _status(env_var))
            for env_var, label in _PROVIDERS
        ]

        async def on_select(value: str, label: str) -> None:
            if value == "other":
                await self._ask_custom_var(ctrl)
            else:
                await self._ask_api_key(ctrl, value)

        await ctrl._append_picker(
            title="Which provider's API key?",
            options=options,
            on_select=on_select,
        )

    async def _ask_api_key(self, ctrl: ChatController, env_var: str) -> None:
        current_masked = "****" + os.environ[env_var][-4:] if os.environ.get(env_var) else "not set"
        await ctrl._append_message(
            "system",
            f"Setting  {env_var}  (currently: {current_masked})\n\n"
            f"Type your API key and press Ctrl+Enter.\n"
            f"The key will be active immediately for this session and persisted to config.",
        )

        async def on_key_input(text: str, _ctrl: ChatController) -> None:
            key = text.strip()
            if not key:
                await _ctrl._append_message("system", "Empty input — cancelled.")
                return
            os.environ[env_var] = key
            self._persist_env_var(env_var, key, _ctrl)
            if "OPENROUTER" in env_var:
                self._save_openrouter_to_settings(key, _ctrl)
            masked = key[:4] + "…" + key[-4:] if len(key) > 8 else "****"
            await _ctrl._append_message(
                "system",
                f"✓  {env_var} = {masked}\n"
                f"Active for this session. Saved to config/.env.\n"
                f"For permanent shell-level setup, add to ~/.zshrc or ~/.bashrc:\n"
                f"  export {env_var}=<your_key>",
            )

        from citnega.apps.tui.slash_commands.workspace import WizardState
        ctrl._pending_wizard = WizardState(
            step_name="api_key_input",
            on_input=on_key_input,
        )

    async def _ask_custom_var(self, ctrl: ChatController) -> None:
        await ctrl._append_message(
            "system",
            "Enter the environment variable name and value separated by a space:\n"
            "  MY_CUSTOM_API_KEY  sk-abc123…\n\n"
            "Press Ctrl+Enter to confirm.",
        )

        async def on_input(text: str, _ctrl: ChatController) -> None:
            parts = text.strip().split(None, 1)
            if len(parts) < 2:
                await _ctrl._append_message("system", "Invalid format. Expected: VAR_NAME value")
                return
            var_name, value = parts[0].upper(), parts[1].strip()
            os.environ[var_name] = value
            self._persist_env_var(var_name, value, _ctrl)
            masked = value[:4] + "…" + value[-4:] if len(value) > 8 else "****"
            await _ctrl._append_message("system", f"✓  {var_name} = {masked}  set and saved.")

        from citnega.apps.tui.slash_commands.workspace import WizardState
        ctrl._pending_wizard = WizardState(step_name="custom_var_input", on_input=on_input)

    # ── Local model setup ─────────────────────────────────────────────────────

    async def _step_local_model(self, ctrl: ChatController) -> None:
        options = [
            ("ollama",    "  Ollama  — set OLLAMA_BASE_URL  (default: localhost:11434)"),
            ("lmstudio",  "  LM Studio  — set LM_STUDIO_BASE_URL  (default: localhost:1234/v1)"),
            ("custom",    "  Custom server  — set CUSTOM_REMOTE_URL"),
        ]

        async def on_select(value: str, label: str) -> None:
            if value == "ollama":
                await self._ask_local_url(ctrl, "OLLAMA_BASE_URL", "Ollama", "http://localhost:11434")
            elif value == "lmstudio":
                await self._ask_local_url(ctrl, "LM_STUDIO_BASE_URL", "LM Studio", "http://localhost:1234/v1")
            elif value == "custom":
                await self._ask_local_url(ctrl, "CUSTOM_REMOTE_URL", "Custom server", "http://localhost:8000/v1")

        await ctrl._append_picker(
            title="Which local model server?",
            options=options,
            on_select=on_select,
        )

    async def _ask_local_url(
        self, ctrl: ChatController, env_var: str, server_name: str, default_url: str
    ) -> None:
        current = os.environ.get(env_var, default_url)
        await ctrl._append_message(
            "system",
            f"Enter the {server_name} base URL  [{env_var}]\n"
            f"Current: {current}\n\n"
            f"Press Ctrl+Enter with just the URL (e.g. http://localhost:11434)\n"
            f"or leave blank to keep the current value.",
        )

        async def on_input(text: str, _ctrl: ChatController) -> None:
            url = text.strip()
            if not url:
                await _ctrl._append_message("system", f"Kept existing URL: {current}")
                return
            os.environ[env_var] = url
            self._persist_env_var(env_var, url, _ctrl)
            await _ctrl._append_message(
                "system",
                f"✓  {env_var} = {url}\n"
                f"Active for this session. Restart citnega to reload the model gateway.",
            )

        from citnega.apps.tui.slash_commands.workspace import WizardState
        ctrl._pending_wizard = WizardState(step_name="local_url_input", on_input=on_input)

    # ── Default model picker ──────────────────────────────────────────────────

    async def _step_default_model(self, ctrl: ChatController) -> None:
        models = self._service.list_models() if self._service else []
        if not models:
            await ctrl._append_message("system", "No models available. Check models.yaml.")
            return

        session_id = getattr(ctrl, "_session_id", None)
        active = self._service.get_session_model(session_id) if session_id and self._service else ""

        options = [
            (
                m.model_id,
                f"{'* ' if m.model_id == active else '  '}"
                f"{m.model_id:<32}  {(m.description or '')[:40]}",
            )
            for m in models
        ]

        async def on_select(value: str, label: str) -> None:
            try:
                if session_id and self._service:
                    await self._service.set_session_model(session_id, value)
                app_home = self._get_app_home(ctrl)
                if app_home:
                    from citnega.packages.config.loaders import save_general_settings
                    save_general_settings("runtime", {"default_model_id": value}, app_home)
                ctrl._update_context_bar(model=value)
                await ctrl._append_message("system", f"✓ Default model set to: {value}")
            except Exception as exc:
                await ctrl._append_message("system", f"Failed to set model: {exc}")

        await ctrl._append_picker(
            title=f"Select default model  [active: {active or 'none'}]",
            options=options,
            on_select=on_select,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _persist_env_var(self, name: str, value: str, ctrl: ChatController) -> None:
        """Append / overwrite *name=value* in <app_home>/config/.env."""
        try:
            app_home = self._get_app_home(ctrl)
            if app_home is None:
                return
            env_file = app_home / "config" / ".env"
            env_file.parent.mkdir(parents=True, exist_ok=True)
            lines = env_file.read_text().splitlines() if env_file.exists() else []
            new_lines = [ln for ln in lines if not ln.startswith(f"{name}=")]
            new_lines.append(f"{name}={value}")
            env_file.write_text("\n".join(new_lines) + "\n")
        except Exception:
            pass

    def _save_openrouter_to_settings(self, api_key: str, ctrl: ChatController) -> None:
        try:
            app_home = self._get_app_home(ctrl)
            if app_home is None:
                return
            from citnega.packages.config.loaders import save_general_settings
            save_general_settings("openrouter", {"api_key": api_key, "enabled": True}, app_home)
        except Exception:
            pass

    def _get_app_home(self, ctrl: ChatController) -> Path | None:
        try:
            svc = self._service
            if svc is not None:
                ah = getattr(svc, "_app_home", None)
                if ah is not None:
                    return Path(ah)
            from citnega.packages.storage.path_resolver import PathResolver
            return PathResolver().app_home
        except Exception:
            return None
