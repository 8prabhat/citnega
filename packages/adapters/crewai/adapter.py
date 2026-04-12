"""
CrewAIFrameworkAdapter — IFrameworkAdapter for CrewAI.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from citnega.packages.adapters.base.base_adapter import BaseFrameworkAdapter
from citnega.packages.adapters.base.checkpoint_serializer import CheckpointSerializer
from citnega.packages.adapters.base.event_translator import EventTranslator
from citnega.packages.adapters.crewai.callable_factory import CrewAICallableFactory
from citnega.packages.adapters.crewai.runner import CrewAIRunner
from citnega.packages.observability.logging_setup import runtime_logger

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.interfaces import IInvocable
    from citnega.packages.protocol.interfaces.adapter import AdapterConfig, ICallableFactory
    from citnega.packages.protocol.models.sessions import Session
    from citnega.packages.storage.path_resolver import PathResolver


class CrewAIFrameworkAdapter(BaseFrameworkAdapter):
    """
    CrewAI adapter.

    Requires: ``uv add 'citnega[crewai]'``
    """

    def __init__(self, path_resolver: PathResolver) -> None:
        super().__init__()
        self._path_resolver = path_resolver
        self._translator = EventTranslator(framework_name="crewai")
        self._factory: CrewAICallableFactory | None = None

    @property
    def framework_name(self) -> str:
        return "crewai"

    async def _do_initialize(self, config: AdapterConfig) -> None:
        runtime_logger.info("crewai_adapter_init", model=config.default_model_id)

    async def create_runner(
        self,
        session: Session,
        callables: list[IInvocable],
        model_gateway: Any,
    ) -> CrewAIRunner:
        token = self._new_cancellation_token()
        checkpoint_dir = self._path_resolver.checkpoint_dir(session.config.session_id)
        serializer = CheckpointSerializer(checkpoint_dir, framework_name="crewai")
        model_id = (
            self._config.default_model_id if self._config else session.config.default_model_id
        )
        return CrewAIRunner(
            session=session,
            callables=callables,
            cancellation_token=token,
            checkpoint_serializer=serializer,
            event_translator=self._translator,
            model_id=model_id,
        )

    @property
    def callable_factory(self) -> ICallableFactory:
        if self._factory is None:
            self._factory = CrewAICallableFactory(
                event_translator=self._translator,
            )
        return self._factory
