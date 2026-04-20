"""
Unit tests for CircuitBreaker (Phase 11, Step 11.4).

Covers all state transitions:
  CLOSED → OPEN (threshold consecutive failures)
  OPEN → HALF_OPEN (after cooldown)
  HALF_OPEN → CLOSED (probe success)
  HALF_OPEN → OPEN (probe failure)
  OPEN blocks requests (raise_if_open raises)
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from citnega.packages.model_gateway.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerRegistry,
    CircuitState,
)
from citnega.packages.shared.errors import ProviderHTTPError


def _breaker(threshold: int = 3, cooldown: float = 1.0) -> CircuitBreaker:
    return CircuitBreaker("test-provider", threshold=threshold, cooldown_seconds=cooldown)


# ── CLOSED state ───────────────────────────────────────────────────────────────


def test_initial_state_is_closed() -> None:
    cb = _breaker()
    assert cb.state == CircuitState.CLOSED


def test_allow_request_when_closed() -> None:
    cb = _breaker()
    assert cb.allow_request() is True


def test_failures_below_threshold_stay_closed() -> None:
    cb = _breaker(threshold=3)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED


def test_success_resets_failure_count() -> None:
    cb = _breaker(threshold=3)
    cb.record_failure()
    cb.record_failure()
    cb.record_success()
    cb.record_failure()
    # Only 1 failure after reset — still closed
    assert cb.state == CircuitState.CLOSED


# ── CLOSED → OPEN ──────────────────────────────────────────────────────────────


def test_threshold_failures_open_circuit() -> None:
    cb = _breaker(threshold=3)
    for _ in range(3):
        cb.record_failure()
    assert cb.state == CircuitState.OPEN


def test_open_circuit_blocks_requests() -> None:
    cb = _breaker(threshold=2)
    cb.record_failure()
    cb.record_failure()
    assert cb.allow_request() is False


def test_raise_if_open_raises_provider_error() -> None:
    cb = _breaker(threshold=1)
    cb.record_failure()
    with pytest.raises(ProviderHTTPError, match="Circuit breaker OPEN"):
        cb.raise_if_open()


def test_raise_if_open_does_not_raise_when_closed() -> None:
    cb = _breaker()
    cb.raise_if_open()  # should not raise


# ── OPEN → HALF_OPEN ───────────────────────────────────────────────────────────


def test_open_transitions_to_half_open_after_cooldown() -> None:
    cb = _breaker(threshold=1, cooldown=0.05)
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    time.sleep(0.06)
    assert cb.state == CircuitState.HALF_OPEN


def test_open_stays_open_before_cooldown() -> None:
    cb = _breaker(threshold=1, cooldown=10.0)
    cb.record_failure()
    assert cb.state == CircuitState.OPEN


def test_half_open_allows_request() -> None:
    cb = _breaker(threshold=1, cooldown=0.05)
    cb.record_failure()
    time.sleep(0.06)
    assert cb.allow_request() is True


# ── HALF_OPEN → CLOSED ────────────────────────────────────────────────────────


def test_half_open_success_closes_circuit() -> None:
    cb = _breaker(threshold=1, cooldown=0.05)
    cb.record_failure()
    time.sleep(0.06)
    assert cb.state == CircuitState.HALF_OPEN
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb.allow_request() is True


# ── HALF_OPEN → OPEN ──────────────────────────────────────────────────────────


def test_half_open_failure_reopens_circuit() -> None:
    cb = _breaker(threshold=1, cooldown=0.05)
    cb.record_failure()
    time.sleep(0.06)
    assert cb.state == CircuitState.HALF_OPEN
    cb.record_failure()
    assert cb.state == CircuitState.OPEN


# ── Registry ───────────────────────────────────────────────────────────────────


def test_registry_returns_same_breaker_for_same_provider() -> None:
    reg = CircuitBreakerRegistry()
    b1 = reg.get("provider-a")
    b2 = reg.get("provider-a")
    assert b1 is b2


def test_registry_returns_different_breakers_per_provider() -> None:
    reg = CircuitBreakerRegistry()
    b1 = reg.get("provider-a")
    b2 = reg.get("provider-b")
    assert b1 is not b2


def test_registry_reset_closes_breaker() -> None:
    reg = CircuitBreakerRegistry()
    cb = reg.get("provider-x")
    with patch(
        "citnega.packages.model_gateway.circuit_breaker._get_settings",
        return_value=(3, 30.0),
    ):
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
    assert cb.state == CircuitState.OPEN
    reg.reset("provider-x")
    assert cb.state == CircuitState.CLOSED


def test_registry_all_states() -> None:
    reg = CircuitBreakerRegistry()
    with patch(
        "citnega.packages.model_gateway.circuit_breaker._get_settings",
        return_value=(3, 30.0),
    ):
        reg.get("p1").record_failure()
        reg.get("p1").record_failure()
        reg.get("p1").record_failure()
    reg.get("p2")  # closed
    states = reg.all_states()
    assert states["p1"] == CircuitState.OPEN
    assert states["p2"] == CircuitState.CLOSED


# ── Integration with BaseProvider._with_retry ─────────────────────────────────


@pytest.mark.asyncio
async def test_base_provider_skips_retry_when_circuit_open() -> None:
    """If circuit is OPEN, _with_retry raises immediately without calling _do_generate."""
    from unittest.mock import MagicMock

    from citnega.packages.model_gateway.providers.base_provider import BaseProvider

    class _Provider(BaseProvider):
        async def _do_generate(self, request):
            raise AssertionError("should not be called")

        async def _do_stream_generate(self, request):
            raise AssertionError("should not be called")
            yield

        async def _do_health_check(self):
            return "ok"

    model_info = MagicMock()
    model_info.model_id = "cb-test-model"
    provider = _Provider(model_info=model_info, http_client=MagicMock())

    # Force circuit open
    cb = CircuitBreaker("cb-test-model", threshold=1)
    cb.record_failure()
    assert cb.state == CircuitState.OPEN

    with patch(
        "citnega.packages.model_gateway.circuit_breaker._registry.get",
        return_value=cb,
    ):
        with pytest.raises(ProviderHTTPError, match="Circuit breaker OPEN"):
            await provider.generate(MagicMock())
