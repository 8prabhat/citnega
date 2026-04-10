"""
Routing policies for the Model Gateway.

StaticPriorityPolicy — pure rule-based: filters models by capability flags
  from TaskNeeds, then sorts by priority descending and returns the top match.

HybridRoutingPolicy — rules first (StaticPriorityPolicy), with a future
  LLM-based fallback slot for when no rule-based match exists.  In Phase 4
  the fallback simply selects the highest-priority model overall.
"""

from __future__ import annotations

from citnega.packages.observability.logging_setup import model_gateway_logger
from citnega.packages.protocol.interfaces.routing import IRoutingPolicy
from citnega.packages.protocol.models.model_gateway import ModelInfo, TaskNeeds
from citnega.packages.shared.errors import ModelGatewayError


class NoSuitableModelError(ModelGatewayError):
    error_code = "GATEWAY_NO_SUITABLE_MODEL"


def _model_satisfies(info: ModelInfo, needs: TaskNeeds) -> bool:
    """Return True if *info* satisfies all requirements in *needs*."""
    caps = info.capabilities
    if needs.local_only and not caps.local_only:
        return False
    if needs.streaming_required and not caps.supports_streaming:
        return False
    if needs.tool_calling_required and not caps.supports_tool_calling:
        return False
    if needs.reasoning_required and not caps.supports_reasoning:
        return False
    if needs.min_context_tokens > 0 and caps.max_context_tokens < needs.min_context_tokens:
        return False
    # Exclude unhealthy models
    if info.health_status == "down":
        return False
    return True


class StaticPriorityPolicy:
    """
    Rule-based routing: filter → sort by priority → pick best.

    Does NOT implement IRoutingPolicy directly — it is a helper used by
    ModelGateway.  Returns a list of suitable ModelInfo sorted by priority.
    """

    def select(
        self,
        models: list[ModelInfo],
        needs: TaskNeeds,
    ) -> list[ModelInfo]:
        """Return suitable models sorted by priority descending."""
        candidates = [m for m in models if _model_satisfies(m, needs)]

        # Prefer models listed in preferred_for matching task_type
        task_type = needs.task_type
        preferred = [m for m in candidates if task_type in m.preferred_for]
        others = [m for m in candidates if task_type not in m.preferred_for]

        sorted_preferred = sorted(preferred, key=lambda m: m.priority, reverse=True)
        sorted_others = sorted(others, key=lambda m: m.priority, reverse=True)
        result = sorted_preferred + sorted_others

        model_gateway_logger.debug(
            "routing_static_selected",
            task_type=task_type,
            candidates=len(candidates),
            top=result[0].model_id if result else None,
        )
        return result


class HybridRoutingPolicy:
    """
    Hybrid: StaticPriorityPolicy first; falls back to highest-priority
    overall when no capability-filtered match exists.

    The LLM-based fallback slot is reserved for Phase 5+ when the model
    gateway can query itself for routing decisions.
    """

    def __init__(self, models: list[ModelInfo]) -> None:
        self._models = models
        self._static = StaticPriorityPolicy()

    def update_models(self, models: list[ModelInfo]) -> None:
        self._models = models

    def select_best(self, needs: TaskNeeds) -> ModelInfo:
        """
        Select the single best model for the given needs.

        Raises NoSuitableModelError if no healthy model is available.
        """
        candidates = self._static.select(self._models, needs)
        if candidates:
            return candidates[0]

        # Fallback: ignore capability filters, pick highest priority healthy
        healthy = [m for m in self._models if m.health_status != "down"]
        if not healthy:
            raise NoSuitableModelError(
                "No healthy models available in the registry."
            )
        return max(healthy, key=lambda m: m.priority)
