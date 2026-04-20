"""Canonical AgentInput base model — single task field with legacy aliases."""

from __future__ import annotations

from pydantic import BaseModel, model_validator


class AgentInput(BaseModel):
    """
    Base model for all agent inputs.

    Accepts ``task``, ``query``, ``text``, or ``goal`` — all are aliased to
    ``task`` so downstream code only needs to read ``input.task``.
    """

    task: str = ""
    query: str = ""
    text: str = ""
    goal: str = ""

    model_config = {"extra": "allow"}

    @model_validator(mode="after")
    def _canonicalize_task(self) -> AgentInput:
        """Ensure task is populated from the first non-empty alias."""
        if not self.task:
            self.task = self.query or self.text or self.goal
        return self
