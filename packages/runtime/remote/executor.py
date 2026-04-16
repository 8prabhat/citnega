"""Remote worker execution backends with signed run envelopes."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import ssl
import time
from typing import TYPE_CHECKING, Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from citnega.packages.runtime.remote.envelopes import (
    EnvelopeSigner,
    EnvelopeVerificationResult,
    RemoteRunEnvelope,
    build_run_envelope,
)
from citnega.packages.shared.errors import CitnegaError

if TYPE_CHECKING:
    from pydantic import BaseModel

    from citnega.packages.protocol.callables.context import CallContext
    from citnega.packages.protocol.callables.interfaces import IInvocable
    from citnega.packages.protocol.callables.results import InvokeResult


@dataclass(frozen=True)
class RemoteDispatchReport:
    worker_id: str
    envelope: RemoteRunEnvelope
    verification: EnvelopeVerificationResult
    duration_ms: int


class InProcessRemoteWorkerPool:
    """
    Remote-worker model backed by bounded in-process workers.

    This is the default P3 execution backend:
      - models dispatch explicitly to worker IDs,
      - wraps each dispatch in a signed run envelope,
      - verifies envelope prior to invocation.
    """

    def __init__(
        self,
        *,
        workers: int = 2,
        signing_key: str = "",
        signing_key_id: str = "current",
        verification_keys: object | None = None,
        require_signed_envelopes: bool = True,
        simulate_latency_ms: int = 0,
    ) -> None:
        self._workers = [f"remote-worker-{i + 1}" for i in range(max(1, workers))]
        self._cursor = 0
        self._cursor_lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(max(1, workers))
        self._signer = EnvelopeSigner(
            signing_key,
            require_signature=require_signed_envelopes,
            key_id=signing_key_id,
            verification_keys=verification_keys,
        )
        self._latency_ms = max(0, int(simulate_latency_ms))

    async def invoke(
        self,
        *,
        target: IInvocable,
        input_obj: BaseModel,
        context: CallContext,
        parent_callable: str,
        attempt: int = 1,
        worker_hint: str = "",
    ) -> tuple[InvokeResult, RemoteDispatchReport]:
        _, envelope, verification = _build_signed_envelope(
            signer=self._signer,
            target=target,
            input_obj=input_obj,
            context=context,
            parent_callable=parent_callable,
            attempt=attempt,
            worker_hint=worker_hint,
        )

        started = time.monotonic()
        async with self._semaphore:
            worker_id = await self._next_worker_id()
            if self._latency_ms > 0:
                await asyncio.sleep(self._latency_ms / 1000.0)
            result = await target.invoke(input_obj, context)
        duration_ms = int((time.monotonic() - started) * 1000)
        return result, RemoteDispatchReport(
            worker_id=worker_id,
            envelope=envelope,
            verification=verification,
            duration_ms=duration_ms,
        )

    async def _next_worker_id(self) -> str:
        async with self._cursor_lock:
            worker_id = self._workers[self._cursor]
            self._cursor = (self._cursor + 1) % len(self._workers)
            return worker_id


class HttpRemoteWorkerPool:
    """
    Network-backed remote worker client.

    Request contract (JSON POST body):
      {
        "envelope": { ... signed RemoteRunEnvelope ... },
        "target_callable": "<name>",
        "input": { ... validated callable input ... },
        "session": { "session_id": "...", "run_id": "...", "turn_id": "..." }
      }

    Response contract:
      {
        "worker_id": "http-worker-1",
        "verification": {"ok": true, "reason": "verified"},
        "duration_ms": 12,
        "result": {"success": true, "output": {...}}  # or success=false + error
      }
    """

    def __init__(
        self,
        *,
        endpoint: str,
        signing_key: str = "",
        signing_key_id: str = "current",
        verification_keys: object | None = None,
        require_signed_envelopes: bool = True,
        timeout_ms: int = 15000,
        auth_token: str = "",
        verify_tls: bool = True,
        ca_cert_path: str = "",
        client_cert_path: str = "",
        client_key_path: str = "",
    ) -> None:
        endpoint = endpoint.strip()
        if not endpoint:
            raise ValueError("Remote HTTP endpoint is required for worker_mode='http'.")

        self._endpoint = endpoint
        self._timeout_ms = max(1, int(timeout_ms))
        self._auth_token = auth_token.strip()
        self._verify_tls = bool(verify_tls)
        self._ca_cert_path = ca_cert_path.strip()
        self._client_cert_path = client_cert_path.strip()
        self._client_key_path = client_key_path.strip()
        if bool(self._client_cert_path) != bool(self._client_key_path):
            raise ValueError(
                "Remote HTTP mTLS requires both client_cert_path and client_key_path."
            )
        self._signer = EnvelopeSigner(
            signing_key,
            require_signature=require_signed_envelopes,
            key_id=signing_key_id,
            verification_keys=verification_keys,
        )

    async def invoke(
        self,
        *,
        target: IInvocable,
        input_obj: BaseModel,
        context: CallContext,
        parent_callable: str,
        attempt: int = 1,
        worker_hint: str = "",
    ) -> tuple[InvokeResult, RemoteDispatchReport]:
        from citnega.packages.protocol.callables.results import InvokeResult

        payload, envelope, verification = _build_signed_envelope(
            signer=self._signer,
            target=target,
            input_obj=input_obj,
            context=context,
            parent_callable=parent_callable,
            attempt=attempt,
            worker_hint=worker_hint,
        )
        request_body = {
            "envelope": envelope.model_dump(mode="json"),
            "target_callable": target.name,
            "input": payload,
            "session": {
                "session_id": context.session_id,
                "run_id": context.run_id,
                "turn_id": context.turn_id,
            },
        }

        started = time.monotonic()
        response = await asyncio.to_thread(self._post_json, request_body)
        duration_ms = int((time.monotonic() - started) * 1000)

        worker_id = str(response.get("worker_id", "")).strip() or "remote-http-worker"
        remote_verification = _parse_remote_verification(
            response.get("verification"),
            fallback=verification,
        )
        if not remote_verification.ok:
            raise ValueError(f"Remote envelope verification failed: {remote_verification.reason}")

        remote_duration = _as_int(response.get("duration_ms"), fallback=duration_ms)
        result_payload = response.get("result")
        if not isinstance(result_payload, dict):
            raise ValueError("Remote HTTP response missing object field: result")

        success = bool(result_payload.get("success", False))
        if success:
            output_payload = result_payload.get("output")
            if not isinstance(output_payload, dict):
                raise ValueError("Remote HTTP success response missing object field: result.output")
            output_obj = target.output_schema.model_validate(output_payload)
            invoke_result = InvokeResult.ok(
                name=target.name,
                callable_type=target.callable_type,
                output=output_obj,
                duration_ms=remote_duration,
            )
        else:
            error_payload = result_payload.get("error")
            if isinstance(error_payload, dict):
                message = str(error_payload.get("message", "")).strip()
            else:
                message = ""
            if not message:
                message = "Remote invocation failed."
            invoke_result = InvokeResult.from_error(
                name=target.name,
                callable_type=target.callable_type,
                error=CitnegaError(message),
                duration_ms=remote_duration,
            )

        return invoke_result, RemoteDispatchReport(
            worker_id=worker_id,
            envelope=envelope,
            verification=remote_verification,
            duration_ms=remote_duration,
        )

    def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw_body = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"

        req = urllib_request.Request(
            self._endpoint,
            data=raw_body,
            headers=headers,
            method="POST",
        )
        timeout_s = self._timeout_ms / 1000.0
        ssl_context = self._build_ssl_context()

        try:
            with urllib_request.urlopen(req, timeout=timeout_s, context=ssl_context) as response:
                body = response.read().decode("utf-8")
        except urllib_error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace").strip()
            message = details or str(exc.reason)
            raise ValueError(f"Remote HTTP dispatch failed ({exc.code}): {message}") from exc
        except urllib_error.URLError as exc:
            raise ValueError(f"Remote HTTP dispatch failed: {exc.reason}") from exc
        except ssl.SSLError as exc:
            raise ValueError(f"Remote HTTP dispatch failed: {exc}") from exc
        except TimeoutError as exc:
            raise ValueError("Remote HTTP dispatch timed out.") from exc

        try:
            decoded = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ValueError("Remote HTTP response was not valid JSON.") from exc

        if not isinstance(decoded, dict):
            raise ValueError("Remote HTTP response root must be a JSON object.")
        return decoded

    def _build_ssl_context(self) -> ssl.SSLContext | None:
        if not self._endpoint.startswith("https://"):
            return None

        if not self._verify_tls:
            context = ssl._create_unverified_context()
        else:
            context = ssl.create_default_context(
                cafile=self._ca_cert_path or None,
            )
        if self._client_cert_path:
            context.load_cert_chain(
                certfile=self._client_cert_path,
                keyfile=self._client_key_path or None,
            )
        return context


def _build_signed_envelope(
    *,
    signer: EnvelopeSigner,
    target: IInvocable,
    input_obj: BaseModel,
    context: CallContext,
    parent_callable: str,
    attempt: int,
    worker_hint: str,
) -> tuple[dict[str, Any], RemoteRunEnvelope, EnvelopeVerificationResult]:
    payload = input_obj.model_dump(mode="json")
    envelope = build_run_envelope(
        session_id=context.session_id,
        run_id=context.run_id,
        turn_id=context.turn_id,
        parent_callable=parent_callable,
        target_callable=target.name,
        payload=payload,
        attempt=attempt,
        worker_hint=worker_hint,
    )
    envelope = signer.sign(envelope)
    verification = signer.verify(envelope)
    if not verification.ok:
        raise ValueError(f"Remote envelope verification failed: {verification.reason}")
    return payload, envelope, verification


def _parse_remote_verification(
    payload: object,
    *,
    fallback: EnvelopeVerificationResult,
) -> EnvelopeVerificationResult:
    if not isinstance(payload, dict):
        return fallback
    ok = bool(payload.get("ok", fallback.ok))
    reason = str(payload.get("reason", fallback.reason)).strip()
    if not reason:
        reason = "verified" if ok else "failed"
    return EnvelopeVerificationResult(ok=ok, reason=reason)


def _as_int(value: object, *, fallback: int) -> int:
    try:
        parsed = int(str(value))
    except Exception:
        return fallback
    return max(0, parsed)
