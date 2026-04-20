"""
SkillImpactAnalyzer — scores how much each active skill contributed to a turn.

Uses trigger phrase overlap + preferred tool overlap as heuristics.
Pure stdlib, zero latency — safe to call on every turn.
"""

from __future__ import annotations

from typing import NamedTuple


class SkillImpactScore(NamedTuple):
    skill_name: str
    score: float  # 0.0–1.0
    evidence: str  # human-readable explanation for logging


class SkillImpactAnalyzer:
    """
    Score active skill contribution based on trigger phrases in the assistant reply
    and overlap between tools the skill prefers and tools actually called.
    """

    def analyze(
        self,
        skill_names: list[str],
        assistant_reply: str,
        tool_calls_made: list[str],
        skill_index: dict[str, dict] | None = None,
    ) -> list[SkillImpactScore]:
        """
        Return SkillImpactScore for each skill that had measurable impact (score > 0.1).
        Results are sorted descending by score.
        """
        if skill_index is None:
            from citnega.packages.skills.builtins import BUILTIN_SKILL_INDEX
            skill_index = BUILTIN_SKILL_INDEX

        results: list[SkillImpactScore] = []
        reply_lower = assistant_reply.lower()

        for name in skill_names:
            skill = skill_index.get(name)
            if not skill:
                continue

            triggers = [t.lower() for t in skill.get("triggers", [])]
            trigger_hits = sum(1 for t in triggers if t in reply_lower)
            trigger_score = trigger_hits / max(len(triggers), 1)

            preferred = skill.get("preferred_tools", []) + skill.get("preferred_agents", [])
            tool_overlap = sum(1 for t in tool_calls_made if any(t in p for p in preferred))
            tool_score = min(tool_overlap * 0.2, 0.4)

            score = min(trigger_score * 0.6 + tool_score, 1.0)
            if score > 0.1:
                results.append(
                    SkillImpactScore(
                        skill_name=name,
                        score=score,
                        evidence=f"triggers:{trigger_hits}/{len(triggers)}, tools:{tool_overlap}",
                    )
                )

        return sorted(results, key=lambda x: x.score, reverse=True)
