"""
DirectModelAdapter — IFrameworkAdapter that uses DirectModelRunner.

Creates one DirectModelRunner per session, backed by the YAML-driven
ProviderFactory.  No external framework dependency.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from citnega.packages.adapters.direct.runner import DirectModelRunner
from citnega.packages.model_gateway.yaml_config import ModelYAMLConfig, load_yaml_config
from citnega.packages.protocol.interfaces.adapter import (
    AdapterConfig,
    ICallableFactory,
    IFrameworkAdapter,
)
from citnega.packages.runtime.context.conversation_store import ConversationStore

if TYPE_CHECKING:
    from pathlib import Path

    from citnega.packages.protocol.callables.interfaces import IInvocable
    from citnega.packages.protocol.models.sessions import Session


class _NoOpCallableFactory(ICallableFactory):
    """Direct adapter does not wrap callables in a framework SDK."""

    def create_tool(self, callable: IInvocable) -> Any:
        return callable

    def create_specialist(self, callable: Any) -> Any:
        return callable

    def create_core_agent(self, callable: Any) -> Any:
        return callable

    def translate_event(self, framework_event: Any) -> Any:
        return None


class DirectModelAdapter(IFrameworkAdapter):
    """
    Lightweight adapter that bypasses ADK/LangGraph/CrewAI.

    Construction::

        adapter = DirectModelAdapter(
            sessions_dir=path_resolver.sessions_dir,
            yaml_config_path=None,   # None → bundled models.yaml
        )
    """

    def __init__(
        self,
        sessions_dir: Path,
        yaml_config_path: Path | None = None,
    ) -> None:
        self._sessions_dir = sessions_dir
        self._yaml_config: ModelYAMLConfig = load_yaml_config(yaml_config_path)
        self._factory = _NoOpCallableFactory()
        self._configured_default_model_id: str = ""
        # session_id → runner (for set_model routing)
        self._runners: dict[str, DirectModelRunner] = {}

    @property
    def framework_name(self) -> str:
        return "direct"

    async def initialize(self, config: AdapterConfig) -> None:
        # Keep the configured default model so runners can honour session/bootstrap defaults.
        self._configured_default_model_id = config.default_model_id

    async def create_runner(
        self,
        session: Session,
        callables: list[IInvocable],
        model_gateway: Any,
    ) -> DirectModelRunner:
        session_id = session.config.session_id
        session_dir = self._sessions_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        default_model_id = (
            session.config.default_model_id
            or self._configured_default_model_id
            or self._yaml_config.default_model
        )

        conv_store = ConversationStore(
            session_dir=session_dir,
            default_model_id=default_model_id,
        )
        await conv_store.load()
        # Remove any trailing user message that was saved before an aborted LLM call
        conv_store.drop_dangling_user_turn()

        from citnega.packages.config.loaders import load_settings

        _settings = load_settings()
        runner = DirectModelRunner(
            session=session,
            yaml_config=self._yaml_config,
            conversation_store=conv_store,
            callables=list(callables),
            model_gateway=model_gateway,
            max_tool_rounds=_settings.runtime.max_tool_rounds,
        )
        self._runners[session_id] = runner
        return runner

    async def set_session_model(self, session_id: str, model_id: str) -> None:
        """Switch the active model for an existing session."""
        runner = self._runners.get(session_id)
        if runner is not None:
            await runner.set_model(model_id)

    async def set_session_mode(self, session_id: str, mode_name: str) -> None:
        """Switch the session mode for an existing session."""
        runner = self._runners.get(session_id)
        if runner is not None:
            await runner.set_mode(mode_name)

    def get_runner(self, session_id: str) -> DirectModelRunner | None:
        return self._runners.get(session_id)

    async def shutdown(self) -> None:
        # Close shared HTTP client on all runners via the factory
        for runner in self._runners.values():
            await runner._factory.aclose()
        self._runners.clear()

    @property
    def callable_factory(self) -> _NoOpCallableFactory:
        return self._factory

    # ── Model listing (for /model command) ───────────────────────────────────

    def list_models_info(self) -> list[dict[str, Any]]:
        """Return model metadata list for UI display."""
        return [
            {
                "id": e.id,
                "model_name": e.model_name,
                "provider": e.provider,
                "priority": e.priority,
                "description": e.description,
            }
            for e in sorted(self._yaml_config.models, key=lambda m: -m.priority)
        ]
