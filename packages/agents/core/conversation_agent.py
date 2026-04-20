"""
ConversationAgent — primary core agent for interactive sessions.

Delegates to specialists via a supervisor loop:
  1. Ask RouterAgent which specialist to call (or if done).
  2. Invoke the specialist and accumulate its result.
  3. Repeat up to MAX_ROUNDS times.
  4. If multiple results accumulated, synthesise a final answer.
  5. Fall back to a direct model response when router is unavailable.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCoreAgent
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext
    from citnega.packages.protocol.callables.interfaces import IStreamable

_MAX_SUPERVISOR_ROUNDS_DEFAULT = 3


def _get_max_supervisor_rounds() -> int:
    try:
        from citnega.packages.config.loaders import load_settings

        return load_settings().runtime.max_supervisor_rounds
    except Exception:
        return _MAX_SUPERVISOR_ROUNDS_DEFAULT

# Common primary-text field names used across specialist input schemas, in
# priority order.  The first one that exists in the schema is used.
_TEXT_FIELD_CANDIDATES = ("query", "task", "text", "user_input", "prompt", "input")


def _build_specialist_input(schema: type, user_input: str) -> dict:
    """
    Build a minimal input dict for a specialist by inspecting its schema.

    Finds the first required (or optional) string field whose name suggests
    it is the primary text input, maps user_input to it, and leaves all other
    fields at their defaults.  This avoids both the "spray every known name"
    anti-pattern and hard crashes on missing required fields.
    """
    try:
        fields = schema.model_fields  # pydantic v2
    except AttributeError:
        # Fallback: return a dict with all candidate keys — Pydantic ignores unknowns
        return dict.fromkeys(_TEXT_FIELD_CANDIDATES, user_input)

    # Build a dict: required string fields → user_input; everything else omitted
    result: dict = {}
    for candidate in _TEXT_FIELD_CANDIDATES:
        if candidate in fields:
            result[candidate] = user_input
            break  # one primary text field is enough

    # If no candidate matched, fill the first required field that has no default
    if not result:
        for name, field_info in fields.items():
            is_required = field_info.is_required()
            annotation = field_info.annotation
            if is_required and annotation in (str, "str"):
                result[name] = user_input
                break

    return result


class ConversationInput(BaseModel):
    user_input: str = Field(description="The user's message or request.")
    session_context: str = Field(default="", description="Optional assembled context string.")


class ConversationOutput(BaseModel):
    response: str = Field(description="Agent's text response.")
    routed_to: str | None = Field(default=None, description="Specialist(s) routed to, if any.")
    tool_calls: list[str] = Field(default_factory=list)


_DIRECT_SYSTEM_PROMPT = (
    "You are Citnega, a helpful, honest, and capable AI assistant. "
    "Answer questions directly and concisely. Ask for clarification when needed. "
    "Never make up facts. Cite sources when available."
)

_SYNTHESIS_SYSTEM_PROMPT = (
    "You are Citnega. Combine the specialist results below into a single, "
    "coherent, concise answer for the user. Do not repeat the raw results verbatim; "
    "synthesise them into a natural response."
)


class ConversationAgent(BaseCoreAgent):
    name = "conversation_agent"
    description = (
        "Multi-step orchestrator: routes a complex request through the right specialists "
        "and synthesises their outputs into a single coherent response. "
        "Use this when a task needs multiple specialists working together "
        "(e.g. research + summarise, or read files + analyse + write report). "
        "For single-specialist tasks call the specialist directly instead."
    )
    callable_type = CallableType.CORE
    # Exposed to the LLM so it can invoke orchestration for complex multi-step tasks.
    llm_direct_access: bool = True
    input_schema = ConversationInput
    output_schema = ConversationOutput
    policy = CallablePolicy(
        timeout_seconds=300.0,
        requires_approval=False,
        network_allowed=True,
        max_depth_allowed=4,
    )

    # ── Entry point ───────────────────────────────────────────────────────────

    async def _execute(self, input: ConversationInput, context: CallContext) -> ConversationOutput:
        if self._nextgen_planning_enabled():
            return await self._execute_nextgen(input, context)
        return await self._execute_legacy(input, context)

    async def _execute_legacy(self, input: ConversationInput, context: CallContext) -> ConversationOutput:
        router = self._get_peer("router_agent")

        if router is None or context.model_gateway is None:
            # No router or no model — skip supervisor, go direct
            return await self._direct_response(input, context)

        accumulated: list[tuple[str, str]] = []  # [(agent_name, result_text)]

        for _round in range(_get_max_supervisor_rounds()):
            route = await self._ask_router(
                router,
                input.user_input,
                [r for _, r in accumulated],
                context,
            )

            if route is None:
                break

            # Router says we're done or wants conversation_agent (direct answer)
            if route.is_complete or route.agent in ("none", self.name, "conversation_agent", ""):
                break

            specialist = self._get_peer(route.agent)
            if specialist is None:
                break

            result_text = await self._invoke_specialist(specialist, input.user_input, context)
            accumulated.append((route.agent, result_text))

        if accumulated:
            return await self._synthesise(input, accumulated, context)

        return await self._direct_response(input, context)

    async def _execute_nextgen(self, input: ConversationInput, context: CallContext) -> ConversationOutput:
        from citnega.packages.planning.classifier import TaskClassifier

        capability_registry = getattr(context, "capability_registry", None)
        classification = TaskClassifier().classify(input.user_input, registry=capability_registry)

        if classification.path == "direct_answer":
            return await self._direct_response(input, context)

        if classification.path == "compiled_plan":
            planner = self._get_peer("planner_agent")
            if planner is not None:
                planned = await self._invoke_planner(planner, input, context, classification.capability_id or "")
                if planned is not None:
                    return planned
            return await self._direct_response(input, context)

        # path == "specialist"
        if classification.capability_id:
            specialist = self._get_peer(classification.capability_id)
            if specialist is not None:
                result_text = await self._invoke_specialist(specialist, input.user_input, context)
                if result_text:
                    return ConversationOutput(response=result_text, routed_to=classification.capability_id)

        # Fallback: try router for specialist discovery
        router = self._get_peer("router_agent")
        if router is not None:
            route = await self._ask_router(router, input.user_input, [], context)
            if route is not None and not route.is_complete and route.agent not in {"none", self.name, "conversation_agent", ""}:
                specialist = self._get_peer(route.agent)
                if specialist is not None:
                    result_text = await self._invoke_specialist(specialist, input.user_input, context)
                    if result_text:
                        return ConversationOutput(response=result_text, routed_to=route.agent)

        return await self._direct_response(input, context)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_peer(self, name: str) -> IStreamable | None:
        """Return a sub_callable by name, or None."""
        for c in self.list_sub_callables():
            if c.name == name:
                return c
        return None

    async def _ask_router(
        self,
        router: IStreamable,
        user_input: str,
        previous_results: list[str],
        context: CallContext,
    ):
        """Call RouterAgent and return its output, or None on failure."""
        from citnega.packages.agents.core.router import RouterInput

        try:
            child_ctx = context.child(self.name, self.callable_type)
            result = await router.invoke(
                RouterInput(user_input=user_input, previous_results=previous_results),
                child_ctx,
            )
            if result.success and result.output:
                return result.output
        except Exception:
            pass
        return None

    async def _invoke_specialist(
        self,
        specialist: IStreamable,
        user_input: str,
        context: CallContext,
    ) -> str:
        """Invoke a specialist with a best-effort input and return text result."""
        child_ctx = context.child(self.name, self.callable_type)
        try:
            input_obj = specialist.input_schema.model_validate(
                _build_specialist_input(specialist.input_schema, user_input)
            )
            result = await specialist.invoke(input_obj, child_ctx)
            if result.success and result.output:
                out = result.output
                # Try common response field names
                for field in ("response", "result", "content", "summary", "output"):
                    val = getattr(out, field, None)
                    if val:
                        return str(val)
                return out.model_dump_json()
            if result.error:
                return f"[{specialist.name} error: {result.error.message}]"
        except Exception as exc:
            return f"[{specialist.name} error: {exc}]"
        return ""

    async def _synthesise(
        self,
        input: ConversationInput,
        accumulated: list[tuple[str, str]],
        context: CallContext,
    ) -> ConversationOutput:
        """Merge multiple specialist results into a single coherent response."""
        from citnega.packages.protocol.models.model_gateway import ModelMessage, ModelRequest

        if context.model_gateway is None:
            # No gateway — join results with labels
            parts = [f"**{name}**: {text}" for name, text in accumulated]
            return ConversationOutput(
                response="\n\n".join(parts),
                routed_to=", ".join(n for n, _ in accumulated),
            )

        results_block = "\n\n".join(
            f"[{name}]:\n{text}" for name, text in accumulated
        )
        messages = [
            ModelMessage(role="system", content=_SYNTHESIS_SYSTEM_PROMPT),
            ModelMessage(role="system", content=f"Specialist results:\n{results_block}"),
            ModelMessage(role="user", content=input.user_input),
        ]
        response = await context.model_gateway.generate(
            ModelRequest(messages=messages, stream=False, temperature=0.7)
        )
        return ConversationOutput(
            response=response.content,
            routed_to=", ".join(n for n, _ in accumulated),
        )

    async def _direct_response(
        self,
        input: ConversationInput,
        context: CallContext,
    ) -> ConversationOutput:
        """Direct model call — no specialist routing."""
        if context.model_gateway is None:
            return ConversationOutput(response="(model gateway unavailable)", routed_to=None)

        from citnega.packages.protocol.models.model_gateway import ModelMessage, ModelRequest

        messages: list[ModelMessage] = [
            ModelMessage(role="system", content=_DIRECT_SYSTEM_PROMPT),
        ]
        if input.session_context:
            messages.append(
                ModelMessage(
                    role="system",
                    content=f"Session context:\n{input.session_context}",
                )
            )
        messages.append(ModelMessage(role="user", content=input.user_input))

        response = await context.model_gateway.generate(
            ModelRequest(messages=messages, stream=False, temperature=0.7)
        )
        return ConversationOutput(response=response.content, routed_to=None)

    async def _invoke_planner(
        self,
        planner: IStreamable,
        input: ConversationInput,
        context: CallContext,
        preferred_capability: str,
    ) -> ConversationOutput | None:
        from citnega.packages.agents.core.planner_agent import PlannerInput

        child_ctx = context.child(self.name, self.callable_type)
        planner_input = PlannerInput(
            goal=input.user_input,
            constraints="",
            max_steps=6,
            preferred_capability=preferred_capability,
        )
        result = await planner.invoke(planner_input, child_ctx)
        if not result.success or result.output is None:
            return None
        plan_steps = list(getattr(result.output, "plan_steps", []))
        return ConversationOutput(
            response=result.output.response,
            routed_to="planner_agent",
            tool_calls=plan_steps,
        )

    @staticmethod
    def _nextgen_planning_enabled() -> bool:
        try:
            from citnega.packages.config.loaders import load_settings

            return load_settings().nextgen.planning_enabled
        except Exception:
            return False
