"""Built-in slash commands for the TUI."""

from __future__ import annotations

from typing import Any

from citnega.packages.protocol.interfaces.slash_command import ISlashCommand


class HelpCommand(ISlashCommand):
    name = "help"
    help_text = "Show available slash commands."

    async def execute(self, args: list[str], app_context: Any) -> None:
        lines = ["Available commands:"]
        for cmd_name, cmd in app_context._slash_commands.items():
            lines.append(f"  /{cmd_name:<12} {cmd.help_text}")
        await app_context._append_message("system", "\n".join(lines))


class CancelCommand(ISlashCommand):
    name = "cancel"
    help_text = "Cancel the currently running turn."

    def __init__(self, service: Any) -> None:
        self._service = service

    async def execute(self, args: list[str], app_context: Any) -> None:
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

    async def execute(self, args: list[str], app_context: Any) -> None:
        screen = app_context._app.screen
        screen.action_clear_chat()


class ModelCommand(ISlashCommand):
    name = "model"
    help_text = "Show or switch the active model. Usage: /model [model_id]"

    def __init__(self, service: Any) -> None:
        self._service = service

    async def execute(self, args: list[str], app_context: Any) -> None:
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

    async def _switch_model(self, app_context: Any, session_id: str | None, model_id: str) -> None:
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
            try:
                from citnega.apps.tui.widgets.status_bar import StatusBar

                status = app_context._app.screen.query_one(StatusBar)
                status.set_model(model_id)
            except Exception:
                pass
            app_context._update_context_bar(model=model_id)
        except Exception as exc:
            await app_context._append_message("system", f"Model switch failed: {exc}")


class ModeCommand(ISlashCommand):
    name = "mode"
    help_text = (
        "Show or switch session mode. Usage: "
        "/mode [chat|plan|explore|research|code|review|operate]"
    )

    def __init__(self, service: Any) -> None:
        self._service = service

    async def execute(self, args: list[str], app_context: Any) -> None:
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

    async def _switch_mode(self, app_context: Any, session_id: str | None, requested: str) -> None:
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
            try:
                from citnega.apps.tui.widgets.status_bar import StatusBar

                status = app_context._app.screen.query_one(StatusBar)
                status.set_mode(mode_obj.display_label)
            except Exception:
                pass
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

    def __init__(self, service: Any) -> None:
        self._service = service

    async def execute(self, args: list[str], app_context: Any) -> None:
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

    def __init__(self, service: Any) -> None:
        self._service = service

    async def execute(self, args: list[str], app_context: Any) -> None:
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

    def __init__(self, service: Any) -> None:
        self._service = service

    async def execute(self, args: list[str], app_context: Any) -> None:
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

    def __init__(self, service: Any) -> None:
        self._service = service

    async def execute(self, args: list[str], app_context: Any) -> None:
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

            # Update status bar
            try:
                from citnega.apps.tui.widgets.status_bar import StatusBar

                status = app_context._app.screen.query_one(StatusBar)
                status.session_id = session.config.session_id
            except Exception:
                pass

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

    def __init__(self, service: Any) -> None:
        self._service = service

    async def execute(self, args: list[str], app_context: Any) -> None:
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

    async def _switch_session(self, app_context: Any, session) -> None:
        from textual.containers import VerticalScroll
        from textual.widgets import Label as _Label

        sid = session.config.session_id
        app_context._session_id = sid
        app_context._app._session_id = sid

        # ── Hard-clear both panels with await so removal is complete before
        #    we start mounting history.  Using action_clear_chat() without
        #    await leaves old nodes registered when _append_message runs.
        screen = app_context._app.screen
        try:
            scroll = screen.query_one("#chat-scroll", VerticalScroll)
            await scroll.remove_children()
        except Exception:
            scroll = None

        try:
            tools_panel = screen.query_one("#tools-panel", VerticalScroll)
            await tools_panel.remove_children()
        except Exception:
            tools_panel = None

        try:
            from citnega.apps.tui.widgets.status_bar import StatusBar
            screen.query_one(StatusBar).session_id = sid
        except Exception:
            pass

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

        # ── Restore tool call / agent call history ────────────────────────
        tool_history = []
        if tools_panel is not None:
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
                    await tools_panel.mount(block)
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

        # ── Restore placeholders if panels are still empty ────────────────
        if scroll is not None and messages_loaded == 0 and not scroll.query("#empty-hint"):
            try:
                from citnega.apps.tui.widgets.welcome_banner import WelcomeBanner
                await scroll.mount(WelcomeBanner(id="empty-hint"))
            except Exception:
                pass

        if tools_panel is not None and not tool_history and not tools_panel.query("#tools-empty"):
            try:
                await tools_panel.mount(_Label("No active tools", id="tools-empty"))
            except Exception:
                pass

        await app_context._append_message(
            "system", f"Switched to: {session.config.name}  [{sid[:8]}…]"
        )


class CompactCommand(ISlashCommand):
    name = "compact"
    help_text = "Compact the conversation history. Usage: /compact [keep_recent_count]"

    def __init__(self, service: Any) -> None:
        self._service = service

    async def execute(self, args: list[str], app_context: Any) -> None:
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

    def __init__(self, service: Any) -> None:
        self._service = service

    async def execute(self, args: list[str], app_context: Any) -> None:
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
            # Update status bar if available
            try:
                from citnega.apps.tui.widgets.status_bar import StatusBar
                status = app_context._app.screen.query_one(StatusBar)
                status.session_name = new_name
            except Exception:
                pass
            await app_context._append_message(
                "system", f"Session renamed to: {new_name!r}"
            )
        except Exception as exc:
            await app_context._append_message("system", f"Rename failed: {exc}")


class DeleteSessionCommand(ISlashCommand):
    name = "delete"
    help_text = "Delete the current session and start a new one. Usage: /delete [--yes]"

    def __init__(self, service: Any) -> None:
        self._service = service

    async def execute(self, args: list[str], app_context: Any) -> None:
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

    def __init__(self, service: Any) -> None:
        self._service = service

    async def execute(self, args: list[str], app_context: Any) -> None:
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
