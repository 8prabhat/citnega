"""Unit tests for policy environment templates."""

from __future__ import annotations

from pathlib import Path

from citnega.packages.config.settings import PolicySettings
from citnega.packages.protocol.callables.types import CallablePolicy
from citnega.packages.runtime.policy.templates import (
    apply_policy_template_to_tools,
    resolve_policy_template,
)


class _FakeTool:
    def __init__(self, **policy_kwargs):
        self.policy = CallablePolicy(**policy_kwargs)


def test_resolve_team_template_requires_mutation_approvals() -> None:
    effective = resolve_policy_template(PolicySettings(template="team"))

    assert effective.template_name == "team"
    assert effective.enforce_network_deny is False
    assert "write_file" in effective.require_approval_tools
    assert "run_shell" in effective.require_approval_tools


def test_resolve_locked_down_template_enforces_network_and_workspace_bounds() -> None:
    effective = resolve_policy_template(PolicySettings(template="locked_down"))

    assert effective.template_name == "locked_down"
    assert effective.enforce_network_deny is True
    assert effective.enforce_workspace_bounds is True
    assert "fetch_url" in effective.require_approval_tools


def test_apply_template_mutates_tool_policies() -> None:
    tools = {
        "read_file": _FakeTool(requires_approval=False, allowed_paths=[]),
        "write_file": _FakeTool(requires_approval=False, allowed_paths=[]),
        "run_shell": _FakeTool(requires_approval=False),
    }
    effective = resolve_policy_template(
        PolicySettings(
            template="team",
            enforce_workspace_bounds=True,
        )
    )

    apply_policy_template_to_tools(
        tools,
        effective,
        workspace_root="/tmp/workspace",
        app_home=Path("/tmp/app_home"),
    )

    assert tools["write_file"].policy.requires_approval is True
    assert tools["run_shell"].policy.requires_approval is True
    assert "/tmp/workspace" in tools["read_file"].policy.allowed_paths
    assert "/tmp/app_home" in tools["read_file"].policy.allowed_paths
