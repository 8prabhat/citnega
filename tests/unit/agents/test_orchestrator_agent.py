"""Unit tests for OrchestratorAgent retry/dependency/rollback behavior."""

from __future__ import annotations

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pydantic import BaseModel
import pytest

from citnega.packages.agents.core.orchestrator_agent import (
    OrchestrationStep,
    OrchestratorAgent,
    OrchestratorInput,
)
from citnega.packages.protocol.callables.context import CallContext
from citnega.packages.protocol.callables.interfaces import IInvocable
from citnega.packages.protocol.callables.results import InvokeResult
from citnega.packages.protocol.callables.types import CallableMetadata, CallablePolicy, CallableType
from citnega.packages.protocol.models.sessions import SessionConfig
from citnega.packages.runtime.events.emitter import EventEmitter
from citnega.packages.runtime.events.tracer import Tracer
from citnega.packages.runtime.policy.approval_manager import ApprovalManager
from citnega.packages.runtime.policy.enforcer import PolicyEnforcer
from citnega.packages.runtime.remote.envelopes import EnvelopeSigner, RemoteRunEnvelope
from citnega.packages.shared.errors import CallableError


class _TaskInput(BaseModel):
    task: str = ""
    working_dir: str = ""


class _TaskOutput(BaseModel):
    response: str


class _FakeCallable(IInvocable):
    callable_type = CallableType.TOOL
    input_schema = _TaskInput
    output_schema = _TaskOutput
    policy = CallablePolicy()

    def __init__(self, name: str, fail_times: int = 0) -> None:
        self.name = name
        self._fail_times = fail_times
        self.calls = 0

    async def invoke(self, input_obj: _TaskInput, context: CallContext) -> InvokeResult:
        self.calls += 1
        if self.calls <= self._fail_times:
            return InvokeResult.from_error(
                name=self.name,
                callable_type=self.callable_type,
                error=CallableError(f"{self.name} failed attempt {self.calls}"),
                duration_ms=1,
            )
        return InvokeResult.ok(
            name=self.name,
            callable_type=self.callable_type,
            output=_TaskOutput(response=f"{self.name} ok: {input_obj.task}"),
            duration_ms=1,
        )

    def get_metadata(self) -> CallableMetadata:
        return CallableMetadata(
            name=self.name,
            description=f"{self.name} description",
            callable_type=self.callable_type,
            input_schema_json=self.input_schema.model_json_schema(),
            output_schema_json=self.output_schema.model_json_schema(),
            policy=self.policy,
        )


def _context() -> CallContext:
    return CallContext(
        session_id="s1",
        run_id="r1",
        turn_id="t1",
        session_config=SessionConfig(
            session_id="s1",
            name="orchestrator-tests",
            framework="direct",
            default_model_id="x",
        ),
    )


def _make_agent() -> OrchestratorAgent:
    emitter = EventEmitter()
    enforcer = PolicyEnforcer(emitter, ApprovalManager())
    tracer = MagicMock(spec=Tracer)
    tracer.record = MagicMock()
    return OrchestratorAgent(policy_enforcer=enforcer, event_emitter=emitter, tracer=tracer)


@contextmanager
def _remote_http_server(*, signing_key: str):
    signer = EnvelopeSigner(signing_key, require_signature=True)

    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8")
            payload = json.loads(raw)
            envelope = RemoteRunEnvelope.model_validate(payload.get("envelope", {}))
            verification = signer.verify(envelope)
            response = {
                "worker_id": "http-worker-orchestrator",
                "verification": verification.model_dump(mode="json"),
                "duration_ms": 2,
                "result": {
                    "success": verification.ok,
                    "output": {"response": "remote orchestrator ok"},
                    "error": (
                        {"message": f"verification failed:{verification.reason}"}
                        if not verification.ok
                        else None
                    ),
                },
            }
            body = json.dumps(response, ensure_ascii=True).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

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


@pytest.mark.asyncio
async def test_orchestrator_executes_dependencies_with_retry() -> None:
    agent = _make_agent()
    prep = _FakeCallable("prep_tool")
    flaky_build = _FakeCallable("build_tool", fail_times=1)
    agent.sync_tool_registry({"prep_tool": prep, "build_tool": flaky_build})

    result = await agent.invoke(
        OrchestratorInput(
            goal="prepare and build",
            steps=[
                OrchestrationStep(step_id="step1", callable_name="prep_tool", task="prep workspace"),
                OrchestrationStep(
                    step_id="step2",
                    callable_name="build_tool",
                    task="build artifacts",
                    depends_on=["step1"],
                    retries=1,
                ),
            ],
            max_retries=0,
        ),
        _context(),
    )

    assert result.success
    out = result.output
    assert out.failed_steps == 0
    assert out.completed_steps == 2
    step2 = next(s for s in out.step_results if s.step_id == "step2")
    assert step2.status == "completed"
    assert step2.attempts == 2


@pytest.mark.asyncio
async def test_orchestrator_runs_rollbacks_after_failure() -> None:
    agent = _make_agent()
    prep = _FakeCallable("prep_tool")
    deploy_fail = _FakeCallable("deploy_tool", fail_times=10)
    cleanup = _FakeCallable("cleanup_tool")
    agent.sync_tool_registry(
        {"prep_tool": prep, "deploy_tool": deploy_fail, "cleanup_tool": cleanup}
    )

    result = await agent.invoke(
        OrchestratorInput(
            goal="deploy release",
            steps=[
                OrchestrationStep(
                    step_id="step1",
                    callable_name="prep_tool",
                    task="prepare release",
                    rollback_callable="cleanup_tool",
                    rollback_args={"task": "cleanup prepared assets"},
                ),
                OrchestrationStep(
                    step_id="step2",
                    callable_name="deploy_tool",
                    task="deploy now",
                    depends_on=["step1"],
                ),
            ],
            max_retries=0,
            rollback_on_failure=True,
            fail_fast=True,
        ),
        _context(),
    )

    assert result.success
    out = result.output
    assert out.failed_steps == 1
    assert any("rollback via 'cleanup_tool' succeeded" in a for a in out.rollback_actions)
    step1 = next(s for s in out.step_results if s.step_id == "step1")
    assert step1.status == "rolled_back"


@pytest.mark.asyncio
async def test_orchestrator_uses_nextgen_execution_engine_when_enabled() -> None:
    agent = _make_agent()
    repo_map = _FakeCallable("repo_map")
    qa_agent = _FakeCallable("qa_agent")
    agent.sync_tool_registry({"repo_map": repo_map, "qa_agent": qa_agent})

    with patch("citnega.packages.config.loaders.load_settings") as mock_settings:
        mock_settings.return_value = SimpleNamespace(
            nextgen=SimpleNamespace(execution_enabled=True)
        )
        result = await agent.invoke(
            OrchestratorInput(
                goal="review repo",
                steps=[
                    OrchestrationStep(step_id="step1", callable_name="repo_map", task="map repo"),
                    OrchestrationStep(step_id="step2", callable_name="qa_agent", task="review repo"),
                ],
                rollback_on_failure=False,
                fail_fast=True,
            ),
            _context(),
        )

    assert result.success
    out = result.output
    assert out.failed_steps == 0
    assert out.completed_steps == 2
    queue = agent._event_emitter.get_queue("r1")
    event_types = []
    while not queue.empty():
        event_types.append(type(queue.get_nowait()).__name__)
    assert "PlanCompiledEvent" in event_types
    assert "ExecutionBatchStartedEvent" in event_types


@pytest.mark.asyncio
async def test_orchestrator_remote_step_executes_with_signed_envelope() -> None:
    agent = _make_agent()
    remote_tool = _FakeCallable("remote_tool")
    agent.sync_tool_registry({"remote_tool": remote_tool})
    agent.configure_remote_execution(
        SimpleNamespace(
            enabled=True,
            worker_mode="inprocess",
            workers=2,
            require_signed_envelopes=True,
            envelope_signing_key="secret",
            simulate_latency_ms=0,
            allowed_callables=[],
        )
    )

    result = await agent.invoke(
        OrchestratorInput(
            goal="execute remotely",
            allow_remote=True,
            steps=[
                OrchestrationStep(
                    step_id="step1",
                    callable_name="remote_tool",
                    task="remote task",
                    execution_target="remote",
                )
            ],
            max_retries=0,
        ),
        _context(),
    )

    assert result.success
    out = result.output
    assert out.failed_steps == 0
    step = out.step_results[0]
    assert step.execution_target == "remote"
    assert step.worker_id.startswith("remote-worker-")
    assert step.envelope_id.startswith("env-")
    assert step.envelope_verified is True


@pytest.mark.asyncio
async def test_orchestrator_remote_step_fails_when_signature_key_missing() -> None:
    agent = _make_agent()
    remote_tool = _FakeCallable("remote_tool")
    agent.sync_tool_registry({"remote_tool": remote_tool})
    agent.configure_remote_execution(
        SimpleNamespace(
            enabled=True,
            worker_mode="inprocess",
            workers=1,
            require_signed_envelopes=True,
            envelope_signing_key="",
            simulate_latency_ms=0,
            allowed_callables=[],
        )
    )

    result = await agent.invoke(
        OrchestratorInput(
            goal="execute remotely",
            allow_remote=True,
            steps=[
                OrchestrationStep(
                    step_id="step1",
                    callable_name="remote_tool",
                    task="remote task",
                    execution_target="remote",
                )
            ],
            max_retries=0,
        ),
        _context(),
    )

    assert result.success
    out = result.output
    assert out.failed_steps == 1
    step = out.step_results[0]
    assert step.status == "failed"
    assert "signing key is required" in step.error


@pytest.mark.asyncio
async def test_orchestrator_remote_step_executes_with_http_worker_mode() -> None:
    with _remote_http_server(signing_key="secret") as endpoint:
        agent = _make_agent()
        remote_tool = _FakeCallable("remote_tool")
        agent.sync_tool_registry({"remote_tool": remote_tool})
        agent.configure_remote_execution(
            SimpleNamespace(
                enabled=True,
                worker_mode="http",
                workers=1,
                require_signed_envelopes=True,
                envelope_signing_key="secret",
                simulate_latency_ms=0,
                allowed_callables=[],
                http_endpoint=endpoint,
                request_timeout_ms=5000,
                auth_token="",
                verify_tls=True,
            )
        )

        result = await agent.invoke(
            OrchestratorInput(
                goal="execute remotely",
                allow_remote=True,
                steps=[
                    OrchestrationStep(
                        step_id="step1",
                        callable_name="remote_tool",
                        task="remote task",
                        execution_target="remote",
                    )
                ],
                max_retries=0,
            ),
            _context(),
        )

    assert result.success
    out = result.output
    assert out.failed_steps == 0
    step = out.step_results[0]
    assert step.execution_target == "remote"
    assert step.worker_id == "http-worker-orchestrator"
    assert step.envelope_id.startswith("env-")
    assert step.envelope_verified is True
