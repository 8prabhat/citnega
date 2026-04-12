"""
DynamicLoader — hot-loads Python files from a workfolder into live callables.

For each .py file in agents/, tools/, and workflows/ the loader:
  1. Imports the module via importlib (no sys.path mutation).
  2. Scans module globals for subclasses of BaseCallable that are not base
     classes themselves.
  3. Instantiates each discovered class with the injected dependencies.
  4. Returns a dict mapping callable name → instance.

Errors in individual files are caught, logged as warnings, and skipped —
a broken file never prevents other files from loading.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.util
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path
    import types

    from citnega.packages.protocol.callables.interfaces import IInvocable
    from citnega.packages.workspace.writer import WorkspaceWriter

logger = logging.getLogger(__name__)

# Base classes that should never be instantiated by the loader
_BASE_CLASS_NAMES = frozenset(
    {
        "BaseCallable",
        "BaseCoreAgent",
        "SpecialistBase",
    }
)


@dataclass(frozen=True)
class WorkspaceLoadResult:
    tools: dict[str, IInvocable]
    agents: dict[str, IInvocable]
    workflows: dict[str, IInvocable]

    @property
    def callables(self) -> dict[str, IInvocable]:
        return {**self.tools, **self.agents, **self.workflows}

    def ordered_items(self) -> list[tuple[str, IInvocable]]:
        return [
            *self.tools.items(),
            *self.agents.items(),
            *self.workflows.items(),
        ]


class DynamicLoader:
    """
    Scans a directory tree for BaseCallable subclasses and instantiates them.

    Args:
        enforcer:      IPolicyEnforcer (injected by bootstrap)
        emitter:       IEventEmitter   (injected by bootstrap)
        tracer:        ITracer         (injected by bootstrap)
        tool_registry: Mapping of tool name → callable, passed to agent/workflow ctors.
    """

    def __init__(
        self,
        enforcer,
        emitter,
        tracer,
        tool_registry: dict[str, IInvocable] | None = None,
    ) -> None:
        self._enforcer = enforcer
        self._emitter = emitter
        self._tracer = tracer
        self._tool_registry = tool_registry or {}

    # ── Public API ─────────────────────────────────────────────────────────────

    def load_directory(self, path: Path) -> dict[str, IInvocable]:
        """
        Load all .py files in ``path`` (non-recursive).

        Returns a mapping of callable.name → instantiated callable.
        Files that fail to import or contain no callables are silently skipped.
        """
        result: dict[str, IInvocable] = {}
        if not path.is_dir():
            return result

        for py_file in sorted(path.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            try:
                loaded = self._load_file(py_file)
                result.update(loaded)
            except Exception as exc:
                logger.warning("DynamicLoader: skipping %s — %s", py_file, exc)

        return result

    def load_workfolder(self, writer: WorkspaceWriter) -> dict[str, IInvocable]:
        """
        Load all three subdirectories (agents, tools, workflows).

        Returns merged dict of all discovered callables.
        """
        return self.load_workspace(writer).callables

    def load_workspace(self, writer: WorkspaceWriter) -> WorkspaceLoadResult:
        """
        Load a workspace in dependency order.

        Custom tools are loaded first so custom agents and workflows receive
        the final tool registry with workfolder overrides already applied.
        """
        from citnega.packages.workspace.writer import WorkspaceWriter

        assert isinstance(writer, WorkspaceWriter)
        writer.ensure_dirs()

        tools = self.load_directory(writer.tools_dir)
        merged_tools = {**self._tool_registry, **tools}
        downstream_loader = DynamicLoader(
            self._enforcer,
            self._emitter,
            self._tracer,
            tool_registry=merged_tools,
        )
        agents = downstream_loader.load_directory(writer.agents_dir)
        workflows = downstream_loader.load_directory(writer.workflows_dir)
        return WorkspaceLoadResult(tools=tools, agents=agents, workflows=workflows)

    # ── Internals ──────────────────────────────────────────────────────────────

    def _load_file(self, path: Path) -> dict[str, IInvocable]:
        """Import one .py file and return all BaseCallable subclasses found."""
        module = self._import_module(path)
        return self._extract_callables(module)

    @staticmethod
    def _import_module(path: Path) -> types.ModuleType:
        """Import a file by path without mutating sys.path."""
        digest = hashlib.sha1(str(path.resolve()).encode("utf-8")).hexdigest()[:12]
        module_name = f"_citnega_workspace_{path.parent.name}_{path.stem}_{digest}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot create module spec for {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        return module

    def _extract_callables(self, module: types.ModuleType) -> dict[str, IInvocable]:
        """Scan module globals for instantiable BaseCallable subclasses."""
        from citnega.packages.protocol.callables.base import BaseCallable

        result: dict[str, IInvocable] = {}
        for _attr_name, obj in vars(module).items():
            if (
                isinstance(obj, type)
                and issubclass(obj, BaseCallable)
                and obj.__name__ not in _BASE_CLASS_NAMES
                and obj is not BaseCallable
            ):
                try:
                    instance = self._instantiate(obj)
                    result[instance.name] = instance
                except Exception as exc:
                    logger.warning(
                        "DynamicLoader: could not instantiate %s — %s", obj.__name__, exc
                    )
        return result

    def _instantiate(self, cls: type) -> IInvocable:
        """Instantiate a callable class with the injected dependencies."""
        from citnega.packages.agents.specialists._specialist_base import (
            SpecialistBase,
        )
        from citnega.packages.protocol.callables.base import BaseCoreAgent

        if issubclass(cls, (SpecialistBase, BaseCoreAgent)):
            return cls(self._enforcer, self._emitter, self._tracer, self._tool_registry)
        return cls(self._enforcer, self._emitter, self._tracer)
