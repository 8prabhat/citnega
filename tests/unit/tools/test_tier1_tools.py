"""
Unit tests for Batch 3 tier-1 integration tools.

Each test covers the "missing env/dep → graceful message" contract so CI passes
without cloud credentials, browsers, or mmdc installed.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from citnega.packages.protocol.callables.context import CallContext
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.protocol.models.sessions import SessionConfig
from citnega.packages.runtime.events.emitter import EventEmitter
from citnega.packages.runtime.events.tracer import Tracer
from citnega.packages.runtime.policy.approval_manager import ApprovalManager
from citnega.packages.runtime.policy.enforcer import PolicyEnforcer


def _deps():
    emitter = EventEmitter()
    mgr = ApprovalManager()
    enforcer = PolicyEnforcer(emitter, mgr)
    tracer = MagicMock(spec=Tracer)
    tracer.record = MagicMock()
    return enforcer, emitter, tracer


def _make_tool(cls):
    enforcer, emitter, tracer = _deps()
    return cls(policy_enforcer=enforcer, event_emitter=emitter, tracer=tracer)


def _context():
    return CallContext(
        session_id="test",
        run_id="r1",
        turn_id="t1",
        session_config=SessionConfig(
            session_id="test", name="test", framework="stub", default_model_id="x"
        ),
    )


# ── Contract: each tool has name, description, callable_type, input/output schema ──

class TestToolContracts:
    def test_browser_session_contract(self):
        from citnega.packages.tools.builtin.browser_session import BrowserSessionTool
        t = _make_tool(BrowserSessionTool)
        assert t.name == "browser_session"
        assert t.callable_type == CallableType.TOOL
        assert t.input_schema is not None
        assert t.output_schema is not None

    def test_mermaid_render_contract(self):
        from citnega.packages.tools.builtin.mermaid_render import MermaidRenderTool
        t = _make_tool(MermaidRenderTool)
        assert t.name == "mermaid_render"
        assert t.callable_type == CallableType.TOOL

    def test_jira_ops_contract(self):
        from citnega.packages.tools.builtin.jira_ops import JiraOpsTool
        t = _make_tool(JiraOpsTool)
        assert t.name == "jira_ops"
        assert t.callable_type == CallableType.TOOL

    def test_github_ops_contract(self):
        from citnega.packages.tools.builtin.github_ops import GitHubOpsTool
        t = _make_tool(GitHubOpsTool)
        assert t.name == "github_ops"
        assert t.callable_type == CallableType.TOOL

    def test_vault_secret_contract(self):
        from citnega.packages.tools.builtin.vault_secret import VaultSecretTool
        t = _make_tool(VaultSecretTool)
        assert t.name == "vault_secret"
        assert t.callable_type == CallableType.TOOL

    def test_cloud_ops_contract(self):
        from citnega.packages.tools.builtin.cloud_ops import CloudOpsTool
        t = _make_tool(CloudOpsTool)
        assert t.name == "cloud_ops"
        assert t.callable_type == CallableType.TOOL

    def test_email_reader_contract(self):
        from citnega.packages.tools.builtin.email_reader import EmailReaderTool
        t = _make_tool(EmailReaderTool)
        assert t.name == "email_reader"
        assert t.callable_type == CallableType.TOOL

    def test_calendar_query_contract(self):
        from citnega.packages.tools.builtin.calendar_query import CalendarQueryTool
        t = _make_tool(CalendarQueryTool)
        assert t.name == "calendar_query"
        assert t.callable_type == CallableType.TOOL

    def test_prometheus_query_contract(self):
        from citnega.packages.tools.builtin.prometheus_query import PrometheusQueryTool
        t = _make_tool(PrometheusQueryTool)
        assert t.name == "prometheus_query"
        assert t.callable_type == CallableType.TOOL

    def test_linear_ops_contract(self):
        from citnega.packages.tools.builtin.linear_ops import LinearOpsTool
        t = _make_tool(LinearOpsTool)
        assert t.name == "linear_ops"
        assert t.callable_type == CallableType.TOOL

    def test_agent_delegate_contract(self):
        from citnega.packages.tools.builtin.agent_delegate import AgentDelegateTool
        t = _make_tool(AgentDelegateTool)
        assert t.name == "agent_delegate"
        assert t.callable_type == CallableType.TOOL


# ── Graceful missing-env / missing-dep tests ──────────────────────────────────

@pytest.mark.asyncio
async def test_jira_ops_missing_env_returns_graceful_message():
    from citnega.packages.tools.builtin.jira_ops import JiraOpsTool, JiraOpsInput
    t = _make_tool(JiraOpsTool)
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("JIRA_URL", None)
        os.environ.pop("JIRA_TOKEN", None)
        result = await t._execute(JiraOpsInput(operation="get", issue_key="TEST-1"), _context())
    assert "JIRA_URL" in result.result or "JIRA_TOKEN" in result.result


@pytest.mark.asyncio
async def test_github_ops_missing_token_returns_graceful_message():
    from citnega.packages.tools.builtin.github_ops import GitHubOpsTool, GitHubOpsInput
    t = _make_tool(GitHubOpsTool)
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("GITHUB_TOKEN", None)
        result = await t._execute(
            GitHubOpsInput(operation="list_prs", owner="foo", repo="bar"), _context()
        )
    assert "GITHUB_TOKEN" in result.result


@pytest.mark.asyncio
async def test_vault_secret_env_backend_reads_os_environ(monkeypatch):
    from citnega.packages.tools.builtin.vault_secret import VaultSecretTool, VaultSecretInput
    monkeypatch.setenv("MY_SECRET_KEY", "supersecretvalue")
    monkeypatch.delenv("VAULT_ADDR", raising=False)
    t = _make_tool(VaultSecretTool)
    result = await t._execute(
        VaultSecretInput(secret_path="MY_SECRET_KEY", backend="env"), _context()
    )
    assert "supe****" in result.result or "MY_SECRET_KEY" in result.result


@pytest.mark.asyncio
async def test_vault_secret_env_missing_key_returns_graceful_message(monkeypatch):
    from citnega.packages.tools.builtin.vault_secret import VaultSecretTool, VaultSecretInput
    monkeypatch.delenv("NONEXISTENT_KEY_XYZ", raising=False)
    monkeypatch.delenv("VAULT_ADDR", raising=False)
    t = _make_tool(VaultSecretTool)
    result = await t._execute(
        VaultSecretInput(secret_path="NONEXISTENT_KEY_XYZ", backend="env"), _context()
    )
    assert "not set" in result.result


@pytest.mark.asyncio
async def test_cloud_ops_missing_boto3_returns_graceful_message():
    from citnega.packages.tools.builtin.cloud_ops import CloudOpsTool, CloudOpsInput
    t = _make_tool(CloudOpsTool)
    with patch.dict("sys.modules", {"boto3": None}):
        result = await t._execute(
            CloudOpsInput(provider="aws", operation="list_resources", resource_type="ec2"),
            _context(),
        )
    assert "boto3" in result.result or "aws" in result.result.lower()


@pytest.mark.asyncio
async def test_cloud_ops_unknown_provider_returns_graceful_message():
    from citnega.packages.tools.builtin.cloud_ops import CloudOpsTool, CloudOpsInput
    t = _make_tool(CloudOpsTool)
    result = await t._execute(
        CloudOpsInput(provider="unknown_cloud", operation="list_resources"), _context()
    )
    assert "unknown provider" in result.result


@pytest.mark.asyncio
async def test_email_reader_missing_env_returns_graceful_message(monkeypatch):
    from citnega.packages.tools.builtin.email_reader import EmailReaderTool, EmailReaderInput
    monkeypatch.delenv("EMAIL_HOST", raising=False)
    monkeypatch.delenv("EMAIL_USER", raising=False)
    monkeypatch.delenv("EMAIL_PASSWORD", raising=False)
    t = _make_tool(EmailReaderTool)
    result = await t._execute(EmailReaderInput(action="search", query="ALL"), _context())
    assert "EMAIL_HOST" in result.result


@pytest.mark.asyncio
async def test_calendar_query_missing_google_sdk_returns_graceful_message():
    from citnega.packages.tools.builtin.calendar_query import CalendarQueryTool, CalendarQueryInput
    t = _make_tool(CalendarQueryTool)
    with patch.dict("sys.modules", {"googleapiclient": None, "googleapiclient.discovery": None}):
        result = await t._execute(
            CalendarQueryInput(action="list_events", start_date="2024-01-01", end_date="2024-01-31"),
            _context(),
        )
    assert "google" in result.result.lower() or "install" in result.result.lower()


@pytest.mark.asyncio
async def test_linear_ops_missing_api_key_returns_graceful_message(monkeypatch):
    from citnega.packages.tools.builtin.linear_ops import LinearOpsTool, LinearOpsInput
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    t = _make_tool(LinearOpsTool)
    result = await t._execute(LinearOpsInput(operation="list_issues"), _context())
    assert "LINEAR_API_KEY" in result.result


@pytest.mark.asyncio
async def test_mermaid_render_empty_diagram_returns_graceful_message():
    from citnega.packages.tools.builtin.mermaid_render import MermaidRenderTool, MermaidRenderInput
    t = _make_tool(MermaidRenderTool)
    result = await t._execute(MermaidRenderInput(diagram_text=""), _context())
    assert "empty" in result.result


@pytest.mark.asyncio
async def test_agent_delegate_no_sub_callables_returns_graceful_message():
    from citnega.packages.tools.builtin.agent_delegate import AgentDelegateTool, AgentDelegateInput
    t = _make_tool(AgentDelegateTool)
    ctx = _context()
    result = await t._execute(AgentDelegateInput(agent_name="hr_agent", task="help"), ctx)
    assert "not found" in result.result


# ── Registry registration test ────────────────────────────────────────────────

def test_all_tier1_tools_registered_in_registry():
    from unittest.mock import MagicMock
    from citnega.packages.tools.registry import ToolRegistry

    emitter = EventEmitter()
    mgr = ApprovalManager()
    enforcer = PolicyEnforcer(emitter, mgr)
    tracer = MagicMock(spec=Tracer)
    tracer.record = MagicMock()

    registry = ToolRegistry(enforcer=enforcer, emitter=emitter, tracer=tracer)
    tools = registry.build_all()

    expected = {
        "browser_session", "mermaid_render", "jira_ops", "github_ops",
        "vault_secret", "cloud_ops", "email_reader", "calendar_query",
        "prometheus_query", "linear_ops", "agent_delegate",
    }
    missing = expected - set(tools.keys())
    assert not missing, f"Missing tools in registry: {missing}"
