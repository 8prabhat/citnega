"""
ToolRegistry — factory that creates and returns all registered tool instances.

Usage in bootstrap::

    registry = ToolRegistry(
        enforcer=policy_enforcer,
        emitter=event_emitter,
        tracer=tracer,
        kb_store=kb_store,          # optional — for read_kb tool
    )
    tools: dict[str, IInvocable] = registry.build_all()

Following DIP: bootstrap code depends on this abstraction, not on concrete
tool imports scattered across files.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.interfaces import IInvocable
    from citnega.packages.protocol.interfaces.events import IEventEmitter, ITracer
    from citnega.packages.protocol.interfaces.knowledge_store import IKnowledgeStore
    from citnega.packages.protocol.interfaces.policy import IPolicyEnforcer
    from citnega.packages.storage.path_resolver import PathResolver


class ToolRegistry:
    """
    Single source of truth for built-in tool instantiation.

    All tools receive the same injected infrastructure (enforcer, emitter,
    tracer).  Adding a new tool means adding it here and nowhere else (OCP).
    """

    def __init__(
        self,
        enforcer: IPolicyEnforcer,
        emitter: IEventEmitter,
        tracer: ITracer,
        path_resolver: PathResolver | None = None,
        kb_store: IKnowledgeStore | None = None,
    ) -> None:
        self._enforcer = enforcer
        self._emitter = emitter
        self._tracer = tracer
        self._path_resolver = path_resolver
        self._kb_store = kb_store

    def build_all(self) -> dict[str, IInvocable]:
        """Instantiate every built-in tool and return as name→instance dict."""
        tools: dict[str, IInvocable] = {}
        for tool in self._create_tools():
            tools[tool.name] = tool
        return tools

    # ── Private: create one instance per tool ────────────────────────────────

    def _deps(self):
        """Return the three common constructor args."""
        return self._enforcer, self._emitter, self._tracer

    def _create_tools(self) -> list[IInvocable]:
        from citnega.packages.tools.builtin.fetch_url import FetchURLTool
        from citnega.packages.tools.builtin.list_dir import ListDirTool
        from citnega.packages.tools.builtin.read_file import ReadFileTool
        from citnega.packages.tools.builtin.run_shell import RunShellTool
        from citnega.packages.tools.builtin.search_files import SearchFilesTool
        from citnega.packages.tools.builtin.search_web import SearchWebTool
        from citnega.packages.tools.builtin.summarize_text import SummarizeTextTool

        instances: list[IInvocable] = [
            ReadFileTool(*self._deps()),
            ListDirTool(*self._deps()),
            SearchFilesTool(*self._deps()),
            FetchURLTool(*self._deps()),
            SearchWebTool(*self._deps()),
            RunShellTool(*self._deps()),
            SummarizeTextTool(*self._deps()),
        ]

        # read_kb requires the KB store
        if self._kb_store is not None:
            from citnega.packages.tools.builtin.read_kb import ReadKBTool

            instances.append(ReadKBTool(*self._deps(), knowledge_store=self._kb_store))

        return instances
