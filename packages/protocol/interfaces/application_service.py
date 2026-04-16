"""IApplicationService — facade interface for TUI and CLI."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    from citnega.packages.capabilities import CapabilityDescriptor
    from citnega.packages.planning import CompiledPlan
    from citnega.packages.protocol.callables.types import CallableMetadata
    from citnega.packages.protocol.events import CanonicalEvent
    from citnega.packages.protocol.models import (
        KBItem,
        KBSearchResult,
        ModelInfo,
        RunSummary,
        Session,
        SessionConfig,
        StateSnapshot,
    )


class IApplicationService(ABC):
    """
    Facade for all TUI / CLI interactions.

    The TUI and CLI depend on this interface only — they never import
    runtime internals, adapters, or infrastructure directly.
    """

    # ── Session management ─────────────────────────────────────────────────────

    @abstractmethod
    async def create_session(self, config: SessionConfig) -> Session: ...

    @abstractmethod
    async def get_session(self, session_id: str) -> Session | None: ...

    @abstractmethod
    async def list_sessions(self, limit: int = 50) -> list[Session]: ...

    @abstractmethod
    async def delete_session(self, session_id: str) -> None: ...

    # ── Run execution ──────────────────────────────────────────────────────────

    @abstractmethod
    async def run_turn(self, session_id: str, user_input: str) -> str:
        """Start a turn; returns the run_id."""
        ...

    @abstractmethod
    def stream_events(self, run_id: str) -> AsyncIterator[CanonicalEvent]:
        """Yield canonical events for a running or completed run."""
        ...

    @abstractmethod
    async def get_run(self, run_id: str) -> RunSummary | None: ...

    @abstractmethod
    async def list_runs(self, session_id: str, limit: int = 50) -> list[RunSummary]: ...

    # ── Run control ────────────────────────────────────────────────────────────

    @abstractmethod
    async def pause_run(self, run_id: str) -> None: ...

    @abstractmethod
    async def resume_run(self, run_id: str) -> None: ...

    @abstractmethod
    async def cancel_run(self, run_id: str) -> None: ...

    @abstractmethod
    async def respond_to_approval(
        self,
        approval_id: str,
        approved: bool,
        note: str | None = None,
    ) -> None: ...

    # ── Introspection ──────────────────────────────────────────────────────────

    @abstractmethod
    async def get_state_snapshot(self, session_id: str) -> StateSnapshot: ...

    # ── Knowledge base ─────────────────────────────────────────────────────────

    @abstractmethod
    async def search_kb(self, query: str, limit: int = 10) -> list[KBSearchResult]: ...

    @abstractmethod
    async def add_kb_item(self, item: KBItem) -> KBItem: ...

    @abstractmethod
    async def delete_kb_item(self, item_id: str) -> None: ...

    # ── Import / export ────────────────────────────────────────────────────────

    @abstractmethod
    async def export_session(
        self,
        session_id: str,
        fmt: str = "jsonl",
        output_path: Path | None = None,
    ) -> Path: ...

    @abstractmethod
    async def import_session(self, path: Path) -> Session: ...

    # ── Workspace / hot-reload ────────────────────────────────────────────────

    @abstractmethod
    def register_callable(self, callable_obj: object) -> None: ...

    @abstractmethod
    async def hot_reload_workfolder(self, workfolder: Path, loader: object) -> dict[str, Any]: ...

    @abstractmethod
    def save_workspace_path(self, path: str) -> None: ...

    # ── Registry queries ───────────────────────────────────────────────────────

    @abstractmethod
    def list_agents(self) -> list[CallableMetadata]: ...

    @abstractmethod
    def list_tools(self) -> list[CallableMetadata]: ...

    @abstractmethod
    def list_frameworks(self) -> list[str]: ...

    @abstractmethod
    def list_models(self) -> list[ModelInfo]: ...

    # ── Nextgen planning / strategy ────────────────────────────────────────────

    @abstractmethod
    def list_capabilities(self) -> list[CapabilityDescriptor]: ...

    @abstractmethod
    def list_skills(self) -> list[CapabilityDescriptor]: ...

    @abstractmethod
    def compile_mental_model(self, session_id: str, text: str) -> dict[str, Any]: ...

    @abstractmethod
    def set_session_skills(self, session_id: str, skill_names: list[str]) -> None: ...

    @abstractmethod
    def get_session_skills(self, session_id: str) -> list[str]: ...

    @abstractmethod
    def compile_plan(
        self,
        session_id: str,
        objective: str,
        *,
        capability_id: str | None = None,
        workflow_name: str | None = None,
        variables: dict[str, Any] | None = None,
    ) -> CompiledPlan: ...
