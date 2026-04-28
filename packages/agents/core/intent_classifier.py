"""
IntentClassifier — classifies user intent and recommends execution strategy.

Sits at the front of the pipeline and answers:
  • What *kind* of task is this? (simple Q&A / multi-step / agentic / code / research…)
  • Which *mode* best fits? (chat / code / research / plan / explore)
  • Should the planner or orchestrator be invoked, or direct conversation?
  • How many specialist agents are likely needed?

Used by ConversationAgent and autonomous runners to route requests optimally
before spending tokens on planning or execution.
"""

from __future__ import annotations

import json
import re
from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCoreAgent
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class TaskKind(str, Enum):
    SIMPLE       = "simple"        # single-turn factual / conversational
    RESEARCH     = "research"      # web search, knowledge gathering
    CODE         = "code"          # code generation / review / debug
    ANALYSIS     = "analysis"      # data analysis, comparison, summarisation
    MULTI_STEP   = "multi_step"    # sequential specialist workflow
    AGENTIC      = "agentic"       # autonomous, long-running, multi-agent
    FILE_OPS     = "file_ops"      # file read/write/edit
    CREATIVE     = "creative"      # writing, brainstorming, content generation
    PLANNING     = "planning"      # project plan, roadmap, strategy
    UNKNOWN      = "unknown"


class RecommendedMode(str, Enum):
    CHAT         = "chat"
    CODE         = "code"
    RESEARCH     = "research"
    AUTO_RESEARCH = "auto_research"
    PLAN         = "plan"
    EXPLORE      = "explore"
    AUTO         = "auto"         # let the model decide


class IntentClassifierInput(BaseModel):
    user_input: str = Field(description="The user's raw request.")
    conversation_history: list[str] = Field(
        default_factory=list,
        description="Last 3–5 turns of conversation for context.",
    )


class IntentClassifierOutput(BaseModel):
    task_kind: TaskKind = Field(description="Classified task type.")
    recommended_mode: RecommendedMode = Field(description="Suggested session mode.")
    needs_planning: bool = Field(
        default=False,
        description="True when multi-step planning is warranted.",
    )
    needs_orchestration: bool = Field(
        default=False,
        description="True when DAG-style orchestration across agents is warranted.",
    )
    estimated_specialist_count: int = Field(
        default=1,
        description="Rough number of specialist agents likely needed.",
    )
    confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Classifier confidence (0–1).",
    )
    rationale: str = Field(
        default="",
        description="One-sentence explanation of the classification.",
    )
    suggested_first_agent: str = Field(
        default="",
        description="Name of the first specialist or core agent to invoke, if obvious.",
    )


_SYSTEM_PROMPT = """\
You are an intent classification engine. Analyse the user request and output JSON.

Task kinds:
  simple       – single-turn factual answer or conversational reply
  research     – requires web search or knowledge retrieval
  code         – code generation, debugging, review, refactoring
  analysis     – data analysis, comparison, summarisation of existing info
  multi_step   – sequential workflow needing 2+ specialist agents
  agentic      – long-running autonomous goal (write → run → verify → iterate)
  file_ops     – reading, writing, editing files on disk
  creative     – writing, brainstorming, copywriting, design ideation
  planning     – project planning, roadmap, strategy, task breakdown
  unknown      – cannot classify confidently

Modes: chat | code | research | plan | explore | auto

Reply ONLY with valid JSON — no markdown fences:
{
  "task_kind": "<kind>",
  "recommended_mode": "<mode>",
  "needs_planning": <true|false>,
  "needs_orchestration": <true|false>,
  "estimated_specialist_count": <int>,
  "confidence": <0.0–1.0>,
  "rationale": "<one sentence>",
  "suggested_first_agent": "<agent_name or empty>"
}
"""


class IntentClassifierAgent(BaseCoreAgent):
    name = "intent_classifier"
    description = (
        "Classifies the user's intent and recommends execution strategy (mode, planning, "
        "orchestration). Call this first when routing is non-obvious, to avoid wasting "
        "tokens on the wrong specialist."
    )
    callable_type = CallableType.CORE
    llm_direct_access: bool = False   # called internally by router/conversation agents
    input_schema = IntentClassifierInput
    output_schema = IntentClassifierOutput
    policy = CallablePolicy(
        timeout_seconds=15.0,
        requires_approval=False,
        network_allowed=False,
        max_depth_allowed=1,
    )

    async def _execute(
        self, input: IntentClassifierInput, context: CallContext
    ) -> IntentClassifierOutput:
        # Fast keyword-based pre-classification (zero tokens, <1 ms)
        fast = self._fast_classify(input.user_input)
        if fast is not None and fast.confidence >= 0.85:
            return fast

        # LLM-based classification (used for ambiguous requests)
        if context.model_gateway is None:
            return fast or self._fallback(input.user_input)

        from citnega.packages.protocol.models.model_gateway import ModelMessage, ModelRequest

        messages: list[ModelMessage] = [ModelMessage(role="system", content=_SYSTEM_PROMPT)]
        if input.conversation_history:
            context_text = "\n".join(f"- {t}" for t in input.conversation_history[-3:])
            messages.append(
                ModelMessage(role="system", content=f"Recent turns:\n{context_text}")
            )
        messages.append(ModelMessage(role="user", content=input.user_input))

        try:
            response = await context.model_gateway.generate(
                ModelRequest(messages=messages, stream=False, temperature=0.0)
            )
            raw = response.content.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            data = json.loads(raw.strip())
            return IntentClassifierOutput(
                task_kind=TaskKind(data.get("task_kind", "unknown")),
                recommended_mode=RecommendedMode(data.get("recommended_mode", "auto")),
                needs_planning=bool(data.get("needs_planning", False)),
                needs_orchestration=bool(data.get("needs_orchestration", False)),
                estimated_specialist_count=int(data.get("estimated_specialist_count", 1)),
                confidence=float(data.get("confidence", 0.75)),
                rationale=str(data.get("rationale", "")),
                suggested_first_agent=str(data.get("suggested_first_agent", "")),
            )
        except Exception:
            return fast or self._fallback(input.user_input)

    # ── Fast keyword classifier (no LLM) ─────────────────────────────────────

    _RESEARCH_DEEP_KEYWORDS = frozenset({
        "auto research", "deep research", "comprehensive research",
        "investigate thoroughly", "research in depth", "full report on",
        "multi-source", "find all information about", "cross-verify",
        "thorough research", "investigative report", "in-depth analysis",
    })

    _CODE_KEYWORDS = frozenset({
        "code", "function", "bug", "debug", "refactor", "implement", "class",
        "method", "test", "lint", "compile", "script", "python", "javascript",
        "typescript", "rust", "java", "go ", "sql", "api", "endpoint",
    })
    _RESEARCH_KEYWORDS = frozenset({
        "research", "find", "search", "latest", "news", "article", "paper",
        "what is", "who is", "explain", "learn about", "tell me about",
    })
    _PLAN_KEYWORDS = frozenset({
        "plan", "roadmap", "strategy", "schedule", "milestone", "epic",
        "sprint", "project", "timeline", "breakdown", "steps to",
    })
    _FILE_KEYWORDS = frozenset({
        "read file", "write file", "edit file", "open file", "save file",
        "create file", "delete file", "list files", "directory",
        ".yaml", ".json", ".csv", ".txt", ".toml", ".env", ".log", ".md",
        "file contents", "its contents",
    })
    _AGENTIC_KEYWORDS = frozenset({
        "autonomously", "run continuously", "monitor", "watch", "every hour",
        "every day", "scheduled", "poll", "retry until", "keep trying",
        "background task", "long running",
    })
    _MULTI_STEP_KEYWORDS = frozenset({
        "then", "after that", "followed by", "step by step",
        "and also", "multiple steps", "several tasks", "chain",
        "workflow", "pipeline", "orchestrate", "coordinate",
        "first build", "first write", "first create", "first run",
        "then deploy", "then test", "then verify", "then publish",
    })

    @classmethod
    def _fast_classify(cls, text: str) -> IntentClassifierOutput | None:
        lower = text.lower()
        words = set(re.findall(r'\b\w+\b', lower))

        def _match(keywords: frozenset) -> bool:
            for kw in keywords:
                if ' ' in kw:
                    if kw in lower:
                        return True
                elif kw in words:
                    return True
            return False

        if _match(cls._AGENTIC_KEYWORDS):
            return IntentClassifierOutput(
                task_kind=TaskKind.AGENTIC,
                recommended_mode=RecommendedMode.AUTO,
                needs_planning=True,
                needs_orchestration=True,
                estimated_specialist_count=3,
                confidence=0.87,
                rationale="Request contains long-running or autonomous operation signals.",
                suggested_first_agent="orchestrator_agent",
            )

        # MULTI_STEP is checked before CODE/PLAN/RESEARCH so that compound requests
        # ("build X then test it") are routed to orchestration rather than a single specialist.
        if _match(cls._MULTI_STEP_KEYWORDS):
            return IntentClassifierOutput(
                task_kind=TaskKind.MULTI_STEP,
                recommended_mode=RecommendedMode.PLAN,
                needs_planning=True,
                needs_orchestration=True,
                estimated_specialist_count=2,
                confidence=0.82,
                rationale="Request contains multi-step sequencing signals.",
                suggested_first_agent="planner_agent",
            )

        if _match(cls._CODE_KEYWORDS):
            return IntentClassifierOutput(
                task_kind=TaskKind.CODE,
                recommended_mode=RecommendedMode.CODE,
                needs_planning=len(text) > 200,
                needs_orchestration=False,
                estimated_specialist_count=1,
                confidence=0.88,
                rationale="Request contains code-related keywords.",
                suggested_first_agent="code_agent",
            )

        if _match(cls._PLAN_KEYWORDS):
            return IntentClassifierOutput(
                task_kind=TaskKind.PLANNING,
                recommended_mode=RecommendedMode.PLAN,
                needs_planning=True,
                needs_orchestration=False,
                estimated_specialist_count=1,
                confidence=0.86,
                rationale="Request contains planning or roadmap keywords.",
                suggested_first_agent="planner_agent",
            )

        if _match(cls._RESEARCH_DEEP_KEYWORDS):
            return IntentClassifierOutput(
                task_kind=TaskKind.RESEARCH,
                recommended_mode=RecommendedMode.AUTO_RESEARCH,
                needs_planning=True,
                needs_orchestration=False,
                estimated_specialist_count=1,
                confidence=0.89,
                rationale="Request contains deep/autonomous research signals.",
                suggested_first_agent="auto_research_agent",
            )

        if _match(cls._RESEARCH_KEYWORDS):
            return IntentClassifierOutput(
                task_kind=TaskKind.RESEARCH,
                recommended_mode=RecommendedMode.RESEARCH,
                needs_planning=False,
                needs_orchestration=False,
                estimated_specialist_count=1,
                confidence=0.85,
                rationale="Request contains research/lookup keywords.",
                suggested_first_agent="research_agent",
            )

        if _match(cls._FILE_KEYWORDS):
            return IntentClassifierOutput(
                task_kind=TaskKind.FILE_OPS,
                recommended_mode=RecommendedMode.EXPLORE,
                needs_planning=False,
                needs_orchestration=False,
                estimated_specialist_count=1,
                confidence=0.88,
                rationale="Request involves file system operations.",
                suggested_first_agent="file_agent",
            )

        return None

    def _fallback(self, text: str) -> IntentClassifierOutput:
        return IntentClassifierOutput(
            task_kind=TaskKind.SIMPLE,
            recommended_mode=RecommendedMode.CHAT,
            needs_planning=False,
            needs_orchestration=False,
            estimated_specialist_count=1,
            confidence=0.5,
            rationale="Unable to classify — defaulting to simple conversational response.",
        )
