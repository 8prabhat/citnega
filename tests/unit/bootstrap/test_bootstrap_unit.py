"""
Unit tests for bootstrap helper functions.

Covers:
  - _select_adapter(): all supported frameworks + unknown key
  - _build_model_gateway(): local_only exit, healthy provider passes
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from citnega.packages.bootstrap.bootstrap import (
    EXIT_ADAPTER_ERROR,
    _build_model_gateway,
    _select_adapter,
)

# ── _select_adapter ────────────────────────────────────────────────────────────


def _path_resolver() -> MagicMock:
    pr = MagicMock()
    pr.sessions_dir = "/tmp/sessions"
    return pr


def test_select_adapter_direct_returns_adapter() -> None:
    pr = _path_resolver()
    with patch("citnega.packages.adapters.direct.adapter.DirectModelAdapter") as mock_cls:
        mock_cls.return_value = MagicMock()
        adapter = _select_adapter("direct", pr)
    assert adapter is not None


def test_select_adapter_case_insensitive() -> None:
    pr = _path_resolver()
    with patch("citnega.packages.adapters.direct.adapter.DirectModelAdapter") as mock_cls:
        mock_cls.return_value = MagicMock()
        adapter = _select_adapter("DIRECT", pr)
    assert adapter is not None


def test_select_adapter_unknown_framework_exits() -> None:
    pr = _path_resolver()
    with pytest.raises(SystemExit) as exc_info:
        _select_adapter("unknown_xyz", pr)
    assert exc_info.value.code == EXIT_ADAPTER_ERROR


def test_select_adapter_import_error_exits() -> None:
    pr = _path_resolver()
    with patch(
        "citnega.packages.adapters.direct.adapter.DirectModelAdapter",
        side_effect=ImportError("missing dep"),
    ):
        with pytest.raises(SystemExit) as exc_info:
            _select_adapter("direct", pr)
    assert exc_info.value.code == EXIT_ADAPTER_ERROR


def test_select_adapter_init_error_exits() -> None:
    pr = _path_resolver()
    with patch(
        "citnega.packages.adapters.direct.adapter.DirectModelAdapter",
        side_effect=RuntimeError("bad init"),
    ):
        with pytest.raises(SystemExit) as exc_info:
            _select_adapter("direct", pr)
    assert exc_info.value.code == EXIT_ADAPTER_ERROR


# ── _build_model_gateway ───────────────────────────────────────────────────────


def _fake_settings(*, local_only: bool = True) -> MagicMock:
    s = MagicMock()
    s.runtime.local_only = local_only
    return s


@pytest.mark.asyncio
async def test_build_gateway_no_providers_local_only_warns_and_continues() -> None:
    """No healthy provider in local_only mode now emits a warning instead of exiting."""
    from citnega.packages.model_gateway.gateway import ModelGateway

    settings = _fake_settings(local_only=True)
    emitter = MagicMock()

    with (
        patch("citnega.packages.model_gateway.registry.ModelRegistry.load"),
        patch("citnega.packages.model_gateway.registry.ModelRegistry.list_all", return_value=[]),
    ):
        gateway = await _build_model_gateway(settings, emitter)
    assert isinstance(gateway, ModelGateway)


@pytest.mark.asyncio
async def test_build_gateway_no_providers_not_local_only_returns_gateway() -> None:
    settings = _fake_settings(local_only=False)
    emitter = MagicMock()

    with (
        patch("citnega.packages.model_gateway.registry.ModelRegistry.load"),
        patch("citnega.packages.model_gateway.registry.ModelRegistry.list_all", return_value=[]),
    ):
        from citnega.packages.model_gateway.gateway import ModelGateway
        gateway = await _build_model_gateway(settings, emitter)
    assert isinstance(gateway, ModelGateway)


@pytest.mark.asyncio
async def test_build_gateway_registry_load_failure_is_non_fatal() -> None:
    """If model_registry.toml is missing, the gateway should still be returned (not local_only)."""
    settings = _fake_settings(local_only=False)
    emitter = MagicMock()

    with (
        patch(
            "citnega.packages.model_gateway.registry.ModelRegistry.load",
            side_effect=FileNotFoundError("no registry"),
        ),
        patch("citnega.packages.model_gateway.registry.ModelRegistry.list_all", return_value=[]),
    ):
        from citnega.packages.model_gateway.gateway import ModelGateway
        gateway = await _build_model_gateway(settings, emitter)
    assert isinstance(gateway, ModelGateway)
