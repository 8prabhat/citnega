"""Specialist agents."""

from citnega.packages.agents.specialists.research_agent import ResearchAgent
from citnega.packages.agents.specialists.summary_agent import SummaryAgent
from citnega.packages.agents.specialists.file_agent import FileAgent
from citnega.packages.agents.specialists.data_agent import DataAgent
from citnega.packages.agents.specialists.writing_agent import WritingAgent

ALL_SPECIALISTS = [ResearchAgent, SummaryAgent, FileAgent, DataAgent, WritingAgent]

__all__ = [
    "ResearchAgent", "SummaryAgent", "FileAgent", "DataAgent", "WritingAgent",
    "ALL_SPECIALISTS",
]
