"""
SkillTriggerMatcher — live-wires the `triggers` field on every skill dict.

Each skill has a list of trigger phrases. This matcher counts how many triggers
appear in the user's input and returns the top-scoring skills. Pure substring
matching — no ML, no external deps, no latency.
"""

from __future__ import annotations


class SkillTriggerMatcher:
    """
    Match user input text to skills via their trigger phrases.

    Scoring: count of distinct triggers found in the lowercased input.
    Skills with zero matches are excluded.
    """

    def __init__(self, skill_index: dict[str, dict]) -> None:
        # Pre-lowercase all triggers at construction time for fast per-turn matching.
        self._index: list[tuple[str, list[str]]] = [
            (name, [t.lower() for t in skill.get("triggers", [])])
            for name, skill in skill_index.items()
            if skill.get("triggers")
        ]

    def match(self, user_input: str, limit: int = 3) -> list[str]:
        """
        Return up to `limit` skill names whose triggers match user_input.

        Returns an empty list when no skill triggers match — never raises.
        """
        if not user_input:
            return []
        text = user_input.lower()
        scores: list[tuple[int, str]] = []
        for name, triggers in self._index:
            matched = sum(1 for t in triggers if t in text)
            if matched:
                scores.append((matched, name))
        scores.sort(reverse=True)
        return [name for _, name in scores[:limit]]
