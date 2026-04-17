"""
TaskClassifier — routes an objective to the appropriate execution path.

Classification paths (in order of priority):
  direct_answer   — short factual question; no specialist or plan needed
  specialist      — single capability match from registry metadata
  compiled_plan   — multi-step, ambiguous, or plan-mode request
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel

if TYPE_CHECKING:
    from citnega.packages.capabilities.registry import CapabilityRegistry
    from citnega.packages.strategy.models import StrategySpec

_CLASSIFIER_CONFIDENCE_THRESHOLD_DEFAULT = 0.7

# Patterns that indicate a short, factual question best answered directly.
_DIRECT_ANSWER_PATTERNS = re.compile(
    r"^(what\s+is|what\'s|who\s+is|who\'s|where\s+is|when\s+is|define|explain|"
    r"tell\s+me\s+about|how\s+do\s+you|what\s+does|what\s+are)\b",
    re.IGNORECASE,
)
_DIRECT_ANSWER_MAX_WORDS = 12

# Patterns that indicate a complex, multi-step request needing a plan.
_PLAN_PATTERNS = re.compile(
    r"\b(plan|step[\s-]by[\s-]step|workflow|then\s+.*(then|after|next)|"
    r"first.*then|multiple\s+steps?|sequence|pipeline|automate|"
    r"end[\s-]to[\s-]end|full\s+process|create\s+and\s+(then|also)|"
    r"implement\s+and\s+(test|deploy)|build\s+and\s+(run|test|deploy))\b",
    re.IGNORECASE,
)


class ClassificationResult(BaseModel):
    path: Literal["direct_answer", "specialist", "compiled_plan"]
    capability_id: str | None = None
    confidence: float = 1.0
    reason: str = ""


class TaskClassifier:
    """Deterministic first-pass classifier with optional registry-based routing."""

    def classify(
        self,
        objective: str,
        registry: CapabilityRegistry | None = None,
        strategy: StrategySpec | None = None,
    ) -> ClassificationResult:
        objective = objective.strip()

        # 1. Strategy override → compiled_plan (highest priority)
        if strategy is not None and getattr(strategy, "force_plan_mode", False):
            return ClassificationResult(
                path="compiled_plan",
                confidence=1.0,
                reason="strategy forces plan mode",
            )

        # 2. Short factual question → direct answer
        word_count = len(objective.split())
        if word_count <= _DIRECT_ANSWER_MAX_WORDS and _DIRECT_ANSWER_PATTERNS.match(objective):
            return ClassificationResult(
                path="direct_answer",
                confidence=0.9,
                reason="short factual question",
            )

        # 3. Explicit plan indicators → compiled_plan
        if _PLAN_PATTERNS.search(objective):
            return ClassificationResult(
                path="compiled_plan",
                confidence=0.85,
                reason="plan pattern detected",
            )

        # 4. Registry-based single-capability match
        if registry is not None:
            match = self._registry_match(objective, registry)
            if match is not None and match[1] >= _CLASSIFIER_CONFIDENCE_THRESHOLD_DEFAULT:
                return ClassificationResult(
                    path="specialist",
                    capability_id=match[0],
                    confidence=match[1],
                    reason=f"registry match: {match[0]}",
                )

        # 5. Default → compiled_plan (safe default for unknown cases)
        return ClassificationResult(
            path="compiled_plan",
            confidence=0.6,
            reason="fallback: no clear single-capability match",
        )

    def _registry_match(
        self,
        objective: str,
        registry: CapabilityRegistry,
    ) -> tuple[str, float] | None:
        """
        Score each capability descriptor against the objective.

        Returns (capability_id, confidence) for the best match above threshold,
        or None if no match is found.
        """
        from citnega.packages.capabilities.models import CapabilityKind

        objective_lower = objective.lower()
        words = set(re.findall(r"\w+", objective_lower))

        best_id: str | None = None
        best_score: float = 0.0

        for descriptor in registry.list_all():
            # Only route to agents or tools — not workflow templates or skills
            if descriptor.kind not in (CapabilityKind.AGENT, CapabilityKind.TOOL):
                continue

            score = 0.0
            name_lower = descriptor.capability_id.lower().replace("_", " ")
            desc_lower = descriptor.description.lower()

            # Name match: direct overlap between capability name and objective words
            name_words = set(name_lower.split())
            overlap = len(words & name_words)
            if overlap > 0:
                score += overlap * 0.3

            # Description match: keyword overlap
            desc_words = set(re.findall(r"\w+", desc_lower))
            desc_overlap = len(words & desc_words)
            if desc_overlap > 0:
                score += min(desc_overlap * 0.05, 0.3)

            # Tag match
            for tag in descriptor.tags:
                if tag.lower() in objective_lower:
                    score += 0.2

            # Normalize to [0, 1]
            score = min(score, 1.0)

            if score > best_score:
                best_score = score
                best_id = descriptor.capability_id

        if best_id is not None and best_score >= _CLASSIFIER_CONFIDENCE_THRESHOLD_DEFAULT:
            return best_id, best_score
        return None
