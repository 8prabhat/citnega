"""ExecutionBackendFactory — creates the appropriate backend from AppSettings."""

from __future__ import annotations

from typing import TYPE_CHECKING

from citnega.packages.protocol.interfaces.execution_backend import IExecutionBackend

if TYPE_CHECKING:
    from citnega.packages.config.settings import Settings


class ExecutionBackendFactory:
    """Single factory for IExecutionBackend — follows same pattern as ProviderFactory."""

    @staticmethod
    def create(settings: Settings) -> IExecutionBackend:
        """Return DockerExecutionBackend if docker.enabled, else LocalExecutionBackend."""
        if settings.docker.enabled:
            from citnega.packages.execution.backends.docker import DockerExecutionBackend
            return DockerExecutionBackend(settings.docker)

        from citnega.packages.execution.backends.local import LocalExecutionBackend
        return LocalExecutionBackend()
