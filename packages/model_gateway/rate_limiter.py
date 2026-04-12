"""
TokenBucketRateLimiter — per (provider, model) RPM + TPM enforcement.

Two independent token buckets per model:
  - RPM bucket: 1 token = 1 request.
  - TPM bucket: 1 token = 1 prompt/completion token.

On bucket exhaustion, ``acquire()`` raises RateLimitExceededError with
the estimated retry-after seconds.  Callers should catch this and emit
a RateLimitEvent before re-queuing the request.

Design notes:
  - Buckets refill continuously (fractional tokens) using monotonic time.
  - Thread-safe via asyncio.Lock (single event loop assumed).
  - One RateLimiter instance per ModelGateway; keys are (provider, model_id).
"""

from __future__ import annotations

import asyncio
import time

from citnega.packages.observability.logging_setup import model_gateway_logger
from citnega.packages.shared.errors import RateLimitExceededError


class _TokenBucket:
    """Continuous-refill token bucket."""

    def __init__(self, capacity: float, refill_rate: float) -> None:
        """
        Args:
            capacity:    Maximum tokens (burst size).
            refill_rate: Tokens added per second.
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self._tokens = float(capacity)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0) -> float:
        """
        Attempt to consume *tokens* from the bucket.

        Returns 0.0 on success.
        Returns the estimated seconds-to-wait if insufficient tokens.
        """
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(
                self.capacity,
                self._tokens + elapsed * self.refill_rate,
            )
            self._last_refill = now

            if self._tokens >= tokens:
                self._tokens -= tokens
                return 0.0
            deficit = tokens - self._tokens
            return deficit / self.refill_rate

    def available(self) -> float:
        """Approximate available tokens (without lock, for monitoring)."""
        elapsed = time.monotonic() - self._last_refill
        return min(self.capacity, self._tokens + elapsed * self.refill_rate)


class TokenBucketRateLimiter:
    """
    Rate limiter managing RPM and TPM buckets per (provider, model_id).

    Usage::

        limiter = TokenBucketRateLimiter()
        limiter.set_limits("ollama", "gemma3-12b-local", rpm=60, tpm=100_000)
        await limiter.acquire("ollama", "gemma3-12b-local", prompt_tokens=512)
    """

    def __init__(self) -> None:
        self._rpm_buckets: dict[tuple[str, str], _TokenBucket] = {}
        self._tpm_buckets: dict[tuple[str, str], _TokenBucket] = {}

    def set_limits(
        self,
        provider: str,
        model_id: str,
        *,
        rpm: int = 60,
        tpm: int = 100_000,
    ) -> None:
        """Configure RPM + TPM buckets for a (provider, model_id) pair."""
        key = (provider, model_id)
        # RPM bucket: capacity=rpm, refill=rpm/60 tokens per second
        self._rpm_buckets[key] = _TokenBucket(
            capacity=float(rpm),
            refill_rate=rpm / 60.0,
        )
        # TPM bucket: capacity=tpm, refill=tpm/60 tokens per second
        self._tpm_buckets[key] = _TokenBucket(
            capacity=float(tpm),
            refill_rate=tpm / 60.0,
        )

    async def acquire(
        self,
        provider: str,
        model_id: str,
        *,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        charge_rpm: bool = True,
    ) -> None:
        """
        Consume 1 RPM token (if charge_rpm=True) and (prompt + completion) TPM tokens.

        Raises RateLimitExceededError with retry_after_seconds if any
        bucket is exhausted.
        """
        key = (provider, model_id)
        rpm_bucket = self._rpm_buckets.get(key)
        tpm_bucket = self._tpm_buckets.get(key)

        if charge_rpm and rpm_bucket:
            wait = await rpm_bucket.acquire(1.0)
            if wait > 0:
                model_gateway_logger.warning(
                    "rate_limit_rpm",
                    provider=provider,
                    model_id=model_id,
                    retry_after=round(wait, 2),
                )
                raise RateLimitExceededError(
                    f"RPM limit exceeded for {provider}/{model_id}. Retry after {wait:.1f}s."
                )

        total_tokens = float(prompt_tokens + completion_tokens)
        if tpm_bucket and total_tokens > 0:
            wait = await tpm_bucket.acquire(total_tokens)
            if wait > 0:
                model_gateway_logger.warning(
                    "rate_limit_tpm",
                    provider=provider,
                    model_id=model_id,
                    tokens=total_tokens,
                    retry_after=round(wait, 2),
                )
                raise RateLimitExceededError(
                    f"TPM limit exceeded for {provider}/{model_id}. Retry after {wait:.1f}s."
                )

    def available_rpm(self, provider: str, model_id: str) -> float:
        bucket = self._rpm_buckets.get((provider, model_id))
        return bucket.available() if bucket else float("inf")

    def available_tpm(self, provider: str, model_id: str) -> float:
        bucket = self._tpm_buckets.get((provider, model_id))
        return bucket.available() if bucket else float("inf")
