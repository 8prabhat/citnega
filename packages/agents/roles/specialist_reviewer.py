"""SpecialistReviewerAgent — reviews domain agent outputs for quality."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.agents.base import BaseAgent
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class ReviewerInput(BaseModel):
    content: str = Field(description="Content to review.")
    domain: str = Field(default="general", description="Domain context for the review.")


class ReviewerOutput(BaseModel):
    strengths: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    verdict: str = Field(description="Approved / Needs revision / Rejected")
    raw_review: str = Field(description="Full review text.")


class SpecialistReviewerAgent(BaseAgent):
    agent_id = "specialist_reviewer"
    name = "specialist_reviewer_agent"
    description = "Reviews domain specialist outputs for accuracy, completeness, and quality."
    callable_type = CallableType.SPECIALIST
    input_schema = ReviewerInput
    output_schema = ReviewerOutput
    policy = CallablePolicy(
        timeout_seconds=60.0,
        requires_approval=False,
        max_depth_allowed=3,
    )
    TOOL_WHITELIST: list[str] = []  # synthesizes via model only

    SYSTEM_PROMPT = (
        "You are a specialist reviewer. Review the given content rigorously. "
        "Format your response with sections: Strengths, Issues, Recommendations, Verdict."
    )

    async def _execute(self, input: ReviewerInput, context: CallContext) -> ReviewerOutput:
        user_msg = f"Domain: {input.domain}\n\nContent to review:\n{input.content}"
        raw = await self._call_model(user_msg, context)

        # Parse sections from free-form response
        strengths, issues, recs, verdict = [], [], [], "Needs revision"
        current: list[str] = []
        current_section = None
        for line in raw.splitlines():
            ls = line.strip()
            lsl = ls.lower()
            if "strength" in lsl:
                current_section = "strengths"
                current = strengths
            elif "issue" in lsl or "weakness" in lsl or "problem" in lsl:
                current_section = "issues"
                current = issues
            elif "recommend" in lsl or "suggestion" in lsl:
                current_section = "recs"
                current = recs
            elif "verdict" in lsl or "approved" in ls or "rejected" in ls or "revision" in lsl:
                verdict = ls.replace("**", "").replace("Verdict:", "").strip() or "Needs revision"
            elif ls.startswith(("-", "•", "*")) and current_section:
                current.append(ls.lstrip("-•* "))

        return ReviewerOutput(
            strengths=strengths,
            issues=issues,
            recommendations=recs,
            verdict=verdict,
            raw_review=raw,
        )
