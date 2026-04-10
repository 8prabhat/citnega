"""
BaseAgent — YAML-driven configurable agent base.

All agents that load their system prompt, tool whitelist, and policy
from ``agents/config/agents.yaml`` extend this class.

Usage::

    class FinanceAgent(BaseAgent):
        agent_id = "finance"
        name     = "finance_agent"
        description = "Financial analysis specialist."
        input_schema  = SpecialistInput
        output_schema = SpecialistOutput

The ``agent_id`` key is looked up in ``agents.yaml``.  If not found,
the class-level ``SYSTEM_PROMPT`` and ``TOOL_WHITELIST`` are used as
fallback (backward-compatible with existing specialists).
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from citnega.packages.agents.specialists._specialist_base import SpecialistBase

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.interfaces import IInvocable
    from citnega.packages.protocol.interfaces.events import IEventEmitter, ITracer
    from citnega.packages.protocol.interfaces.policy import IPolicyEnforcer


# ── YAML loader (cached, module-level) ────────────────────────────────────────

_AGENTS_YAML = Path(__file__).parent / "config" / "agents.yaml"


@functools.lru_cache(maxsize=1)
def _load_agents_config() -> dict[str, Any]:
    """Load and cache agents.yaml. Returns empty dict on any error."""
    try:
        return yaml.safe_load(_AGENTS_YAML.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


# ── Base class ─────────────────────────────────────────────────────────────────

class BaseAgent(SpecialistBase):
    """
    YAML-configurable agent base.

    Subclasses set ``agent_id`` to match a key in ``agents.yaml``.
    At construction time, the YAML config is merged into the instance:
      - ``system_prompt`` overrides ``SYSTEM_PROMPT``
      - ``tools`` list overrides ``TOOL_WHITELIST``
      - ``policy`` overrides the class-level ``policy``

    This keeps domain logic in Python and configuration in YAML (OCP).
    """

    agent_id: str = ""   # override in subclasses — must match agents.yaml key

    def __init__(
        self,
        policy_enforcer: "IPolicyEnforcer",
        event_emitter:   "IEventEmitter",
        tracer:          "ITracer",
        tool_registry:   "dict[str, IInvocable] | None" = None,
    ) -> None:
        super().__init__(policy_enforcer, event_emitter, tracer, tool_registry)

        # Load YAML config for this agent
        config = _load_agents_config().get(self.agent_id, {})

        # Override system prompt if YAML has one
        yaml_prompt = config.get("system_prompt", "").strip()
        if yaml_prompt:
            self._system_prompt_override: str | None = yaml_prompt
        else:
            self._system_prompt_override = None

        # Override tool whitelist if YAML has one
        yaml_tools: list[str] | None = config.get("tools")
        if yaml_tools is not None:
            self.TOOL_WHITELIST = yaml_tools  # type: ignore[misc]

        # Override policy if YAML has one
        yaml_policy: dict | None = config.get("policy")
        if yaml_policy:
            from citnega.packages.protocol.callables.types import CallablePolicy  # noqa: PLC0415
            merged = {**self.policy.model_dump(), **yaml_policy}
            self.policy = CallablePolicy(**merged)  # type: ignore[misc]

    @property
    def effective_system_prompt(self) -> str:
        """Return YAML system prompt if set, else class-level SYSTEM_PROMPT."""
        return self._system_prompt_override or self.SYSTEM_PROMPT

    async def _call_model(
        self,
        user_input: str,
        context: "Any",
        system_override: str | None = None,
    ) -> str:
        """Call model with effective system prompt (YAML > class default)."""
        return await super()._call_model(
            user_input,
            context,
            system_override=system_override or self.effective_system_prompt,
        )
