"""
ADKFrameworkAdapter — IFrameworkAdapter implementation for Google ADK.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from citnega.packages.adapters.adk.callable_factory import ADKCallableFactory
from citnega.packages.adapters.adk.runner import ADKRunner
from citnega.packages.adapters.base.base_adapter import BaseFrameworkAdapter
from citnega.packages.adapters.base.checkpoint_serializer import CheckpointSerializer
from citnega.packages.adapters.base.event_translator import EventTranslator
from citnega.packages.observability.logging_setup import runtime_logger

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.interfaces import IInvocable
    from citnega.packages.protocol.interfaces.adapter import AdapterConfig, ICallableFactory
    from citnega.packages.protocol.models.sessions import Session
    from citnega.packages.storage.path_resolver import PathResolver


class ADKFrameworkAdapter(BaseFrameworkAdapter):
    """
    Google ADK adapter.

    Requires: ``uv add 'citnega[adk]'``  (google-adk package).
    The google.adk SDK is never imported at module level — only inside
    ADKRunner._get_adk_runner() when the first turn runs.
    """

    def __init__(self, path_resolver: PathResolver) -> None:
        super().__init__()
        self._path_resolver = path_resolver
        self._translator = EventTranslator(framework_name="adk")
        self._factory: ADKCallableFactory | None = None

    @property
    def framework_name(self) -> str:
        return "adk"

    async def _do_initialize(self, config: AdapterConfig) -> None:
        # No ADK SDK imports here — deferred to runner
        runtime_logger.info(
            "adk_adapter_init",
            model=config.default_model_id,
        )

    async def create_runner(
        self,
        session: Session,
        callables: list[IInvocable],
        model_gateway: Any,
    ) -> ADKRunner:
        token = self._new_cancellation_token()
        checkpoint_dir = self._path_resolver.checkpoint_dir(session.config.session_id)
        serializer = CheckpointSerializer(checkpoint_dir, framework_name="adk")
        model_id = (
            self._config.default_model_id if self._config else session.config.default_model_id
        )
        runner = ADKRunner(
            session=session,
            callables=callables,
            cancellation_token=token,
            checkpoint_serializer=serializer,
            event_translator=self._translator,
            model_id=model_id,
        )
        runtime_logger.debug(
            "adk_runner_created",
            session_id=session.config.session_id,
            callable_count=len(callables),
        )
        return runner

    @property
    def callable_factory(self) -> ICallableFactory:
        if self._factory is None:
            from citnega.packages.protocol.models.sessions import SessionConfig

            # Factory is session-agnostic at this level; session_config injected per-runner
            self._factory = ADKCallableFactory(
                event_translator=self._translator,
                session_config=SessionConfig(
                    session_id="__factory__",
                    name="factory",
                    framework="adk",
                    default_model_id=self._config.default_model_id if self._config else "",
                ),
            )
        return self._factory
