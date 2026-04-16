"""
AgentRegistry — factory that creates and returns all registered agent instances.

Usage in bootstrap::

    registry = AgentRegistry(
        enforcer=policy_enforcer,
        emitter=event_emitter,
        tracer=tracer,
        tools=tool_dict,       # dict[str, IInvocable] from ToolRegistry
    )
    agents: dict[str, IInvocable] = registry.build_all()

Following DIP — bootstrap depends on this abstraction, not on imports
scattered across agent modules.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.base import BaseCallable
    from citnega.packages.protocol.callables.interfaces import IInvocable
    from citnega.packages.protocol.interfaces.events import IEventEmitter, ITracer
    from citnega.packages.protocol.interfaces.policy import IPolicyEnforcer


class AgentRegistry:
    """
    Single source of truth for agent instantiation.

    Agents that need tools receive a filtered tool_registry (only the tools
    listed in their TOOL_WHITELIST or agents.yaml config).
    """

    def __init__(
        self,
        enforcer: IPolicyEnforcer,
        emitter: IEventEmitter,
        tracer: ITracer,
        tools: dict[str, IInvocable] | None = None,
    ) -> None:
        self._enforcer = enforcer
        self._emitter = emitter
        self._tracer = tracer
        self._tools = tools or {}

    def build_all(self) -> dict[str, IInvocable]:
        """Instantiate every registered agent and return as name→instance dict."""
        agents: dict[str, IInvocable] = {}
        for agent in self._create_agents():
            agents[agent.name] = agent
        self.wire_core_agents(agents, self._tools)
        return agents

    @staticmethod
    def wire_core_agents(
        agents: dict[str, IInvocable],
        tools: dict[str, IInvocable] | None = None,
    ) -> None:
        from citnega.packages.protocol.callables.base import BaseCoreAgent
        from citnega.packages.protocol.callables.types import CallableType

        core_agents = [
            a for a in agents.values() if getattr(a, "callable_type", None) == CallableType.CORE
        ]
        non_core = [
            a for a in agents.values() if getattr(a, "callable_type", None) != CallableType.CORE
        ]

        for agent in core_agents:
            if isinstance(agent, BaseCoreAgent):
                agent.sync_tool_registry(tools or {})
                # Give every CORE agent access to: all non-CORE agents + all other CORE agents
                # This lets ConversationAgent call RouterAgent, and RouterAgent know the specialists.
                peers = non_core + [a for a in core_agents if a.name != agent.name]
                agent.sync_sub_callables(peers)

    # ── Private ───────────────────────────────────────────────────────────────

    def _make(self, cls: type[BaseCallable]) -> IInvocable:
        """Create an agent instance with standard injected deps + tools."""
        return cls(self._enforcer, self._emitter, self._tracer, self._tools)

    def _create_agents(self) -> list[IInvocable]:
        # ── Core agents ───────────────────────────────────────────────────────
        # ── Existing core agents ──────────────────────────────────────────────
        from citnega.packages.agents.core.conversation_agent import (
            ConversationAgent,
        )
        from citnega.packages.agents.core.orchestrator_agent import OrchestratorAgent
        from citnega.packages.agents.core.planner_agent import PlannerAgent
        from citnega.packages.agents.core.reasoning import ReasoningAgent
        from citnega.packages.agents.core.retriever import RetrieverAgent
        from citnega.packages.agents.core.router import RouterAgent
        from citnega.packages.agents.core.tool_executor import ToolExecutorAgent
        from citnega.packages.agents.core.validator import ValidatorAgent
        from citnega.packages.agents.core.writer import WriterAgent

        # ── Domain specialists ────────────────────────────────────────────────
        from citnega.packages.agents.domain import ALL_DOMAIN_AGENTS

        # ── Role agents ───────────────────────────────────────────────────────
        from citnega.packages.agents.roles import ALL_ROLE_AGENTS

        # ── Existing specialists ───────────────────────────────────────────────
        from citnega.packages.agents.specialists import ALL_SPECIALISTS

        all_classes = [
            # Core
            RouterAgent,
            ReasoningAgent,
            ValidatorAgent,
            WriterAgent,
            RetrieverAgent,
            ToolExecutorAgent,
            ConversationAgent,
            OrchestratorAgent,
            PlannerAgent,
            # Domain
            *ALL_DOMAIN_AGENTS,
            # Roles
            *ALL_ROLE_AGENTS,
            # Legacy specialists (kept for backward compat)
            *ALL_SPECIALISTS,
        ]

        agents = []
        for cls in all_classes:
            try:
                agents.append(self._make(cls))
            except Exception:
                pass  # skip any agent that fails to instantiate

        return agents
