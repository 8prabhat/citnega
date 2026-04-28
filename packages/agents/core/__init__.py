"""Core agents."""

from citnega.packages.agents.core.conversation_agent import ConversationAgent
from citnega.packages.agents.core.intent_classifier import IntentClassifierAgent
from citnega.packages.agents.core.orchestrator_agent import OrchestratorAgent
from citnega.packages.agents.core.planner_agent import PlannerAgent
from citnega.packages.agents.core.reasoning import ReasoningAgent
from citnega.packages.agents.core.replanner import RePlanner
from citnega.packages.agents.core.retriever import RetrieverAgent
from citnega.packages.agents.core.router import RouterAgent
from citnega.packages.agents.core.tool_executor import ToolExecutorAgent
from citnega.packages.agents.core.validator import ValidatorAgent
from citnega.packages.agents.core.writer import WriterAgent

ALL_CORE_AGENTS = [
    ConversationAgent,
    IntentClassifierAgent,
    OrchestratorAgent,
    PlannerAgent,
    RePlanner,
    RouterAgent,
    ReasoningAgent,
    ValidatorAgent,
    WriterAgent,
    RetrieverAgent,
    ToolExecutorAgent,
]

__all__ = [
    "ALL_CORE_AGENTS",
    "ConversationAgent",
    "IntentClassifierAgent",
    "OrchestratorAgent",
    "PlannerAgent",
    "RePlanner",
    "ReasoningAgent",
    "RetrieverAgent",
    "RouterAgent",
    "ToolExecutorAgent",
    "ValidatorAgent",
    "WriterAgent",
]
