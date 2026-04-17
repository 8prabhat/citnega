"""Unit tests for remote worker pool and signed run envelopes."""

from __future__ import annotations

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading

from pydantic import BaseModel
import pytest

from citnega.packages.protocol.callables.context import CallContext
from citnega.packages.protocol.callables.results import InvokeResult
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.protocol.models.sessions import SessionConfig
from citnega.packages.runtime.remote.envelopes import (
    EnvelopeSigner,
    RemoteRunEnvelope,
    build_run_envelope,
)
from citnega.packages.runtime.remote.executor import HttpRemoteWorkerPool, InProcessRemoteWorkerPool


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
            output=_Output(response=f"ok:{input_obj.task}:{context.run_id}"),
            duration_ms=1,
        )


def _context() -> CallContext:
    return CallContext(
        session_id="s1",
        run_id="r1",
        turn_id="t1",
        session_config=SessionConfig(
            session_id="s1",
            name="remote-test",
            framework="direct",
            default_model_id="x",
        ),
    )


@contextmanager
def _remote_http_server(
    *,
    signing_key: str,
    signing_key_id: str = "current",
    verification_keys: list[str] | None = None,
    auth_token: str = "",
    error_message: str = "",
):
    signer = EnvelopeSigner(
        signing_key,
        require_signature=True,
        key_id=signing_key_id,
        verification_keys=verification_keys,
    )

    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            if self.path != "/invoke":
                self._write_json({"error": "not_found"}, status=404)
                return

            if auth_token:
                expected = f"Bearer {auth_token}"
                if self.headers.get("Authorization", "") != expected:
                    self._write_json({"error": "unauthorized"}, status=401)
                    return

            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8")
            payload = json.loads(raw)

            envelope = RemoteRunEnvelope.model_validate(payload.get("envelope", {}))
            verification = signer.verify(envelope)
            response = {
                "worker_id": "http-worker-1",
                "verification": verification.model_dump(mode="json"),
                "duration_ms": 3,
                "result": {},
            }
            if not verification.ok:
                response["result"] = {
                    "success": False,
                    "error": {"message": f"verification_failed:{verification.reason}"},
                }
            elif error_message:
                response["result"] = {
                    "success": False,
                    "error": {"message": error_message},
                }
            else:
                task = str(payload.get("input", {}).get("task", ""))
                run_id = str(payload.get("session", {}).get("run_id", ""))
                response["result"] = {
                    "success": True,
                    "output": {"response": f"http:{task}:{run_id}"},
                }
            self._write_json(response, status=200)

        def log_message(self, format: str, *args: object) -> None:
            return

        def _write_json(self, payload: dict[str, object], *, status: int) -> None:
            body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    endpoint = f"http://127.0.0.1:{server.server_address[1]}/invoke"
    try:
        yield endpoint
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


def test_envelope_sign_and_verify_success() -> None:
    envelope = build_run_envelope(
        session_id="s1",
        run_id="r1",
        turn_id="t1",
        parent_callable="orchestrator_agent",
        target_callable="qa_agent",
        payload={"goal": "release"},
    )
    signer = EnvelopeSigner("secret", require_signature=True, key_id="2026-04")
    signed = signer.sign(envelope)
    verdict = signer.verify(signed)
    assert verdict.ok
    assert verdict.reason == "verified"
    assert signed.key_id == "2026-04"


def test_envelope_signature_mismatch_detected() -> None:
    envelope = build_run_envelope(
        session_id="s1",
        run_id="r1",
        turn_id="t1",
        parent_callable="orchestrator_agent",
        target_callable="qa_agent",
        payload={"goal": "release"},
    )
    signer = EnvelopeSigner("secret", require_signature=True)
    signed = signer.sign(envelope)

    tampered = signed.model_copy(update={"payload_sha256": "0" * 64})
    verdict = signer.verify(tampered)
    assert not verdict.ok
    assert verdict.reason == "signature_mismatch"


def test_envelope_signer_accepts_rotated_historical_key() -> None:
    envelope = build_run_envelope(
        session_id="s1",
        run_id="r1",
        turn_id="t1",
        parent_callable="orchestrator_agent",
        target_callable="qa_agent",
        payload={"goal": "release"},
    )
    old_signer = EnvelopeSigner("old-secret", require_signature=True, key_id="2026-03")
    rotated_signer = EnvelopeSigner(
        "new-secret",
        require_signature=True,
        key_id="2026-04",
        verification_keys=["2026-03=old-secret"],
    )

    signed = old_signer.sign(envelope)
    verdict = rotated_signer.verify(signed)

    assert verdict.ok
    assert verdict.reason == "verified"


def test_envelope_signer_rejects_unknown_key_id() -> None:
    envelope = build_run_envelope(
        session_id="s1",
        run_id="r1",
        turn_id="t1",
        parent_callable="orchestrator_agent",
        target_callable="qa_agent",
        payload={"goal": "release"},
    )
    signer = EnvelopeSigner(
        "new-secret",
        require_signature=True,
        key_id="2026-04",
        verification_keys=["2026-03=old-secret"],
    )
    tampered = signer.sign(envelope).model_copy(update={"key_id": "missing-key"})

    verdict = signer.verify(tampered)

    assert not verdict.ok
    assert verdict.reason == "unknown_key_id"


@pytest.mark.asyncio
async def test_inprocess_remote_worker_pool_invokes_with_verified_envelope() -> None:
    pool = InProcessRemoteWorkerPool(
        workers=2,
        signing_key="secret",
        signing_key_id="2026-04",
        require_signed_envelopes=True,
    )
    target = _FakeCallable()
    result, report = await pool.invoke(
        target=target,
        input_obj=_Input(task="run"),
        context=_context(),
        parent_callable="orchestrator_agent",
        attempt=1,
        worker_hint="alpha",
    )

    assert result.success
    assert report.verification.ok
    assert report.envelope.target_callable == "fake_tool"
    assert report.envelope.key_id == "2026-04"
    assert report.worker_id.startswith("remote-worker-")


@pytest.mark.asyncio
async def test_remote_worker_pool_requires_signature_key_when_enforced() -> None:
    pool = InProcessRemoteWorkerPool(
        workers=1,
        signing_key="",
        require_signed_envelopes=True,
    )
    with pytest.raises(ValueError, match="signing key is required"):
        await pool.invoke(
            target=_FakeCallable(),
            input_obj=_Input(task="run"),
            context=_context(),
            parent_callable="orchestrator_agent",
        )


def test_http_remote_worker_pool_requires_endpoint() -> None:
    with pytest.raises(ValueError, match="endpoint is required"):
        HttpRemoteWorkerPool(
            endpoint="",
            signing_key="secret",
            require_signed_envelopes=True,
        )


def test_http_remote_worker_pool_requires_complete_mtls_key_pair() -> None:
    with pytest.raises(ValueError, match="requires both client_cert_path and client_key_path"):
        HttpRemoteWorkerPool(
            endpoint="https://remote.example.com/invoke",
            signing_key="secret",
            require_signed_envelopes=True,
            client_cert_path="/tmp/client-cert.pem",
        )


@pytest.mark.asyncio
async def test_http_remote_worker_pool_invokes_with_network_transport() -> None:
    with _remote_http_server(
        signing_key="secret",
        signing_key_id="2026-04",
        auth_token="token123",
    ) as endpoint:
        pool = HttpRemoteWorkerPool(
            endpoint=endpoint,
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
            attempt=2,
            worker_hint="net-a",
        )

    assert result.success
    assert result.output is not None
    assert result.output.response == "http:ship:r1"
    assert report.worker_id == "http-worker-1"
    assert report.verification.ok
    assert report.envelope.attempt == 2
    assert report.envelope.key_id == "2026-04"


@pytest.mark.asyncio
async def test_http_remote_worker_pool_supports_rotated_server_verifier_keys() -> None:
    with _remote_http_server(
        signing_key="new-secret",
        signing_key_id="2026-04",
        verification_keys=["2026-03=old-secret"],
    ) as endpoint:
        pool = HttpRemoteWorkerPool(
            endpoint=endpoint,
            signing_key="old-secret",
            signing_key_id="2026-03",
            require_signed_envelopes=True,
            timeout_ms=5000,
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
async def test_http_remote_worker_pool_remote_failure_maps_to_error_result() -> None:
    with _remote_http_server(signing_key="secret", error_message="remote exploded") as endpoint:
        pool = HttpRemoteWorkerPool(
            endpoint=endpoint,
            signing_key="secret",
            require_signed_envelopes=True,
            timeout_ms=5000,
        )
        result, report = await pool.invoke(
            target=_FakeCallable(),
            input_obj=_Input(task="ship"),
            context=_context(),
            parent_callable="orchestrator_agent",
        )

    assert not result.success
    assert result.error is not None
    assert "remote exploded" in result.error.message
    assert report.verification.ok
