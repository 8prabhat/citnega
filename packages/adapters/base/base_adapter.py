"""
BaseFrameworkAdapter — partial implementation of IFrameworkAdapter.

Concrete adapters extend this and implement:
  - ``framework_name`` property
  - ``_do_initialize(config)``
  - ``create_runner(session, callables, model_gateway)``
  - ``callable_factory`` property

Shared behaviour (provided here):
  - ``initialize()`` guards against double-init.
  - ``shutdown()`` cancels all active runners via CancellationToken.
"""

from __future__ import annotations

from abc import abstractmethod
import contextlib

from citnega.packages.adapters.base.cancellation import CancellationToken
from citnega.packages.observability.logging_setup import runtime_logger
from citnega.packages.protocol.interfaces.adapter import AdapterConfig, IFrameworkAdapter


class BaseFrameworkAdapter(IFrameworkAdapter):
    """
    Shared lifecycle for all three framework adapters.

    Concrete subclasses must implement the abstract methods below.
    They must NOT import their framework SDK at module level — all
    framework imports belong inside ``_do_initialize()`` or inside
    the runner/factory classes in the adapter's own sub-package.
    """

    def __init__(self) -> None:
        self._config: AdapterConfig | None = None
        self._initialized: bool = False
        self._cancellation_tokens: list[CancellationToken] = []

    # ------------------------------------------------------------------
    # IFrameworkAdapter contract
    # ------------------------------------------------------------------

    async def initialize(self, config: AdapterConfig) -> None:
        if self._initialized:
            runtime_logger.warning(
                "adapter_already_initialized",
                framework=self.framework_name,
            )
            return
        self._config = config
        await self._do_initialize(config)
        self._initialized = True
        runtime_logger.info(
            "adapter_initialized",
            framework=self.framework_name,
            model=config.default_model_id,
        )

    async def shutdown(self) -> None:
        """Cancel all active runners and release resources."""
        runtime_logger.info("adapter_shutdown_start", framework=self.framework_name)
        for token in self._cancellation_tokens:
            token.cancel()
        self._cancellation_tokens.clear()
        await self._do_shutdown()
        runtime_logger.info("adapter_shutdown_complete", framework=self.framework_name)

    # ------------------------------------------------------------------
    # Internal hooks (override in subclasses)
    # ------------------------------------------------------------------

    @abstractmethod
    async def _do_initialize(self, config: AdapterConfig) -> None:
        """Framework-specific initialization logic."""
        ...

    async def _do_shutdown(self) -> None:
        """Override to release framework-specific resources. Default: no-op."""

    # ------------------------------------------------------------------
    # Helpers for subclasses
    # ------------------------------------------------------------------

    def _new_cancellation_token(self) -> CancellationToken:
        """Create and register a new CancellationToken for a runner."""
        token = CancellationToken()
        self._cancellation_tokens.append(token)
        return token

    def _release_token(self, token: CancellationToken) -> None:
        """Remove a completed runner's token from the live list."""
        with contextlib.suppress(ValueError):
            self._cancellation_tokens.remove(token)
