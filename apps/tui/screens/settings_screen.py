"""
SettingsScreen — F2 panel to view and edit all Citnega configuration values.

Layout::

    ┌─────────────────────────────────────────────────────┐
    │  Header: "Settings"                                  │
    ├─────────────────────────────────────────────────────┤
    │  TabbedContent                                       │
    │  ┌─ Workspace ─┬─ Model ─┬─ Conversation ─┬─ ...─┐ │
    │  │  [form]     │         │                 │      │ │
    │  └─────────────┴─────────┴─────────────────┴──────┘ │
    ├─────────────────────────────────────────────────────┤
    │  [Save & Close]   [Discard]                          │
    └─────────────────────────────────────────────────────┘

Keybindings
-----------
  ctrl+s   Save and close
  escape   Discard and close
  tab      Next field
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, ScrollableContainer, Vertical
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, Switch, TabbedContent, TabPane

if TYPE_CHECKING:
    from citnega.packages.config.settings import Settings


# ---------------------------------------------------------------------------
# Per-field metadata used to auto-build the form
# ---------------------------------------------------------------------------

_WORKSPACE_FIELDS: list[tuple[str, str, str]] = [
    ("workfolder_path", "Workspace folder path", "text"),
    ("auto_refresh",    "Auto-refresh workspace on startup", "bool"),
    ("strict_workspace_loading", "Strict workspace loading (fail on unknown modules)", "bool"),
]

_RUNTIME_FIELDS: list[tuple[str, str, str]] = [
    ("default_model_id",         "Default model ID", "text"),
    ("framework",                "Framework (adk / direct / crewai / langgraph)", "text"),
    ("max_tool_rounds",          "Max tool rounds per LLM turn", "int"),
    ("max_callable_depth",       "Max callable nesting depth", "int"),
    ("local_only",               "Local-only mode (reject remote calls)", "bool"),
    ("provider_max_retries",     "Provider max retries", "int"),
    ("streaming_max_retries",    "Streaming max retries", "int"),
    ("circuit_breaker_threshold","Circuit breaker threshold (failures)", "int"),
    ("circuit_breaker_cooldown_seconds", "Circuit breaker cooldown (seconds)", "float"),
    ("stream_timeout_seconds",   "Stream event timeout (seconds)", "float"),
]

_CONVERSATION_FIELDS: list[tuple[str, str, str]] = [
    ("auto_compact",               "Auto-compact conversation", "bool"),
    ("compact_threshold_messages", "Compact at N messages (0=off)", "int"),
    ("compact_threshold_tokens",   "Compact at N tokens (0=off)", "int"),
    ("compact_keep_recent",        "Keep N recent messages after compact", "int"),
    ("compact_use_model",          "Use model for compaction summary", "bool"),
    ("max_sessions_shown",         "Max sessions shown in picker", "int"),
    ("auto_name_from_first_message", "Auto-name session from first message", "bool"),
]

_SESSION_FIELDS: list[tuple[str, str, str]] = [
    ("max_context_tokens",        "Max context tokens", "int"),
    ("approval_timeout_seconds",  "Approval timeout (seconds)", "int"),
]

_LOGGING_FIELDS: list[tuple[str, str, str]] = [
    ("level",          "Log level (DEBUG / INFO / WARNING / ERROR)", "text"),
    ("format",         "Log format (jsonl / text)", "text"),
    ("retention_days", "Log retention (days)", "int"),
]

_POLICY_FIELDS: list[tuple[str, str, str]] = [
    ("template",                "Policy template (dev / team / locked_down)", "text"),
    ("enforce_network_deny",    "Deny all network calls", "bool"),
    ("enforce_workspace_bounds","Constrain file tools to workspace", "bool"),
    ("workspace_root",          "Workspace root override (empty = auto)", "text"),
    ("bypass_permissions",      "⚠ Bypass ALL permission checks (DANGEROUS — dev only)", "bool"),
]

_NEXTGEN_FIELDS: list[tuple[str, str, str]] = [
    ("planning_enabled",           "Nextgen planning stack", "bool"),
    ("execution_enabled",          "Nextgen execution stack", "bool"),
    ("workflows_enabled",          "Workflows support", "bool"),
    ("skills_enabled",             "Skills support", "bool"),
    ("parallel_execution_enabled", "Parallel tool execution", "bool"),
]

_OPENROUTER_FIELDS: list[tuple[str, str, str]] = [
    ("enabled",       "Enable OpenRouter provider", "bool"),
    ("api_key",       "API key (CITNEGA_OPENROUTER_API_KEY)", "text"),
    ("default_model", "Default model ID (e.g. openai/gpt-4o-mini)", "text"),
    ("site_url",      "Site URL (optional, for rankings)", "text"),
    ("app_name",      "App name (optional, for rankings)", "text"),
]

_DOCKER_FIELDS: list[tuple[str, str, str]] = [
    ("enabled",          "Enable Docker execution backend", "bool"),
    ("image",            "Docker image (e.g. python:3.12-slim)", "text"),
    ("workdir",          "Container workdir", "text"),
    ("memory_limit",     "Memory limit (e.g. 512m)", "text"),
    ("cpu_limit",        "CPU limit (e.g. 1.0)", "float"),
    ("network_disabled", "Disable container networking", "bool"),
    ("read_only",        "Read-only container filesystem", "bool"),
    ("pids_limit",       "PID limit", "int"),
]

_TELEGRAM_FIELDS: list[tuple[str, str, str]] = [
    ("enabled",         "Enable Telegram notifications", "bool"),
    ("bot_token",       "Bot token (CITNEGA_TELEGRAM_BOT_TOKEN)", "text"),
    ("default_chat_id", "Default chat ID", "text"),
]

_DISCORD_FIELDS: list[tuple[str, str, str]] = [
    ("enabled",            "Enable Discord notifications", "bool"),
    ("bot_token",          "Bot token (CITNEGA_DISCORD_BOT_TOKEN)", "text"),
    ("default_channel_id", "Default channel ID", "text"),
]


# ---------------------------------------------------------------------------
# Screen
# ---------------------------------------------------------------------------


class SettingsScreen(Screen):
    """F2 settings panel — view/edit all Citnega configuration."""

    BINDINGS = [
        Binding("ctrl+s", "save_close", "Save & Close", show=True),
        Binding("escape", "discard", "Discard", show=True),
    ]

    DEFAULT_CSS = """
    SettingsScreen {
        layout: vertical;
        background: $background;
    }

    #settings-tabs {
        height: 1fr;
    }

    .settings-pane {
        padding: 1 2;
        height: 1fr;
    }

    .field-row {
        layout: horizontal;
        height: auto;
        margin-bottom: 1;
        align: left middle;
    }

    .field-label {
        width: 40;
        color: $text;
        padding-right: 1;
    }

    .field-input {
        width: 1fr;
        min-width: 20;
    }

    .field-switch {
        width: auto;
    }

    #settings-buttons {
        height: 3;
        layout: horizontal;
        padding: 0 2;
        background: $panel;
        align: left middle;
    }

    #btn-save {
        margin-right: 1;
    }

    .section-hint {
        color: $text-muted;
        margin-bottom: 1;
        height: auto;
    }
    """

    class Saved(Message):
        """Settings were saved and screen is closing."""

    def __init__(self, service: Any = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = service
        self._settings: Settings | None = None
        self._widgets: dict[str, Input | Switch] = {}

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with TabbedContent(id="settings-tabs"):
            with TabPane("Workspace", id="tab-workspace"):
                yield self._build_pane("workspace", _WORKSPACE_FIELDS)
            with TabPane("Model & Runtime", id="tab-runtime"):
                yield self._build_pane("runtime", _RUNTIME_FIELDS)
            with TabPane("Conversation", id="tab-conversation"):
                yield self._build_pane("conversation", _CONVERSATION_FIELDS)
            with TabPane("Session", id="tab-session"):
                yield self._build_pane("session", _SESSION_FIELDS)
            with TabPane("Logging", id="tab-logging"):
                yield self._build_pane("logging", _LOGGING_FIELDS)
            with TabPane("Policy", id="tab-policy"):
                yield self._build_pane("policy", _POLICY_FIELDS)
            with TabPane("Advanced", id="tab-nextgen"):
                yield self._build_pane("nextgen", _NEXTGEN_FIELDS)
            with TabPane("Providers", id="tab-openrouter"):
                yield self._build_pane("openrouter", _OPENROUTER_FIELDS)
            with TabPane("Docker", id="tab-docker"):
                yield self._build_pane("docker", _DOCKER_FIELDS)
            with TabPane("Telegram", id="tab-telegram"):
                yield self._build_pane("telegram", _TELEGRAM_FIELDS)
            with TabPane("Discord", id="tab-discord"):
                yield self._build_pane("discord", _DISCORD_FIELDS)
        with Container(id="settings-buttons"):
            yield Button("Save & Close  [ctrl+s]", id="btn-save", variant="primary")
            yield Button("Discard  [esc]", id="btn-discard", variant="default")
        yield Footer()

    def _build_pane(self, section: str, fields: list[tuple[str, str, str]]) -> ScrollableContainer:
        pane = ScrollableContainer(classes="settings-pane")
        return pane

    def on_mount(self) -> None:
        try:
            from citnega.packages.config.loaders import load_settings
            self._settings = load_settings()
        except Exception:
            self._settings = None

        for section, fields in [
            ("workspace",    _WORKSPACE_FIELDS),
            ("runtime",      _RUNTIME_FIELDS),
            ("conversation", _CONVERSATION_FIELDS),
            ("session",      _SESSION_FIELDS),
            ("logging",      _LOGGING_FIELDS),
            ("policy",       _POLICY_FIELDS),
            ("nextgen",      _NEXTGEN_FIELDS),
            ("openrouter",   _OPENROUTER_FIELDS),
            ("docker",       _DOCKER_FIELDS),
            ("telegram",     _TELEGRAM_FIELDS),
            ("discord",      _DISCORD_FIELDS),
        ]:
            pane_id = f"tab-{section}"
            try:
                pane_container = self.query_one(f"#{pane_id} .settings-pane")
            except Exception:
                continue

            for field_id, label_text, field_type in fields:
                current_val = self._get_field_value(section, field_id)
                widget_id = f"field-{section}-{field_id}"

                if field_type == "bool":
                    w: Input | Switch = Switch(
                        value=bool(current_val),
                        id=widget_id,
                        classes="field-switch",
                    )
                else:
                    w = Input(
                        value=str(current_val) if current_val is not None else "",
                        id=widget_id,
                        classes="field-input",
                    )

                self._widgets[widget_id] = w
                lbl = Label(label_text, classes="field-label")
                row = Container(classes="field-row")
                # Mount row into pane, then children into row (deferred to after DOM is ready)
                async def _mount_row(pc=pane_container, r=row, l=lbl, widget=w) -> None:
                    await pc.mount(r)
                    await r.mount(l)
                    await r.mount(widget)
                self.app.call_later(_mount_row)

    def _get_field_value(self, section: str, field_id: str) -> Any:
        if self._settings is None:
            return ""
        try:
            sec = getattr(self._settings, section, None)
            return getattr(sec, field_id, "") if sec is not None else ""
        except Exception:
            return ""

    def _collect_values(self) -> dict[str, dict[str, Any]]:
        """Collect all edited values grouped by section."""
        result: dict[str, dict[str, Any]] = {}

        for section, fields in [
            ("workspace",    _WORKSPACE_FIELDS),
            ("runtime",      _RUNTIME_FIELDS),
            ("conversation", _CONVERSATION_FIELDS),
            ("session",      _SESSION_FIELDS),
            ("logging",      _LOGGING_FIELDS),
            ("policy",       _POLICY_FIELDS),
            ("nextgen",      _NEXTGEN_FIELDS),
            ("openrouter",   _OPENROUTER_FIELDS),
            ("docker",       _DOCKER_FIELDS),
            ("telegram",     _TELEGRAM_FIELDS),
            ("discord",      _DISCORD_FIELDS),
        ]:
            sec_data: dict[str, Any] = {}
            for field_id, _, field_type in fields:
                widget_id = f"field-{section}-{field_id}"
                w = self._widgets.get(widget_id)
                if w is None:
                    continue
                try:
                    if isinstance(w, Switch):
                        sec_data[field_id] = w.value
                    else:
                        raw = w.value.strip()
                        if field_type == "int":
                            sec_data[field_id] = int(raw) if raw else 0
                        elif field_type == "float":
                            sec_data[field_id] = float(raw) if raw else 0.0
                        else:
                            sec_data[field_id] = raw
                except (ValueError, TypeError):
                    pass  # skip invalid values silently
            if sec_data:
                result[section] = sec_data

        return result

    def action_save_close(self) -> None:
        self._save()
        self.dismiss(True)

    def action_discard(self) -> None:
        self.dismiss(False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-save":
            self.action_save_close()
        elif event.button.id == "btn-discard":
            self.action_discard()

    def _save(self) -> None:
        values = self._collect_values()

        app_home = self._get_app_home()
        if app_home is None:
            self.notify("Cannot save — app home not available", severity="error")
            return

        try:
            from citnega.packages.config.loaders import save_general_settings, save_workspace_settings

            # Workspace path gets its own dedicated file
            ws = values.pop("workspace", {})
            if "workfolder_path" in ws:
                path = ws.pop("workfolder_path")
                if path:
                    save_workspace_settings(path, app_home)
                    # Also ensure directory exists
                    p = Path(path).expanduser()
                    if not p.exists():
                        p.mkdir(parents=True, exist_ok=True)
                    # Update live service
                    svc = self._service
                    if svc is not None and hasattr(svc, "save_workspace_path"):
                        svc.save_workspace_path(path)
            # Other workspace keys go to settings.toml
            if ws:
                save_general_settings("workspace", ws, app_home)

            # All remaining sections → settings.toml
            for section, sec_values in values.items():
                save_general_settings(section, sec_values, app_home)

            self.post_message(self.Saved())
            self.notify("Settings saved. Some changes take effect after restart.", severity="information")
        except Exception as exc:
            self.notify(f"Save failed: {exc}", severity="error")

    def _get_app_home(self) -> Path | None:
        try:
            svc = self._service
            if svc is not None:
                ah = getattr(svc, "_app_home", None)
                if ah is not None:
                    return Path(ah)
            # Fallback: resolve via PathResolver
            from citnega.packages.storage.path_resolver import PathResolver
            return PathResolver().app_home
        except Exception:
            return None
