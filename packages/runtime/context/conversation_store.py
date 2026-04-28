"""
ConversationStore — per-session JSON conversation history.

Stores:
  - messages: list of {"role": str, "content": str} dicts
  - active_model_id: the currently selected model for this session
  - mode_name: active session mode ("chat" | "plan" | "explore")

File location: <sessions_dir>/<session_id>/conversation.json

Thread-safety: asyncio.Lock per instance.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


class ConversationStore:
    """
    Manages conversation history for a single session on disk.

    Each session gets its own ``conversation.json`` file.  The store is
    the source of truth for both the message history and the active model.
    """

    # Base system prompt — no hardcoded tool names.
    # The runner appends a dynamic "## Available Tools" section built from
    # the actual registered callables, so this stays accurate regardless of
    # which tools are installed.
    _SYSTEM_PROMPT = (
        "You are Citnega, a helpful, concise, and thoughtful AI assistant. "
        "Respond clearly and accurately. Use fenced code blocks for code. "
        "Be direct and avoid unnecessary verbosity.\n\n"
        "## Memory\n\n"
        "You have two memory systems:\n"
        "  • **Session memory** — the conversation history above (what was said this session).\n"
        "  • **Persistent knowledge base** — use `read_kb` to recall facts, notes, and research "
        "saved across sessions; use `write_kb` to save important discoveries for future use.\n\n"
        "Always check session history before asking a clarifying question the user already answered.\n\n"
        "## Tool Use — mandatory rules\n\n"
        "Your training has a cutoff date — never rely on memory alone for anything "
        "that could have changed. Use your available tools proactively.\n\n"
        "**When to use tools (non-exhaustive):**\n"
        "  • Anything about current events, conflicts, geopolitics, elections, sanctions\n"
        "  • Economic events: markets, prices, company news, product launches\n"
        "  • Sports: live scores, results, standings, schedules, venues\n"
        "  • Technology: software versions, API changes, security advisories\n"
        "  • Any analytical question ('what is the logic/reasoning behind X') where X "
        "is an ongoing or recent situation — find the CURRENT state first, then analyse\n"
        "  • Anything that may have changed in the past 12 months\n"
        "  • File operations: read_file, write_file, edit_file, list_dir, search_files\n"
        "  • Shell commands and tests: run_shell\n"
        "  • Git operations: git_ops (status, diff, log, commit, etc.)\n\n"
        "**Rule of thumb:** When in doubt, use a tool first and answer second. "
        "Fresh facts + good reasoning beats stale memory every time.\n\n"
        "## Parallel Tool Calls — REQUIRED behaviour\n\n"
        "You MUST call multiple tools in a single response whenever the sub-tasks are independent. "
        "This is not optional and not 'simulated' — the runtime natively executes all tool calls "
        "you emit in one turn concurrently, then feeds you all results at once.\n\n"
        "NEVER say phrases like:\n"
        "  • 'I cannot run tools in parallel'\n"
        "  • 'I can simulate parallel execution'\n"
        "  • 'I cannot spawn separate threads'\n\n"
        "These statements are WRONG. You can and must emit multiple tool calls per response.\n\n"
        "**Concrete rule:** If a user asks you to search/list/read multiple things, "
        "call all the relevant tools immediately in this response without asking for "
        "clarification — make reasonable assumptions about scope and proceed. "
        "If a path is not specified, use the current working directory.\n\n"
        "The available tools and their purposes are listed below."
    )

    @staticmethod
    def build_tools_section(llm_tools: dict[str, Any]) -> str:
        """
        Build a '## Available Tools' section from the callable registry.

        Called by the runner at turn start so the prompt always reflects
        what is actually registered — no hardcoded names anywhere.
        """
        if not llm_tools:
            return ""
        lines = ["\n\n## Available Tools\n"]
        for name, tool in sorted(llm_tools.items()):
            desc = getattr(tool, "description", "").strip()
            # One sentence max in the prompt listing
            short = desc.split(".")[0] if "." in desc else desc
            lines.append(f"  • **`{name}`** — {short}.")
        return "\n".join(lines)

    def __init__(self, session_dir: Path, default_model_id: str = "") -> None:
        self._path = session_dir / "conversation.json"
        self._default_model_id = default_model_id
        self._lock = asyncio.Lock()
        self._data: dict[str, Any] = {}

    @property
    def session_dir(self) -> "Path":
        return self._path.parent

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def load(self) -> None:
        """Load from disk if it exists, otherwise initialise with defaults."""
        async with self._lock:
            if self._path.exists():
                try:
                    self._data = json.loads(self._path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    self._data = {}
            if not self._data:
                self._data = {
                    "messages": [],
                    "active_model_id": self._default_model_id,
                    "mode_name": "chat",
                    "plan_phase": "draft",
                    "active_skills": [],
                    "mental_model_spec": None,
                    "compiled_plan_metadata": {},
                }
            else:
                self._data.setdefault("plan_phase", "draft")
                self._data.setdefault("active_skills", [])
                self._data.setdefault("mental_model_spec", None)
                self._data.setdefault("compiled_plan_metadata", {})

    async def save(self) -> None:
        """Persist current state to disk."""
        async with self._lock:
            self._write_now()

    def _write_now(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── Messages ──────────────────────────────────────────────────────────────

    def get_messages(self) -> list[dict[str, str]]:
        """Return the stored message list (shallow copy)."""
        return list(self._data.get("messages", []))

    # ── Tool history ──────────────────────────────────────────────────────────

    def get_tool_history(self) -> list[dict[str, Any]]:
        """Return the stored tool call history (shallow copy)."""
        return list(self._data.get("tool_history", []))

    async def add_tool_call(
        self,
        name: str,
        input_summary: str,
        output_summary: str,
        success: bool,
        callable_type: str = "tool",
        msg_count: int | None = None,
    ) -> None:
        """Append a completed tool/agent call record and save.  Capped at 200 entries."""
        async with self._lock:
            history = self._data.setdefault("tool_history", [])
            # msg_count records how many messages existed when this tool was called.
            # Prefer the explicitly-supplied value (captured at ToolCallStarted time,
            # before the assistant message is added) to avoid a race where the
            # assistant message arrives before this write.
            stored_count = msg_count if msg_count is not None else len(self._data.get("messages", []))
            history.append(
                {
                    "name": name,
                    "input_summary": input_summary,
                    "output_summary": output_summary,
                    "success": success,
                    "callable_type": callable_type,
                    "msg_count": stored_count,
                }
            )
            if len(history) > 200:
                self._data["tool_history"] = history[-200:]
        await self.save()

    async def add_message(self, role: str, content: str) -> None:
        """Append a message and save."""
        async with self._lock:
            self._data.setdefault("messages", []).append({"role": role, "content": content})
        await self.save()

    async def clear_messages(self) -> None:
        """Clear message history and save."""
        async with self._lock:
            self._data["messages"] = []
        await self.save()

    def drop_dangling_user_turn(self) -> bool:
        """
        Remove a trailing user message with no assistant reply.

        Called after load() to handle sessions where the process was killed
        after saving the user message but before the assistant replied.

        Returns True if a dangling message was removed.
        """
        msgs = self._data.get("messages", [])
        content_msgs = [m for m in msgs if m.get("role") in ("user", "assistant")]
        if content_msgs and content_msgs[-1].get("role") == "user":
            # Trailing unanswered user message — remove it from stored list
            self._data["messages"] = [
                m for m in msgs
                if m is not content_msgs[-1]
            ]
            return True
        return False

    def build_messages_for_model(
        self,
        user_input: str,
        system_prompt: str | None = None,
        max_history: int = 40,
    ) -> list[dict[str, str]]:
        """
        Build the full message list to send to the model.

        Returns:
            [system_msg] + last *max_history* history msgs + current user msg
        """
        system = system_prompt or self._SYSTEM_PROMPT
        history = self.get_messages()[-max_history:]
        return [
            {"role": "system", "content": system},
            *history,
            {"role": "user", "content": user_input},
        ]

    # ── Stats ─────────────────────────────────────────────────────────────────

    @property
    def message_count(self) -> int:
        """Number of stored messages (user + assistant combined)."""
        return len(self._data.get("messages", []))

    @property
    def token_estimate(self) -> int:
        """Rough token estimate: total chars of all messages ÷ 4."""
        total_chars = sum(len(m.get("content", "")) for m in self._data.get("messages", []))
        return total_chars // 4

    @property
    def compaction_count(self) -> int:
        """How many times this conversation has been compacted."""
        return len(self._data.get("compaction_history", []))

    # ── Compaction ────────────────────────────────────────────────────────────

    async def compact(self, summary: str, keep_recent: int = 10) -> int:
        """
        Replace old messages with a compaction summary, keeping the most
        recent *keep_recent* messages verbatim.

        Records each compaction in ``compaction_history`` for audit purposes.

        Args:
            summary:     Text summary of the compacted messages.
            keep_recent: How many recent messages to preserve after the summary.

        Returns:
            Number of messages that were archived (compacted away).
        """
        async with self._lock:
            messages = self._data.get("messages", [])
            # Don't compact compaction markers — skip leading system messages
            content_msgs = [m for m in messages if m.get("role") != "system"]
            system_msgs = [m for m in messages if m.get("role") == "system"]

            cutoff = max(0, len(content_msgs) - keep_recent)
            archived = content_msgs[:cutoff]
            recent = content_msgs[cutoff:]

            if not archived:
                return 0

            import datetime as _dt

            compact_marker = {
                "role": "system",
                "content": (
                    f"[Compacted — {len(archived)} messages archived on "
                    f"{_dt.datetime.now(tz=_dt.UTC).strftime('%Y-%m-%d %H:%M UTC')}]\n\n"
                    f"{summary}"
                ),
            }

            # Preserve any existing system/compact markers, add new one, then recent
            self._data["messages"] = [*system_msgs, compact_marker, *recent]

            self._data.setdefault("compaction_history", []).append(
                {
                    "compacted_at": _dt.datetime.now(tz=_dt.UTC).isoformat(),
                    "messages_removed": len(archived),
                    "kept_recent": len(recent),
                    "summary_length": len(summary),
                }
            )

        await self.save()
        return len(archived)

    # ── Active model ──────────────────────────────────────────────────────────

    @property
    def active_model_id(self) -> str:
        return self._data.get("active_model_id") or self._default_model_id

    async def set_active_model(self, model_id: str) -> None:
        """Switch the active model for this session and save."""
        async with self._lock:
            self._data["active_model_id"] = model_id
        await self.save()

    # ── Session mode ──────────────────────────────────────────────────────────

    @property
    def mode_name(self) -> str:
        return self._data.get("mode_name") or "chat"

    async def set_mode(self, mode_name: str) -> None:
        """Switch the session mode and save."""
        async with self._lock:
            self._data["mode_name"] = mode_name
        await self.save()

    # ── Plan phase + nextgen session state ────────────────────────────────────

    @property
    def plan_phase(self) -> str:
        return str(self._data.get("plan_phase") or "draft")

    def set_plan_phase(self, phase: str) -> None:
        """Set the plan phase (``"draft"`` or ``"execute"``) and persist it."""
        self._data["plan_phase"] = phase
        self._write_now()

    @property
    def active_skills(self) -> list[str]:
        return list(self._data.get("active_skills", []))

    def set_active_skills(self, skill_names: list[str]) -> None:
        self._data["active_skills"] = list(skill_names)
        self._write_now()

    @property
    def mental_model_spec(self) -> dict[str, Any] | None:
        value = self._data.get("mental_model_spec")
        return value if isinstance(value, dict) else None

    def set_mental_model_spec(self, spec: dict[str, Any] | None) -> None:
        self._data["mental_model_spec"] = spec
        self._write_now()

    @property
    def compiled_plan_metadata(self) -> dict[str, Any]:
        value = self._data.get("compiled_plan_metadata")
        return dict(value) if isinstance(value, dict) else {}

    def set_compiled_plan_metadata(self, metadata: dict[str, Any] | None) -> None:
        self._data["compiled_plan_metadata"] = dict(metadata or {})
        self._write_now()

    # ── Thinking override ─────────────────────────────────────────────────────

    @property
    def thinking_enabled(self) -> bool | None:
        """
        Per-session thinking override.

        - ``None``  → use the model's default from models.yaml (``thinking:`` flag)
        - ``True``  → force thinking on regardless of model default
        - ``False`` → force thinking off regardless of model default
        """
        val = self._data.get("thinking_enabled")
        if val is None:
            return None
        return bool(val)

    async def set_thinking_enabled(self, value: bool | None) -> None:
        """
        Set the per-session thinking override and persist.

        Pass ``None`` to reset to auto (model YAML default).
        """
        async with self._lock:
            if value is None:
                self._data.pop("thinking_enabled", None)
            else:
                self._data["thinking_enabled"] = value
        await self.save()
