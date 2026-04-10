"""Built-in slash commands for the TUI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from citnega.packages.protocol.interfaces.slash_command import ISlashCommand

if TYPE_CHECKING:
    pass


class HelpCommand(ISlashCommand):
    name      = "help"
    help_text = "Show available slash commands."

    async def execute(self, args: list[str], app_context: Any) -> None:
        lines = ["Available commands:"]
        for cmd_name, cmd in app_context._slash_commands.items():
            lines.append(f"  /{cmd_name:<12} {cmd.help_text}")
        await app_context._append_message("system", "\n".join(lines))


class CancelCommand(ISlashCommand):
    name      = "cancel"
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
    name      = "clear"
    help_text = "Clear the chat window."

    async def execute(self, args: list[str], app_context: Any) -> None:
        screen = app_context._app.screen
        screen.action_clear_chat()


class ModelCommand(ISlashCommand):
    name      = "model"
    help_text = "Show or switch the active model. Usage: /model [model_id]"

    def __init__(self, service: Any) -> None:
        self._service = service

    async def execute(self, args: list[str], app_context: Any) -> None:
        models = self._service.list_models()
        if not args:
            # Show list of available models
            if not models:
                await app_context._append_message(
                    "system",
                    "No models available. Check packages/model_gateway/models.yaml."
                )
                return

            session_id = getattr(app_context, "_session_id", None)
            active_id  = self._service.get_session_model(session_id) if session_id else None

            lines = ["Available models (sorted by priority):"]
            for m in models:
                marker = " *" if m.model_id == active_id else "  "
                lines.append(f"{marker} {m.model_id:<30} (priority={m.priority})")
            if active_id:
                lines.append(f"\nActive: {active_id}")
            lines.append("\nUsage: /model <model_id>")
            await app_context._append_message("system", "\n".join(lines))
        else:
            # Switch model
            requested = args[0]
            model_ids = [m.model_id for m in models]
            if requested not in model_ids:
                await app_context._append_message(
                    "system",
                    f"Unknown model '{requested}'.\nAvailable: {', '.join(model_ids)}"
                )
                return

            session_id = getattr(app_context, "_session_id", None)
            if not session_id:
                await app_context._append_message("system", "No active session.")
                return

            try:
                await self._service.set_session_model(session_id, requested)
                await app_context._append_message(
                    "system", f"Switched to model: {requested}"
                )
                # Refresh status bar
                try:
                    from citnega.apps.tui.widgets.status_bar import StatusBar  # noqa: PLC0415
                    status = app_context._app.screen.query_one(StatusBar)
                    status.set_model(requested)
                except Exception:
                    pass
            except Exception as exc:
                await app_context._append_message("system", f"Model switch failed: {exc}")


class ModeCommand(ISlashCommand):
    name      = "mode"
    help_text = "Show or switch session mode. Usage: /mode [chat|plan|explore]"

    def __init__(self, service: Any) -> None:
        self._service = service

    async def execute(self, args: list[str], app_context: Any) -> None:
        from citnega.packages.runtime.session_modes import all_modes  # noqa: PLC0415

        session_id = getattr(app_context, "_session_id", None)

        if not args:
            # Show available modes and current selection
            current = self._service.get_session_mode(session_id) if session_id else "chat"
            lines = ["Available modes:"]
            for m in all_modes():
                marker = " *" if m.name == current else "  "
                lines.append(f"{marker} {m.name:<10} — {m.description}")
            lines.append(f"\nActive: {current}")
            lines.append("\nUsage: /mode <mode_name>")
            await app_context._append_message("system", "\n".join(lines))
            return

        requested = args[0].lower()
        valid     = [m.name for m in all_modes()]
        if requested not in valid:
            await app_context._append_message(
                "system",
                f"Unknown mode '{requested}'. Available: {', '.join(valid)}"
            )
            return

        if not session_id:
            await app_context._append_message("system", "No active session.")
            return

        try:
            await self._service.set_session_mode(session_id, requested)
            # Reflect in status bar
            from citnega.packages.runtime.session_modes import get_mode  # noqa: PLC0415
            mode_obj = get_mode(requested)
            try:
                from citnega.apps.tui.widgets.status_bar import StatusBar  # noqa: PLC0415
                status = app_context._app.screen.query_one(StatusBar)
                status.set_mode(mode_obj.display_label)
            except Exception:
                pass
            label = mode_obj.display_label or "[CHAT]"
            await app_context._append_message(
                "system",
                f"{label} Mode active — {mode_obj.description}"
            )
        except Exception as exc:
            await app_context._append_message("system", f"Mode switch failed: {exc}")


class ThinkCommand(ISlashCommand):
    name      = "think"
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
                "system",
                f"Thinking: {status}\n\nUsage: /think on | /think off | /think auto"
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
                "system",
                f"Unknown option '{arg}'. Use: /think on | /think off | /think auto"
            )
            return

        try:
            await self._service.set_session_thinking(session_id, value)
            label = {True: "on", False: "off", None: "auto"}[value]
            await app_context._append_message(
                "system", f"Thinking set to: {label}"
            )
        except Exception as exc:
            await app_context._append_message("system", f"Failed: {exc}")


class ApproveCommand(ISlashCommand):
    name      = "approve"
    help_text = "Approve a pending tool call. Usage: /approve <approval_id> [--deny]"

    def __init__(self, service: Any) -> None:
        self._service = service

    async def execute(self, args: list[str], app_context: Any) -> None:
        if not args:
            await app_context._append_message(
                "system", "Usage: /approve <approval_id> [--deny]"
            )
            return
        approval_id = args[0]
        deny = "--deny" in args
        try:
            await self._service.respond_to_approval(approval_id, approved=not deny)
            verb = "denied" if deny else "approved"
            await app_context._append_message(
                "system", f"Approval {approval_id[:8]} {verb}."
            )
        except Exception as exc:
            await app_context._append_message("system", f"Approval error: {exc}")


class AgentCommand(ISlashCommand):
    name      = "agent"
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
            await app_context._append_message(
                "system", "Usage: /agent [agents|tools]"
            )
            return

        await app_context._append_message("system", "\n".join(lines))


class NewSessionCommand(ISlashCommand):
    name      = "new"
    help_text = "Clear the current chat and start a fresh session."

    def __init__(self, service: Any) -> None:
        self._service = service

    async def execute(self, args: list[str], app_context: Any) -> None:
        import uuid  # noqa: PLC0415
        from citnega.packages.protocol.models.sessions import SessionConfig  # noqa: PLC0415

        try:
            cfg = SessionConfig(
                session_id=str(uuid.uuid4()),
                name="new-session",
                framework="stub",
                default_model_id="",
            )
            session = await self._service.create_session(cfg)
            # Update context
            app_context._session_id = session.config.session_id
            if hasattr(app_context._app, "_session_id"):
                app_context._app._session_id = session.config.session_id

            # Clear the chat window
            screen = app_context._app.screen
            screen.action_clear_chat()

            # Update status bar
            try:
                from citnega.apps.tui.widgets.status_bar import StatusBar  # noqa: PLC0415
                status = app_context._app.screen.query_one(StatusBar)
                status.session_id = session.config.session_id
            except Exception:
                pass

            await app_context._append_message(
                "system",
                f"New session started: {session.config.session_id[:8]}…\n"
                "Previous session is still available via /sessions."
            )
        except Exception as exc:
            await app_context._append_message("system", f"Failed to create session: {exc}")


class SessionsCommand(ISlashCommand):
    name      = "sessions"
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
            # Switch to specified session
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
            sid = match.config.session_id
            app_context._session_id = sid
            if hasattr(app_context._app, "_session_id"):
                app_context._app._session_id = sid
            screen = app_context._app.screen
            screen.action_clear_chat()
            try:
                from citnega.apps.tui.widgets.status_bar import StatusBar  # noqa: PLC0415
                status = app_context._app.screen.query_one(StatusBar)
                status.session_id = sid
            except Exception:
                pass
            await app_context._append_message(
                "system",
                f"Switched to session {sid[:8]}… ({match.config.name})"
            )
            return

        # List sessions
        if not sessions:
            await app_context._append_message("system", "No sessions found.")
            return

        current = getattr(app_context, "_session_id", None)
        lines = [f"Sessions ({len(sessions)}):"]
        for s in sessions:
            marker = " *" if s.config.session_id == current else "  "
            from citnega.apps.tui.screens.session_picker import _format_age  # noqa: PLC0415
            age = _format_age(s.last_active_at) if s.last_active_at else "?"
            lines.append(
                f"{marker} {s.config.session_id[:8]:<10} {s.config.name:<25} {age}"
            )
        lines.append("\nUsage: /sessions <id_prefix>  to switch")
        await app_context._append_message("system", "\n".join(lines))


class CompactCommand(ISlashCommand):
    name      = "compact"
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
                    f"(~{stats['token_estimate']} tokens)."
                )
        except Exception as exc:
            await app_context._append_message("system", f"Compact failed: {exc}")
