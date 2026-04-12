"""ValidatorAgent — validates content against criteria."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.agents.base import BaseAgent
from citnega.packages.protocol.callables.types import CallableType

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class ValidatorInput(BaseModel):
    content: str = Field(description="The content to validate.")
    criteria: list[str] = Field(default_factory=list, description="Validation criteria.")


class ValidatorOutput(BaseModel):
    valid: bool = Field(description="True if content passes all criteria.")
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    score: float = Field(default=0.0, description="Quality score 0–1.")


class ValidatorAgent(BaseAgent):
    agent_id = "validator"
    name = "validator_agent"
    description = "Validates content against specified criteria and returns structured feedback."
    callable_type = CallableType.SPECIALIST
    input_schema = ValidatorInput
    output_schema = ValidatorOutput

    SYSTEM_PROMPT = (
        "You are a validation agent. Check whether the given content meets the criteria. "
        'Respond ONLY with JSON: {"valid": bool, "issues": [...], "suggestions": [...], "score": 0.0-1.0}'
    )

    async def _execute(self, input: ValidatorInput, context: CallContext) -> ValidatorOutput:
        criteria_text = (
            "\n".join(f"- {c}" for c in input.criteria) if input.criteria else "(general quality)"
        )
        user_msg = f"Criteria:\n{criteria_text}\n\nContent to validate:\n{input.content}"
        response = await self._call_model(user_msg, context)
        try:
            data = json.loads(response.strip())
            return ValidatorOutput(
                valid=bool(data.get("valid", False)),
                issues=data.get("issues", []),
                suggestions=data.get("suggestions", []),
                score=float(data.get("score", 0.5)),
            )
        except (json.JSONDecodeError, ValueError):
            return ValidatorOutput(valid=False, issues=["Parse error in validator response"])
