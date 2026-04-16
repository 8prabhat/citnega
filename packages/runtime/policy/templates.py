"""Policy templates for environment-specific runtime hardening."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from citnega.packages.config.settings import PolicySettings


_MUTATING_TOOL_NAMES = {
    "write_file",
    "edit_file",
    "run_shell",
    "git_ops",
    "write_kb",
    "artifact_pack",
}

_NETWORK_TOOL_NAMES = {
    "fetch_url",
    "search_web",
    "read_webpage",
}

_FILE_TOOL_NAMES = {
    "read_file",
    "write_file",
    "edit_file",
    "list_dir",
    "search_files",
}


@dataclass(frozen=True)
class EffectivePolicyTemplate:
    template_name: str
    enforce_network_deny: bool
    require_approval_tools: frozenset[str]
    enforce_workspace_bounds: bool


def resolve_policy_template(policy: PolicySettings) -> EffectivePolicyTemplate:
    """
    Resolve the effective policy behavior from policy settings.

    Supported templates:
      - dev: permissive defaults for local iteration
      - team: approval required for mutating tools
      - locked_down: deny network, enforce workspace bounds, and require approval
        for mutating and network tools
    """
    template = _normalise_template_name(getattr(policy, "template", "dev"))

    enforce_network_deny = bool(getattr(policy, "enforce_network_deny", False))
    enforce_workspace_bounds = bool(getattr(policy, "enforce_workspace_bounds", False))
    require_approval_tools: set[str] = set(getattr(policy, "require_approval_tools", []))

    if template == "team":
        require_approval_tools.update(_MUTATING_TOOL_NAMES)
    elif template == "locked_down":
        enforce_network_deny = True
        enforce_workspace_bounds = True
        require_approval_tools.update(_MUTATING_TOOL_NAMES)
        require_approval_tools.update(_NETWORK_TOOL_NAMES)

    return EffectivePolicyTemplate(
        template_name=template,
        enforce_network_deny=enforce_network_deny,
        require_approval_tools=frozenset(require_approval_tools),
        enforce_workspace_bounds=enforce_workspace_bounds,
    )


def apply_policy_template_to_tools(
    tools: dict[str, object],
    effective: EffectivePolicyTemplate,
    *,
    workspace_root: str,
    app_home: Path,
) -> None:
    """
    Mutate tool policies in-place according to the resolved policy template.

    This function is intentionally conservative:
      - only tightens restrictions (approval/path allowlist)
      - does not disable or remove tools
    """
    allowed_roots = [workspace_root, str(app_home)]

    for name, tool in tools.items():
        policy = getattr(tool, "policy", None)
        if policy is None:
            continue

        updates: dict[str, object] = {}

        if name in effective.require_approval_tools and not getattr(policy, "requires_approval", False):
            updates["requires_approval"] = True

        if effective.enforce_workspace_bounds and name in _FILE_TOOL_NAMES:
            existing = list(getattr(policy, "allowed_paths", []) or [])
            if existing:
                merged = list(dict.fromkeys(existing + allowed_roots))
            else:
                merged = list(dict.fromkeys(allowed_roots))
            updates["allowed_paths"] = merged

        if updates:
            tool.policy = policy.model_copy(update=updates)


def _normalise_template_name(value: str) -> str:
    normalised = value.strip().lower().replace("-", "_")
    if normalised in {"dev", "team", "locked_down"}:
        return normalised
    return "dev"
