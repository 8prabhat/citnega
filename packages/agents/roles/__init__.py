"""Role-based agents."""

from citnega.packages.agents.roles.specialist_reviewer import SpecialistReviewerAgent
from citnega.packages.agents.roles.specialist_writer import SpecialistWriterAgent

ALL_ROLE_AGENTS = [SpecialistReviewerAgent, SpecialistWriterAgent]

__all__ = ["ALL_ROLE_AGENTS", "SpecialistReviewerAgent", "SpecialistWriterAgent"]
