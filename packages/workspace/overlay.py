"""Helpers for loading custom workspace callables with override precedence."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from citnega.packages.workspace.loader import DynamicLoader, WorkspaceLoadResult
from citnega.packages.workspace.onboarding import enforce_workspace_onboarding
from citnega.packages.workspace.writer import WorkspaceWriter

if TYPE_CHECKING:
    from citnega.packages.config.settings import WorkspaceSettings
    from citnega.packages.protocol.callables.interfaces import IInvocable

logger = logging.getLogger(__name__)


def resolve_workfolder_path(path: str | Path | None) -> Path | None:
    """Return an absolute workfolder path, or ``None`` when unset."""
    if path is None:
        return None
    raw = str(path).strip()
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def load_workspace_overlay(
    workfolder: Path | None,
    *,
    enforcer,
    emitter,
    tracer,
    tool_registry: dict[str, IInvocable],
    workspace_settings: WorkspaceSettings,
) -> WorkspaceLoadResult:
    """
    Load custom tools, agents, and workflows from ``workfolder``.

    Workfolder callables are loaded in dependency order so that a custom tool
    can override a built-in tool before custom agents or workflows are
    instantiated.
    """
    if workfolder is None:
        return WorkspaceLoadResult(tools={}, agents={}, workflows={})

    writer = WorkspaceWriter(workfolder)
    writer.ensure_dirs()
    report = enforce_workspace_onboarding(writer.root, workspace_settings)
    for warning in report.warnings:
        logger.warning("workspace_onboarding_warning: %s", warning)

    loader = DynamicLoader(
        enforcer=enforcer,
        emitter=emitter,
        tracer=tracer,
        tool_registry=tool_registry,
    )
    return loader.load_workspace(writer)
