"""Reference HTTP remote worker service with explicit allowlist enforcement."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import ssl
import threading
import time
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.context import CallContext
from citnega.packages.protocol.models.sessions import SessionConfig
from citnega.packages.runtime.remote.envelopes import (
    EnvelopeSigner,
    EnvelopeVerificationResult,
    RemoteRunEnvelope,
    payload_sha256,
)
from citnega.packages.shared.errors import CallableNotFoundError

if TYPE_CHECKING:
    from collections.abc import Iterator

    from citnega.packages.protocol.callables.interfaces import IInvocable
    from citnega.packages.runtime.app_service import ApplicationService

_ISOLATION_PROFILE_DESCRIPTIONS = {
    "process": "Dedicated worker process with explicit callable allowlist enforcement.",
    "container": "Dedicated worker intended to run inside a container boundary with allowlist enforcement.",
}


class RemoteInvokeSession(BaseModel):
    session_id: str
    run_id: str
    turn_id: str


class RemoteInvokeRequest(BaseModel):
    envelope: RemoteRunEnvelope
    target_callable: str
    input: dict[str, Any] = Field(default_factory=dict)
    session: RemoteInvokeSession


class RemoteInvokeResult(BaseModel):
    success: bool
    output: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


class RemoteInvokeResponse(BaseModel):
    worker_id: str
    verification: EnvelopeVerificationResult
    duration_ms: int
    isolation_profile: str
    result: RemoteInvokeResult


@dataclass(frozen=True)
class RemoteWorkerTLSConfig:
    cert_path: str = ""
    key_path: str = ""
    client_ca_path: str = ""
    require_client_cert: bool = False

    @property
    def enabled(self) -> bool:
        return bool(self.cert_path and self.key_path)

    @property
    def mtls_required(self) -> bool:
        return self.enabled and self.require_client_cert

    def validate(self) -> None:
        if bool(self.cert_path) != bool(self.key_path):
            raise ValueError("TLS server cert and key must be configured together.")
        if self.require_client_cert and not self.client_ca_path:
            raise ValueError("mTLS requires a client CA bundle.")
        if self.client_ca_path and not self.enabled:
            raise ValueError("Client CA bundle requires HTTPS worker service to be enabled.")

    def create_ssl_context(self) -> ssl.SSLContext:
        self.validate()
        if not self.enabled:
            raise ValueError("TLS config is not enabled.")
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=self.cert_path, keyfile=self.key_path)
        if self.client_ca_path:
            context.load_verify_locations(cafile=self.client_ca_path)
            context.verify_mode = (
                ssl.CERT_REQUIRED if self.require_client_cert else ssl.CERT_OPTIONAL
            )
        return context


class RemoteWorkerHTTPService:
    """Reference remote worker HTTP service backed by a local callable registry."""

    def __init__(
        self,
        *,
        registry: dict[str, IInvocable],
        signing_key: str,
        allowed_callables: list[str] | tuple[str, ...] | set[str],
        signing_key_id: str = "current",
        verification_keys: object | None = None,
        require_signed_envelopes: bool = True,
        auth_token: str = "",
        worker_id: str = "remote-service-1",
        isolation_profile: str = "process",
        tls_cert_path: str = "",
        tls_key_path: str = "",
        tls_client_ca_path: str = "",
        tls_require_client_cert: bool = False,
        session_resolver: object | None = None,
    ) -> None:
        allowed = frozenset(
            str(name).strip() for name in allowed_callables if str(name).strip()
        )
        if not allowed:
            raise ValueError("Remote worker service requires an explicit non-empty callable allowlist.")

        profile = str(isolation_profile).strip().lower() or "process"
        if profile not in _ISOLATION_PROFILE_DESCRIPTIONS:
            raise ValueError(
                f"Unsupported isolation_profile={isolation_profile!r}. "
                f"Supported: {sorted(_ISOLATION_PROFILE_DESCRIPTIONS)}."
            )

        self._registry = dict(registry)
        self._signer = EnvelopeSigner(
            signing_key,
            require_signature=require_signed_envelopes,
            key_id=signing_key_id,
            verification_keys=verification_keys,
        )
        self._allowed_callables = allowed
        self._auth_token = auth_token.strip()
        self._worker_id = worker_id.strip() or "remote-service-1"
        self._isolation_profile = profile
        self._tls = RemoteWorkerTLSConfig(
            cert_path=tls_cert_path.strip(),
            key_path=tls_key_path.strip(),
            client_ca_path=tls_client_ca_path.strip(),
            require_client_cert=bool(tls_require_client_cert),
        )
        self._tls.validate()
        self._session_resolver = session_resolver
        self._invoke_lock = threading.Lock()

    @property
    def allowed_callables(self) -> frozenset[str]:
        return self._allowed_callables

    @property
    def isolation_profile(self) -> str:
        return self._isolation_profile

    @property
    def tls_enabled(self) -> bool:
        return self._tls.enabled

    @property
    def mtls_required(self) -> bool:
        return self._tls.mtls_required

    def health_payload(self) -> dict[str, object]:
        return {
            "ok": True,
            "worker_id": self._worker_id,
            "isolation_profile": self._isolation_profile,
            "isolation_description": _ISOLATION_PROFILE_DESCRIPTIONS[self._isolation_profile],
            "allowed_callables": sorted(self._allowed_callables),
            "require_signed_envelopes": self._signer.require_signature,
            "active_signing_key_id": self._signer.active_key_id,
            "accepted_key_ids": list(self._signer.accepted_key_ids),
            "auth_required": bool(self._auth_token),
            "tls_enabled": self.tls_enabled,
            "mtls_required": self.mtls_required,
        }

    def create_server(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 0,
    ) -> ThreadingHTTPServer:
        service = self

        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                status, payload = service.handle_http_request(
                    method="GET",
                    path=self.path,
                    headers=dict(self.headers.items()),
                    raw_body=b"",
                )
                self._write_json(payload, status=status)

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                raw_body = self.rfile.read(length)
                status, payload = service.handle_http_request(
                    method="POST",
                    path=self.path,
                    headers=dict(self.headers.items()),
                    raw_body=raw_body,
                )
                self._write_json(payload, status=status)

            def log_message(self, format: str, *args: object) -> None:
                return

            def _write_json(self, payload: dict[str, object], *, status: int) -> None:
                body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = ThreadingHTTPServer((host, int(port)), _Handler)
        server.daemon_threads = True
        if self._tls.enabled:
            server.socket = self._tls.create_ssl_context().wrap_socket(
                server.socket,
                server_side=True,
            )
        return server

    @contextmanager
    def serve_in_thread(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 0,
    ) -> Iterator[str]:
        server = self.create_server(host=host, port=port)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        scheme = "https" if self._tls.enabled else "http"
        base_url = f"{scheme}://127.0.0.1:{server.server_address[1]}"
        try:
            yield base_url
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5.0)

    def handle_http_request(
        self,
        *,
        method: str,
        path: str,
        headers: dict[str, str],
        raw_body: bytes,
    ) -> tuple[int, dict[str, object]]:
        if method == "GET" and path == "/health":
            return 200, self.health_payload()

        if path != "/invoke":
            return 404, {"error": "not_found"}

        if method != "POST":
            return 405, {"error": "method_not_allowed"}

        if self._auth_token:
            actual = headers.get("Authorization", "")
            expected = f"Bearer {self._auth_token}"
            if actual != expected:
                return 401, {"error": "unauthorized"}

        try:
            request = RemoteInvokeRequest.model_validate_json(raw_body)
        except Exception as exc:
            return 400, {"error": f"invalid_request:{exc}"}

        try:
            with self._invoke_lock:
                response = asyncio.run(self._handle_invoke(request))
            return 200, response.model_dump(mode="json")
        except PermissionError as exc:
            return 403, {"error": str(exc)}
        except CallableNotFoundError as exc:
            return 404, {"error": exc.message}
        except ValueError as exc:
            return 400, {"error": str(exc)}
        except Exception as exc:
            return 500, {"error": f"remote_worker_internal_error:{exc}"}

    async def _handle_invoke(self, request: RemoteInvokeRequest) -> RemoteInvokeResponse:
        target_name = request.target_callable.strip()
        if not target_name:
            raise ValueError("target_callable must be a non-empty string.")
        if target_name != request.envelope.target_callable:
            raise ValueError("target_callable does not match envelope.target_callable.")
        if target_name not in self._allowed_callables:
            raise PermissionError(f"Callable {target_name!r} is not allowed by remote worker policy.")

        target = self._registry.get(target_name)
        if target is None:
            raise CallableNotFoundError(f"Callable not found: {target_name}")

        if payload_sha256(request.input) != request.envelope.payload_sha256:
            verification = EnvelopeVerificationResult(ok=False, reason="payload_mismatch")
            return RemoteInvokeResponse(
                worker_id=self._worker_id,
                verification=verification,
                duration_ms=0,
                isolation_profile=self._isolation_profile,
                result=RemoteInvokeResult(
                    success=False,
                    error={"message": "Remote envelope verification failed: payload_mismatch"},
                ),
            )

        verification = self._signer.verify(request.envelope)
        if not verification.ok:
            return RemoteInvokeResponse(
                worker_id=self._worker_id,
                verification=verification,
                duration_ms=0,
                isolation_profile=self._isolation_profile,
                result=RemoteInvokeResult(
                    success=False,
                    error={"message": f"Remote envelope verification failed: {verification.reason}"},
                ),
            )

        input_obj = target.input_schema.model_validate(request.input)
        session_config = await self._resolve_session_config(request.session)
        context = CallContext(
            session_id=request.session.session_id,
            run_id=request.session.run_id,
            turn_id=request.session.turn_id,
            session_config=session_config,
        )

        started = time.monotonic()
        result = await target.invoke(input_obj, context)
        duration_ms = int((time.monotonic() - started) * 1000)

        payload = RemoteInvokeResult(
            success=result.success,
            output=(
                result.output.model_dump(mode="json")
                if result.output is not None
                else None
            ),
            error=(
                result.error.to_dict()
                if result.error is not None
                else None
            ),
        )
        return RemoteInvokeResponse(
            worker_id=self._worker_id,
            verification=verification,
            duration_ms=duration_ms,
            isolation_profile=self._isolation_profile,
            result=payload,
        )

    async def _resolve_session_config(self, session: RemoteInvokeSession) -> SessionConfig:
        resolver = self._session_resolver
        if resolver is None:
            return _fallback_session_config(session)

        resolved = resolver(session)
        if asyncio.iscoroutine(resolved):
            resolved = await resolved
        if isinstance(resolved, SessionConfig):
            return resolved
        return _fallback_session_config(session)

    @classmethod
    def from_application_service(
        cls,
        service: ApplicationService,
        *,
        signing_key: str,
        allowed_callables: list[str] | tuple[str, ...] | set[str],
        signing_key_id: str = "current",
        verification_keys: object | None = None,
        require_signed_envelopes: bool = True,
        auth_token: str = "",
        worker_id: str = "remote-service-1",
        isolation_profile: str = "process",
        tls_cert_path: str = "",
        tls_key_path: str = "",
        tls_client_ca_path: str = "",
        tls_require_client_cert: bool = False,
    ) -> RemoteWorkerHTTPService:
        registry = build_remote_callable_registry(service)

        async def _resolve(session: RemoteInvokeSession) -> SessionConfig:
            existing = await service.get_session(session.session_id)
            if existing is not None:
                return existing.config
            return _fallback_session_config(session)

        return cls(
            registry=registry,
            signing_key=signing_key,
            signing_key_id=signing_key_id,
            verification_keys=verification_keys,
            allowed_callables=allowed_callables,
            require_signed_envelopes=require_signed_envelopes,
            auth_token=auth_token,
            worker_id=worker_id,
            isolation_profile=isolation_profile,
            tls_cert_path=tls_cert_path,
            tls_key_path=tls_key_path,
            tls_client_ca_path=tls_client_ca_path,
            tls_require_client_cert=tls_require_client_cert,
            session_resolver=_resolve,
        )


def build_remote_callable_registry(service: ApplicationService) -> dict[str, IInvocable]:
    registry: dict[str, IInvocable] = {}
    registry.update(getattr(service, "_tool_registry", {}))
    registry.update(getattr(service, "_agent_registry", {}))
    return registry


def _fallback_session_config(session: RemoteInvokeSession) -> SessionConfig:
    return SessionConfig(
        session_id=session.session_id,
        name="remote-worker-session",
        framework="direct",
        default_model_id="remote-worker",
    )
