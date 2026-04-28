"""
SkillImprover — refines a skill's body using LLM after high-impact turns.

Gates: score threshold + minimum turn count prevent premature / over-eager improvement.
The improved body is written back to BUILTIN_SKILL_INDEX in-memory only — not persisted
to disk. On restart the process starts fresh. Persistence to workfolder is a future item.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from citnega.packages.skills.impact_analyzer import SkillImpactScore


_IMPROVEMENT_THRESHOLD = 0.70  # only improve when score >= this
_MIN_TURNS_BEFORE_IMPROVE = 5  # avoid improving on first few uses


class SkillImprover:
    """
    LLM-based skill body refinement.

    Requires a model_gateway and settings — both optional. When gateway is None
    the improver is a no-op, which is the safe default.
    """

    def __init__(self, model_gateway: object | None, settings: object | None) -> None:
        self._gateway = model_gateway
        self._settings = settings
        self._turn_counts: dict[str, int] = {}

    async def maybe_improve(
        self,
        score: SkillImpactScore,
        user_input: str,
        assistant_reply: str,
    ) -> str | None:
        """
        Return an improved skill body string if all gates pass, else None.
        Silently returns None on any error — improvement is best-effort.
        """
        if self._gateway is None:
            return None

        name = score.skill_name
        self._turn_counts[name] = self._turn_counts.get(name, 0) + 1

        if score.score < _IMPROVEMENT_THRESHOLD:
            return None
        if self._turn_counts[name] < _MIN_TURNS_BEFORE_IMPROVE:
            return None

        from citnega.packages.skills.builtins import BUILTIN_SKILL_INDEX
        skill = BUILTIN_SKILL_INDEX.get(name)
        if not skill:
            return None

        current_body = skill.get("body", "")
        if not current_body:
            return None

        prompt = (
            f"You are refining an AI skill definition based on observed successful usage.\n\n"
            f"SKILL NAME: {name}\n"
            f"CURRENT BODY:\n{current_body}\n\n"
            f"RECENT USER REQUEST: {user_input[:300]}\n"
            f"ASSISTANT RESPONSE EXCERPT: {assistant_reply[:500]}\n\n"
            f"Improve the skill body to better guide future turns:\n"
            f"- Keep the same markdown structure and headings.\n"
            f"- Add specific tool sequences that demonstrably worked.\n"
            f"- Remove or soften steps that were not needed in this turn.\n"
            f"- Be concise — final body must be ≤130% the length of the current body.\n\n"
            f"Return ONLY the improved body text, no preamble, no explanation."
        )

        try:
            from citnega.packages.protocol.models.model_gateway import ModelRequest

            model_id = getattr(self._settings, "default_model_id", "") if self._settings else ""
            req = ModelRequest(
                model_id=model_id,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=800,
                stream=False,
            )
            chunks: list[str] = []
            async for chunk in self._gateway.stream_generate(req):  # type: ignore[union-attr]
                if hasattr(chunk, "text"):
                    chunks.append(chunk.text)
            improved = "".join(chunks).strip()
            if not improved:
                return None

            # Persist improved skill body to disk so it survives restarts
            try:
                from pathlib import Path
                _skills_dir = Path.home() / ".citnega" / "skills"
                _skills_dir.mkdir(parents=True, exist_ok=True)
                (_skills_dir / f"{name}.md").write_text(improved, encoding="utf-8")
            except Exception:
                pass  # best-effort

            return improved
        except Exception:
            return None
