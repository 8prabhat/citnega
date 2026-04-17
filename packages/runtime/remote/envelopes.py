"""Signed run envelopes for remote callable execution."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import hmac
import json
from typing import Any
import uuid

from pydantic import BaseModel, Field


class RemoteRunEnvelope(BaseModel):
    """Portable execution envelope attached to remote dispatch requests."""

    envelope_id: str = Field(default_factory=lambda: f"env-{uuid.uuid4().hex}")
    session_id: str
    run_id: str
    turn_id: str
    parent_callable: str
    target_callable: str
    attempt: int = 1
    worker_hint: str = ""
    key_id: str = ""
    issued_at: str = Field(default_factory=lambda: datetime.now(tz=UTC).isoformat())
    payload_sha256: str
    signature: str = ""

    def signing_payload(self) -> dict[str, Any]:
        return {
            "envelope_id": self.envelope_id,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "turn_id": self.turn_id,
            "parent_callable": self.parent_callable,
            "target_callable": self.target_callable,
            "attempt": self.attempt,
            "worker_hint": self.worker_hint,
            "key_id": self.key_id,
            "issued_at": self.issued_at,
            "payload_sha256": self.payload_sha256,
        }


class EnvelopeVerificationResult(BaseModel):
    ok: bool
    reason: str = ""


class EnvelopeSigner:
    """HMAC-based signing/verification for remote run envelopes."""

    def __init__(
        self,
        key: str,
        *,
        require_signature: bool = True,
        key_id: str = "",
        verification_keys: object | None = None,
    ) -> None:
        self._key = key.strip()
        self._key_id = key_id.strip()
        self._require_signature = bool(require_signature)
        self._verification_keys = parse_verification_keys(verification_keys)
        if self._key:
            active_key_id = self._key_id or "current"
            existing = self._verification_keys.get(active_key_id)
            if existing and existing != self._key:
                raise ValueError(
                    f"Verification key {active_key_id!r} does not match the active signing key."
                )
            self._key_id = active_key_id
            self._verification_keys[active_key_id] = self._key
        else:
            self._key_id = ""

    @property
    def require_signature(self) -> bool:
        return self._require_signature

    @property
    def active_key_id(self) -> str:
        return self._key_id

    @property
    def accepted_key_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._verification_keys))

    def sign(self, envelope: RemoteRunEnvelope) -> RemoteRunEnvelope:
        if not self._key:
            if self._require_signature:
                raise ValueError("Envelope signing key is required but missing.")
            return envelope.model_copy(update={"key_id": "", "signature": ""})

        signed_envelope = envelope.model_copy(update={"key_id": self._key_id or "current"})
        digest = _hmac_hex(self._key, signed_envelope.signing_payload())
        return signed_envelope.model_copy(update={"signature": digest})

    def verify(self, envelope: RemoteRunEnvelope) -> EnvelopeVerificationResult:
        signature = envelope.signature.strip().lower()
        if not signature:
            if self._require_signature:
                return EnvelopeVerificationResult(ok=False, reason="missing_signature")
            return EnvelopeVerificationResult(ok=True, reason="signature_optional")

        if not self._verification_keys:
            if self._require_signature:
                return EnvelopeVerificationResult(ok=False, reason="missing_signing_key")
            return EnvelopeVerificationResult(ok=True, reason="signature_unverified_no_key")

        key_id = envelope.key_id.strip()
        candidate_keys: list[str]
        if key_id:
            matched_key = self._verification_keys.get(key_id)
            if not matched_key:
                return EnvelopeVerificationResult(ok=False, reason="unknown_key_id")
            candidate_keys = [matched_key]
        else:
            candidate_keys = list(self._verification_keys.values())

        for candidate_key in candidate_keys:
            expected = _hmac_hex(candidate_key, envelope.signing_payload()).lower()
            if hmac.compare_digest(signature, expected):
                return EnvelopeVerificationResult(ok=True, reason="verified")

        if not candidate_keys:
            return EnvelopeVerificationResult(ok=False, reason="signature_mismatch")
        return EnvelopeVerificationResult(ok=False, reason="signature_mismatch")


def payload_sha256(payload: Any) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def build_run_envelope(
    *,
    session_id: str,
    run_id: str,
    turn_id: str,
    parent_callable: str,
    target_callable: str,
    payload: Any,
    attempt: int = 1,
    worker_hint: str = "",
) -> RemoteRunEnvelope:
    return RemoteRunEnvelope(
        session_id=session_id,
        run_id=run_id,
        turn_id=turn_id,
        parent_callable=parent_callable,
        target_callable=target_callable,
        attempt=max(1, attempt),
        worker_hint=worker_hint.strip(),
        payload_sha256=payload_sha256(payload),
    )


def _hmac_hex(key: str, payload: dict[str, Any]) -> str:
    body = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hmac.new(key.encode("utf-8"), body, hashlib.sha256).hexdigest()


def parse_verification_keys(entries: object | None) -> dict[str, str]:
    """Parse remote verification key entries into a stable key-id map."""
    if entries is None:
        return {}

    normalized: dict[str, str] = {}
    if isinstance(entries, dict):
        iterable = entries.items()
    else:
        if isinstance(entries, str):
            entries = [entries]
        if not isinstance(entries, (list, tuple, set, frozenset)):
            raise ValueError(
                "verification_keys must be a mapping or an iterable of 'key_id=secret' entries."
            )
        iterable = []
        for item in entries:
            if isinstance(item, str):
                key_id, sep, key = item.partition("=")
                if not sep:
                    raise ValueError(
                        f"Invalid verification key entry {item!r}. Expected 'key_id=secret'."
                    )
            elif isinstance(item, (tuple, list)) and len(item) == 2:
                key_id, key = item
            else:
                raise ValueError(
                    "verification_keys entries must be strings or 2-item pairs."
                )
            iterable.append((key_id, key))

    for raw_key_id, raw_key in iterable:
        key_id = str(raw_key_id).strip()
        key = str(raw_key).strip()
        if not key_id or not key:
            raise ValueError("verification_keys entries require non-empty key id and key.")
        existing = normalized.get(key_id)
        if existing and existing != key:
            raise ValueError(
                f"Duplicate verification key id {key_id!r} was provided with different values."
            )
        normalized[key_id] = key
    return normalized
