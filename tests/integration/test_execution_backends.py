"""Integration tests: execution backends (local and Docker)."""
from __future__ import annotations

import shutil

import pytest


@pytest.mark.asyncio
async def test_local_backend_echo() -> None:
    from citnega.packages.execution.backends.local import LocalExecutionBackend

    backend = LocalExecutionBackend()
    result = await backend.run("echo hello")
    assert result.exit_code == 0
    assert "hello" in result.stdout
    assert not result.timed_out


@pytest.mark.asyncio
async def test_local_backend_exit_code() -> None:
    from citnega.packages.execution.backends.local import LocalExecutionBackend

    backend = LocalExecutionBackend()
    result = await backend.run("exit 42", timeout=5.0)
    assert result.exit_code == 42


@pytest.mark.asyncio
async def test_local_backend_timeout() -> None:
    from citnega.packages.execution.backends.local import LocalExecutionBackend

    backend = LocalExecutionBackend()
    result = await backend.run("sleep 10", timeout=0.2)
    assert result.timed_out
    assert result.exit_code != 0


@pytest.mark.asyncio
async def test_local_backend_stderr_captured() -> None:
    from citnega.packages.execution.backends.local import LocalExecutionBackend

    backend = LocalExecutionBackend()
    result = await backend.run("echo err >&2", timeout=5.0)
    assert result.exit_code == 0
    assert "err" in result.stderr


def test_factory_returns_local_when_docker_disabled() -> None:
    from unittest.mock import MagicMock
    from citnega.packages.execution.backends.factory import ExecutionBackendFactory
    from citnega.packages.execution.backends.local import LocalExecutionBackend

    settings = MagicMock()
    settings.docker.enabled = False
    backend = ExecutionBackendFactory.create(settings)
    assert isinstance(backend, LocalExecutionBackend)


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker not available")
def test_factory_returns_docker_when_enabled() -> None:
    from unittest.mock import MagicMock
    from citnega.packages.execution.backends.docker import DockerExecutionBackend
    from citnega.packages.execution.backends.factory import ExecutionBackendFactory

    settings = MagicMock()
    settings.docker.enabled = True
    backend = ExecutionBackendFactory.create(settings)
    assert isinstance(backend, DockerExecutionBackend)
