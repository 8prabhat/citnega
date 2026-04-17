"""
Circuit breaker for model providers.

States:
  CLOSED    — normal operation; failures are counted
  OPEN      — provider is failing; all calls raise immediately
  HALF_OPEN — cooldown elapsed; one probe call is allowed through

Transitions:
  CLOSED  → OPEN       after N consecutive failures
  OPEN    → HALF_OPEN  after cooldown_seconds
  HALF_OPEN → CLOSED   on successful probe
  HALF_OPEN → OPEN     on failed probe (resets cooldown)
"""

from __future__ import annotations

import time
from enum import StrEnum
from threading import Lock

from citnega.packages.observability.logging_setup import model_gateway_logger
from citnega.packages.shared.errors import ProviderHTTPError

_THRESHOLD_DEFAULT = 5
_COOLDOWN_DEFAULT = 30.0


def _get_settings() -> tuple[int, float]:
    try:
        from citnega.packages.config.loaders import load_settings

        s = load_settings().runtime
        return s.circuit_breaker_threshold, s.circuit_breaker_cooldown_seconds
    except Exception:
        return _THRESHOLD_DEFAULT, _COOLDOWN_DEFAULT


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Thread-safe per-provider circuit breaker."""

    def __init__(
        self,
        provider_id: str,
        threshold: int | None = None,
        cooldown_seconds: float | None = None,
    ) -> None:
        self._provider_id = provider_id
        self._threshold = threshold
        self._cooldown = cooldown_seconds
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._lock = Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._evaluate_state()

    def record_success(self) -> None:
        with self._lock:
            if self._state in (CircuitState.HALF_OPEN, CircuitState.OPEN):
                model_gateway_logger.info(
                    "circuit_breaker_closed",
                    provider_id=self._provider_id,
                    prev_state=self._state,
                )
            self._state = CircuitState.CLOSED
            self._failure_count = 0

    def record_failure(self) -> None:
        threshold, _ = self._resolved_settings()
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._failure_count >= threshold:
                if self._state != CircuitState.OPEN:
                    model_gateway_logger.warning(
                        "circuit_breaker_opened",
                        provider_id=self._provider_id,
                        failure_count=self._failure_count,
                    )
                self._state = CircuitState.OPEN

    def allow_request(self) -> bool:
        """Return True if the request should be allowed through."""
        with self._lock:
            state = self._evaluate_state()
            if state == CircuitState.CLOSED:
                return True
            if state == CircuitState.HALF_OPEN:
                return True
            # OPEN
            return False

    def raise_if_open(self) -> None:
        if not self.allow_request():
            raise ProviderHTTPError(
                f"Circuit breaker OPEN for provider {self._provider_id!r} — "
                f"too many consecutive failures. Retry after cooldown."
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _evaluate_state(self) -> CircuitState:
        """Must be called with self._lock held."""
        if self._state == CircuitState.OPEN:
            _, cooldown = self._resolved_settings()
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= cooldown:
                self._state = CircuitState.HALF_OPEN
                model_gateway_logger.info(
                    "circuit_breaker_half_open",
                    provider_id=self._provider_id,
                    elapsed_s=round(elapsed, 1),
                )
        return self._state

    def _resolved_settings(self) -> tuple[int, float]:
        if self._threshold is not None and self._cooldown is not None:
            return self._threshold, self._cooldown
        default_threshold, default_cooldown = _get_settings()
        return (
            self._threshold if self._threshold is not None else default_threshold,
            self._cooldown if self._cooldown is not None else default_cooldown,
        )


class CircuitBreakerRegistry:
    """Global per-provider circuit breaker store."""

    def __init__(self) -> None:
        self._breakers: dict[str, CircuitBreaker] = {}
        self._lock = Lock()

    def get(self, provider_id: str) -> CircuitBreaker:
        with self._lock:
            if provider_id not in self._breakers:
                self._breakers[provider_id] = CircuitBreaker(provider_id)
            return self._breakers[provider_id]

    def reset(self, provider_id: str) -> None:
        with self._lock:
            if provider_id in self._breakers:
                self._breakers[provider_id].record_success()

    def all_states(self) -> dict[str, CircuitState]:
        with self._lock:
            return {pid: cb.state for pid, cb in self._breakers.items()}


# Module-level singleton — shared across all providers in this process
_registry = CircuitBreakerRegistry()


def get_circuit_breaker(provider_id: str) -> CircuitBreaker:
    return _registry.get(provider_id)
