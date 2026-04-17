"""Soak coverage for repeated remote orchestration paths."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

from pydantic import BaseModel
import pytest

from citnega.packages.agents.core.orchestrator_agent import (
    OrchestrationStep,
    OrchestratorAgent,
    OrchestratorInput,
)
from citnega.packages.protocol.callables.context import CallContext
from citnega.packages.protocol.callables.results import InvokeResult
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.protocol.models.sessions import SessionConfig
from citnega.packages.runtime.events.emitter import EventEmitter
from citnega.packages.runtime.events.tracer import Tracer
from citnega.packages.runtime.policy.approval_manager import ApprovalManager
from citnega.packages.runtime.policy.enforcer import PolicyEnforcer
from citnega.packages.runtime.remote.service import RemoteWorkerHTTPService
from citnega.packages.shared.errors import CallableError


class _RemoteInput(BaseModel):
    task: str = ""


class _RemoteOutput(BaseModel):
    response: str


class _FlakyRemoteCallable:
    name = "remote_tool"
    callable_type = CallableType.TOOL
    input_schema = _RemoteInput
    output_schema = _RemoteOutput

    def __init__(self, *, fail_on_calls: set[int] | None = None, delay_ms: int = 0) -> None:
        self._fail_on_calls = set(fail_on_calls or set())
        self._delay_ms = max(0, int(delay_ms))
        self.calls = 0

    async def invoke(self, input_obj: _RemoteInput, context: CallContext) -> InvokeResult:
        self.calls += 1
        if self._delay_ms:
            await asyncio.sleep(self._delay_ms / 1000.0)
        if self.calls in self._fail_on_calls:
            return InvokeResult.from_error(
                name=self.name,
                callable_type=self.callable_type,
                error=CallableError(f"remote failure injected on call {self.calls}"),
                duration_ms=1,
            )
        return InvokeResult.ok(
            name=self.name,
            callable_type=self.callable_type,
            output=_RemoteOutput(response=f"remote-ok:{input_obj.task}:{context.run_id}"),
            duration_ms=1,
        )


def _make_orchestrator() -> OrchestratorAgent:
    emitter = EventEmitter()
    enforcer = PolicyEnforcer(emitter, ApprovalManager())
    tracer = MagicMock(spec=Tracer)
    tracer.record = MagicMock()
    return OrchestratorAgent(policy_enforcer=enforcer, event_emitter=emitter, tracer=tracer)


def _context(run_id: str) -> CallContext:
    return CallContext(
        session_id="soak-s1",
        run_id=run_id,
        turn_id=f"{run_id}-t1",
        session_config=SessionConfig(
            session_id="soak-s1",
            name="remote-soak",
            framework="direct",
            default_model_id="x",
        ),
    )


def _configure_remote_http(
    agent: OrchestratorAgent,
    *,
    endpoint: str,
    timeout_ms: int,
) -> None:
    agent.configure_remote_execution(
        SimpleNamespace(
            enabled=True,
            worker_mode="http",
            workers=1,
            require_signed_envelopes=True,
            envelope_signing_key="secret",
            simulate_latency_ms=0,
            allowed_callables=["remote_tool"],
            http_endpoint=f"{endpoint}/invoke",
            request_timeout_ms=timeout_ms,
            auth_token="token123",
            verify_tls=True,
        )
    )


@pytest.mark.asyncio
async def test_remote_http_soak_retries_with_failure_injection() -> None:
    remote_tool = _FlakyRemoteCallable(fail_on_calls={1, 5, 9, 13, 17})
    service = RemoteWorkerHTTPService(
        registry={"remote_tool": remote_tool},
        signing_key="secret",
        allowed_callables=["remote_tool"],
        require_signed_envelopes=True,
        auth_token="token123",
        worker_id="soak-worker-1",
        isolation_profile="process",
    )
    agent = _make_orchestrator()
    agent.sync_tool_registry({"remote_tool": remote_tool})

    with service.serve_in_thread() as base_url:
        _configure_remote_http(agent, endpoint=base_url, timeout_ms=5000)

        for idx in range(1, 13):
            result = await agent.invoke(
                OrchestratorInput(
                    goal="remote soak retry",
                    allow_remote=True,
                    steps=[
                        OrchestrationStep(
                            step_id="step1",
                            callable_name="remote_tool",
                            task=f"task-{idx}",
                            execution_target="remote",
                            retries=1,
                        )
                    ],
                    max_retries=0,
                ),
                _context(f"retry-run-{idx}"),
            )

            assert result.success
            assert result.output.failed_steps == 0
            step = result.output.step_results[0]
            assert step.status == "completed"
            assert step.worker_id == "soak-worker-1"
            assert step.envelope_verified is True

    assert remote_tool.calls >= 12


@pytest.mark.asyncio
async def test_remote_http_soak_timeout_recovery_after_cancel_style_failure() -> None:
    remote_tool = _FlakyRemoteCallable(delay_ms=150)
    service = RemoteWorkerHTTPService(
        registry={"remote_tool": remote_tool},
        signing_key="secret",
        allowed_callables=["remote_tool"],
        require_signed_envelopes=True,
        auth_token="token123",
        worker_id="soak-worker-2",
        isolation_profile="process",
    )
    agent = _make_orchestrator()
    agent.sync_tool_registry({"remote_tool": remote_tool})

    with service.serve_in_thread() as base_url:
        _configure_remote_http(agent, endpoint=base_url, timeout_ms=20)
        timed_out = await agent.invoke(
            OrchestratorInput(
                goal="remote soak timeout",
                allow_remote=True,
                steps=[
                    OrchestrationStep(
                        step_id="step1",
                        callable_name="remote_tool",
                        task="timeout-task",
                        execution_target="remote",
                    )
                ],
                max_retries=0,
            ),
            _context("timeout-run"),
        )

        assert timed_out.success
        assert timed_out.output.failed_steps == 1
        assert "timed out" in timed_out.output.step_results[0].error.lower()

        # Let the timed-out server-side invocation drain before the recovery loop.
        await asyncio.sleep(0.25)

        _configure_remote_http(agent, endpoint=base_url, timeout_ms=1000)
        for idx in range(1, 9):
            recovered = await agent.invoke(
                OrchestratorInput(
                    goal="remote soak recovery",
                    allow_remote=True,
                    steps=[
                        OrchestrationStep(
                            step_id="step1",
                            callable_name="remote_tool",
                            task=f"recovery-{idx}",
                            execution_target="remote",
                        )
                    ],
                    max_retries=0,
                ),
                _context(f"recovery-run-{idx}"),
            )

            assert recovered.success
            assert recovered.output.failed_steps == 0
            assert recovered.output.step_results[0].status == "completed"
