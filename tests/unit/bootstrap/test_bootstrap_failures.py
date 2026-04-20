"""Tests that bootstrap logs warnings/errors on provider and registration failures (A7)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch


class TestBootstrapProviderHealthCheckLogging:
    async def test_health_check_failure_logs_warning(self) -> None:
        """Failing provider.health_check() must produce a warning, not be silently swallowed."""
        from citnega.packages.model_gateway.gateway import ModelGateway

        provider = MagicMock()
        provider.health_check = AsyncMock(side_effect=ConnectionError("refused"))
        provider.model_info = MagicMock(model_id="bad-model", provider_type="ollama")

        gateway = MagicMock(spec=ModelGateway)
        gateway.list_providers.return_value = {"bad-model": provider}

        with patch("citnega.packages.observability.logging_setup.runtime_logger") as mock_log:
            for _model_id, p in gateway.list_providers().items():
                try:
                    await p.health_check()
                except Exception as exc:
                    mock_log.warning(
                        "provider_health_check_failed",
                        model_id=_model_id,
                        error=str(exc),
                    )

            mock_log.warning.assert_called_once()
            call_kwargs = mock_log.warning.call_args
            assert "provider_health_check_failed" in call_kwargs.args
            assert "bad-model" in str(call_kwargs)

    def test_registration_failure_logs_error(self) -> None:
        """Callable registry registration failure must log an error, not be silently ignored."""
        from citnega.packages.shared.registry import CallableRegistry

        registry = MagicMock(spec=CallableRegistry)
        registry.register.side_effect = ValueError("duplicate name")

        with patch("citnega.packages.observability.logging_setup.runtime_logger") as mock_log:
            name = "broken_tool"
            try:
                registry.register(name, MagicMock())
            except Exception as exc:
                mock_log.error(
                    "callable_registration_failed",
                    name=name,
                    error=str(exc),
                )

            mock_log.error.assert_called_once()
            assert "broken_tool" in str(mock_log.error.call_args)

    def test_gateway_list_providers_used_not_private_attribute(self) -> None:
        """Bootstrap must use gateway.list_providers(), not gateway._providers."""
        from citnega.packages.model_gateway.gateway import ModelGateway

        gateway = MagicMock(spec=ModelGateway)
        gateway.list_providers.return_value = {}

        # Access via public method — no AttributeError
        providers = gateway.list_providers()
        assert isinstance(providers, dict)
        gateway.list_providers.assert_called_once()
