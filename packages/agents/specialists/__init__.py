"""Specialist agents."""

from citnega.packages.agents.specialists.code_agent import CodeAgent
from citnega.packages.agents.specialists.data_agent import DataAgent
from citnega.packages.agents.specialists.file_agent import FileAgent
from citnega.packages.agents.specialists.qa_agent import QAAgent
from citnega.packages.agents.specialists.release_agent import ReleaseAgent
from citnega.packages.agents.specialists.research_agent import ResearchAgent
from citnega.packages.agents.specialists.security_agent import SecurityAgent
from citnega.packages.agents.specialists.summary_agent import SummaryAgent
from citnega.packages.agents.specialists.writing_agent import WritingAgent

ALL_SPECIALISTS = [
    ResearchAgent,
    SummaryAgent,
    FileAgent,
    DataAgent,
    WritingAgent,
    CodeAgent,
    QAAgent,
    SecurityAgent,
    ReleaseAgent,
]

__all__ = [
    "ALL_SPECIALISTS",
    "CodeAgent",
    "DataAgent",
    "FileAgent",
    "QAAgent",
    "ReleaseAgent",
    "ResearchAgent",
    "SecurityAgent",
    "SummaryAgent",
    "WritingAgent",
]
