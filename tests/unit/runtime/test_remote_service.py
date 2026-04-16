"""Unit tests for the reference remote worker HTTP service."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel
import pytest

from citnega.packages.protocol.callables.context import CallContext
from citnega.packages.protocol.callables.results import InvokeResult
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.protocol.models.sessions import SessionConfig
from citnega.packages.runtime.remote.envelopes import build_run_envelope
from citnega.packages.runtime.remote.executor import HttpRemoteWorkerPool
from citnega.packages.runtime.remote.service import (
    RemoteInvokeRequest,
    RemoteInvokeSession,
    RemoteWorkerHTTPService,
)


class _Input(BaseModel):
    task: str = ""


class _Output(BaseModel):
    response: str


class _FakeCallable:
    name = "fake_tool"
    callable_type = CallableType.TOOL
    input_schema = _Input
    output_schema = _Output

    async def invoke(self, input_obj: _Input, context: CallContext) -> InvokeResult:
        return InvokeResult.ok(
            name=self.name,
            callable_type=self.callable_type,
            output=_Output(response=f"svc:{input_obj.task}:{context.run_id}"),
            duration_ms=1,
        )


def _context() -> CallContext:
    return CallContext(
        session_id="s1",
        run_id="r1",
        turn_id="t1",
        session_config=SessionConfig(
            session_id="s1",
            name="remote-service-test",
            framework="direct",
            default_model_id="x",
        ),
    )


def _make_service() -> RemoteWorkerHTTPService:
    return RemoteWorkerHTTPService(
        registry={"fake_tool": _FakeCallable()},
        signing_key="secret",
        signing_key_id="2026-04",
        verification_keys=["2026-03=old-secret"],
        allowed_callables=["fake_tool"],
        require_signed_envelopes=True,
        auth_token="token123",
        worker_id="svc-1",
        isolation_profile="container",
    )


def _tls_paths() -> dict[str, str]:
    fixture_dir = Path(__file__).resolve().parents[2] / "fixtures" / "remote_tls"
    return {
        "ca_cert": str(fixture_dir / "ca-cert.pem"),
        "server_cert": str(fixture_dir / "server-cert.pem"),
        "server_key": str(fixture_dir / "server-key.pem"),
        "client_cert": str(fixture_dir / "client-cert.pem"),
        "client_key": str(fixture_dir / "client-key.pem"),
    }


def test_remote_worker_service_requires_explicit_allowlist() -> None:
    with pytest.raises(ValueError, match="explicit non-empty callable allowlist"):
        RemoteWorkerHTTPService(
            registry={"fake_tool": _FakeCallable()},
            signing_key="secret",
            allowed_callables=[],
        )


def test_remote_worker_service_health_payload_includes_isolation_profile() -> None:
    service = _make_service()

    payload = service.health_payload()

    assert payload["ok"] is True
    assert payload["isolation_profile"] == "container"
    assert payload["allowed_callables"] == ["fake_tool"]
    assert payload["active_signing_key_id"] == "2026-04"
    assert payload["accepted_key_ids"] == ["2026-03", "2026-04"]
    assert payload["auth_required"] is True
    assert payload["tls_enabled"] is False
    assert payload["mtls_required"] is False


def test_remote_worker_service_rejects_disallowed_callable() -> None:
    service = _make_service()
    session = RemoteInvokeSession(session_id="s1", run_id="r1", turn_id="t1")
    request = RemoteInvokeRequest(
        envelope=build_run_envelope(
            session_id="s1",
            run_id="r1",
            turn_id="t1",
            parent_callable="orchestrator_agent",
            target_callable="other_tool",
            payload={"task": "ship"},
        ),
        target_callable="other_tool",
        input={"task": "ship"},
        session=session,
    )
    raw_body = request.model_dump_json().encode("utf-8")

    status, payload = service.handle_http_request(
        method="POST",
        path="/invoke",
        headers={"Authorization": "Bearer token123"},
        raw_body=raw_body,
    )

    assert status == 403
    assert "not allowed" in str(payload["error"])


def test_remote_worker_service_rejects_payload_hash_mismatch() -> None:
    service = _make_service()
    session = RemoteInvokeSession(session_id="s1", run_id="r1", turn_id="t1")
    request = RemoteInvokeRequest(
        envelope=build_run_envelope(
            session_id="s1",
            run_id="r1",
            turn_id="t1",
            parent_callable="orchestrator_agent",
            target_callable="fake_tool",
            payload={"task": "ship"},
        ),
        target_callable="fake_tool",
        input={"task": "tampered"},
        session=session,
    )
    request = request.model_copy(
        update={"envelope": request.envelope.model_copy(update={"signature": "123"})}
    )

    status, payload = service.handle_http_request(
        method="POST",
        path="/invoke",
        headers={"Authorization": "Bearer token123"},
        raw_body=request.model_dump_json().encode("utf-8"),
    )

    assert status == 200
    assert payload["verification"]["reason"] == "payload_mismatch"
    assert payload["result"]["success"] is False


@pytest.mark.asyncio
async def test_remote_worker_service_roundtrip_invokes_callable() -> None:
    service = _make_service()
    with service.serve_in_thread() as base_url:
        pool = HttpRemoteWorkerPool(
            endpoint=f"{base_url}/invoke",
            signing_key="secret",
            signing_key_id="2026-04",
            require_signed_envelopes=True,
            timeout_ms=5000,
            auth_token="token123",
        )
        result, report = await pool.invoke(
            target=_FakeCallable(),
            input_obj=_Input(task="ship"),
            context=_context(),
            parent_callable="orchestrator_agent",
        )

        health_status, health_payload = service.handle_http_request(
            method="GET",
            path="/health",
            headers={},
            raw_body=b"",
        )

    assert result.success
    assert result.output is not None
    assert result.output.response == "svc:ship:r1"
    assert report.worker_id == "svc-1"
    assert report.verification.ok
    assert health_status == 200
    assert health_payload["isolation_profile"] == "container"


@pytest.mark.asyncio
async def test_remote_worker_service_accepts_rotated_historical_key() -> None:
    service = _make_service()
    with service.serve_in_thread() as base_url:
        pool = HttpRemoteWorkerPool(
            endpoint=f"{base_url}/invoke",
            signing_key="old-secret",
            signing_key_id="2026-03",
            require_signed_envelopes=True,
            timeout_ms=5000,
            auth_token="token123",
        )
        result, report = await pool.invoke(
            target=_FakeCallable(),
            input_obj=_Input(task="ship"),
            context=_context(),
            parent_callable="orchestrator_agent",
        )

    assert result.success
    assert report.verification.ok
    assert report.envelope.key_id == "2026-03"


@pytest.mark.asyncio
async def test_remote_worker_service_roundtrip_supports_mtls() -> None:
    tls = _tls_paths()
    service = RemoteWorkerHTTPService(
        registry={"fake_tool": _FakeCallable()},
        signing_key="secret",
        signing_key_id="2026-04",
        allowed_callables=["fake_tool"],
        require_signed_envelopes=True,
        auth_token="token123",
        worker_id="svc-mtls",
        isolation_profile="process",
        tls_cert_path=tls["server_cert"],
        tls_key_path=tls["server_key"],
        tls_client_ca_path=tls["ca_cert"],
        tls_require_client_cert=True,
    )

    with service.serve_in_thread() as base_url:
        pool = HttpRemoteWorkerPool(
            endpoint=f"{base_url}/invoke",
            signing_key="secret",
            signing_key_id="2026-04",
            require_signed_envelopes=True,
            timeout_ms=5000,
            auth_token="token123",
            ca_cert_path=tls["ca_cert"],
            client_cert_path=tls["client_cert"],
            client_key_path=tls["client_key"],
        )
        result, report = await pool.invoke(
            target=_FakeCallable(),
            input_obj=_Input(task="ship"),
            context=_context(),
            parent_callable="orchestrator_agent",
        )

    assert base_url.startswith("https://")
    assert result.success
    assert report.worker_id == "svc-mtls"
    assert service.health_payload()["tls_enabled"] is True
    assert service.health_payload()["mtls_required"] is True


@pytest.mark.asyncio
async def test_remote_worker_service_mtls_rejects_missing_client_certificate() -> None:
    tls = _tls_paths()
    service = RemoteWorkerHTTPService(
        registry={"fake_tool": _FakeCallable()},
        signing_key="secret",
        allowed_callables=["fake_tool"],
        require_signed_envelopes=True,
        auth_token="token123",
        worker_id="svc-mtls",
        isolation_profile="process",
        tls_cert_path=tls["server_cert"],
        tls_key_path=tls["server_key"],
        tls_client_ca_path=tls["ca_cert"],
        tls_require_client_cert=True,
    )

    with service.serve_in_thread() as base_url:
        pool = HttpRemoteWorkerPool(
            endpoint=f"{base_url}/invoke",
            signing_key="secret",
            require_signed_envelopes=True,
            timeout_ms=5000,
            auth_token="token123",
            ca_cert_path=tls["ca_cert"],
        )
        with pytest.raises(ValueError, match="Remote HTTP dispatch failed"):
            await pool.invoke(
                target=_FakeCallable(),
                input_obj=_Input(task="ship"),
                context=_context(),
                parent_callable="orchestrator_agent",
            )
