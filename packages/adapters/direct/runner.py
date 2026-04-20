"""
DirectModelRunner — IFrameworkRunner that calls a model provider directly.

Responsibilities (single, separated):
  - Resolves the active model via ConversationStore / context
  - Augments the system prompt via ISessionMode (plan / explore / chat)
  - Optionally parses <think>…</think> blocks via ThinkingStreamParser
  - Streams TokenEvent (response) and ThinkingEvent (reasoning) into the queue
  - Executes tool calls requested by the model (up to MAX_TOOL_ROUNDS)
  - Persists the completed turn to ConversationStore

Dependencies are injected at construction time (DIP).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import json
import os
import subprocess
from typing import TYPE_CHECKING, Any
import uuid

from citnega.packages.capabilities import callable_to_descriptor
from citnega.packages.config.loaders import load_settings
from citnega.packages.model_gateway.provider_factory import ProviderFactory
from citnega.packages.observability.logging_setup import runtime_logger
from citnega.packages.protocol.events.streaming import TokenEvent
from citnega.packages.protocol.events.thinking import ThinkingEvent
from citnega.packages.protocol.interfaces.adapter import IFrameworkRunner
from citnega.packages.protocol.models.checkpoints import CheckpointMeta
from citnega.packages.protocol.models.model_gateway import ModelMessage, ModelRequest
from citnega.packages.protocol.models.runs import RunState, StateSnapshot
from citnega.packages.protocol.modes import get_mode
from citnega.packages.runtime.context.conversation_store import ConversationStore
from citnega.packages.runtime.thinking_parser import ThinkingStreamParser

if TYPE_CHECKING:
    from citnega.packages.model_gateway.yaml_config import ModelYAMLConfig
    from citnega.packages.protocol.callables.interfaces import IInvocable
    from citnega.packages.protocol.events import CanonicalEvent
    from citnega.packages.protocol.models.context import ContextObject
    from citnega.packages.protocol.models.model_gateway import ModelRequest, ModelResponse
    from citnega.packages.protocol.models.runner import ConversationStats
    from citnega.packages.protocol.models.sessions import Session

_MAX_TOOL_ROUNDS_DEFAULT = 5  # prevent infinite tool-call loops


class _RunnerModelGateway:
    """
    Thin IModelGateway adapter wrapping a ProviderFactory.

    Passed into CallContext so specialist agents called during tool execution
    can make non-streaming model calls via context.model_gateway.generate().
    """

    def __init__(self, factory: ProviderFactory, model_id: str) -> None:
        self._factory = factory
        self._model_id = model_id

    async def generate(self, request: ModelRequest) -> ModelResponse:
        from citnega.packages.protocol.models.model_gateway import ModelResponse as _MR

        effective_id = request.model_id or self._model_id
        try:
            provider, effective_id = self._factory.build(effective_id), effective_id
        except KeyError:
            entries = self._factory.list_entries()
            if not entries:
                return _MR(content="[no model available]", model_id=effective_id)
            effective_id = entries[0].id
            provider = self._factory.build(effective_id)

        req = request.model_copy(update={"model_id": effective_id, "stream": False})
        return await provider.generate(req)

    async def stream_generate(self, request):
        effective_id = request.model_id or self._model_id
        try:
            provider = self._factory.build(effective_id)
        except KeyError:
            entries = self._factory.list_entries()
            if not entries:
                return
            provider = self._factory.build(entries[0].id)
            effective_id = entries[0].id

        req = request.model_copy(update={"model_id": effective_id, "stream": True})
        async for chunk in provider.stream_generate(req):
            yield chunk

    async def list_models(self):
        return []

    async def health_check_all(self):
        return {}


class DirectModelRunner(IFrameworkRunner):
    """
    Thin runner that talks directly to an IModelProvider.

    One instance per session, created by DirectModelAdapter.
    Supports multi-round tool calling with registered IInvocable tools.
    """

    def __init__(
        self,
        session: Session,
        yaml_config: ModelYAMLConfig,
        conversation_store: ConversationStore,
        callables: list[IInvocable] | None = None,
        model_gateway: object | None = None,
        capability_registry: object | None = None,
        max_tool_rounds: int = _MAX_TOOL_ROUNDS_DEFAULT,
    ) -> None:
        self._session = session
        self._factory = ProviderFactory(yaml_config)
        self._conv = conversation_store
        self._cancelled = False
        self._paused = False
        self._current_model_id: str = ""
        self._max_tool_rounds = max_tool_rounds
        # Injected ModelGateway (routing + rate-limiting). Falls back to
        # _RunnerModelGateway (direct ProviderFactory) when not provided.
        self._model_gateway = model_gateway
        self._capability_registry = capability_registry
        # Expose TOOL and SPECIALIST callables to the model for function calling.
        # SPECIALIST agents appear as callable tools so the model can invoke them.
        from citnega.packages.protocol.callables.types import CallableType

        # ── Which callables the LLM sees in its function-calling schema ─────────
        #
        # Design principle: the LLM is an orchestrator, not a low-level caller.
        #
        #   SPECIALIST agents  → always in the LLM schema.
        #   TOOL               → in the schema only when llm_direct_access=True
        #                        (the default).  Tools that set llm_direct_access=False
        #                        are agent-internal and never shown to the LLM directly.
        #
        # Each tool controls its own visibility via the llm_direct_access class flag —
        # no hardcoded allowlist here.

        def _llm_visible(c: IInvocable) -> bool:
            if not getattr(c, "callable_type", None):
                return False
            if c.callable_type == CallableType.SPECIALIST:
                return True
            if c.callable_type == CallableType.TOOL:
                return getattr(c, "llm_direct_access", True)
            if c.callable_type == CallableType.CORE:
                # CORE agents are LLM-visible only when they explicitly opt in via
                # llm_direct_access = True.  RouterAgent is internal (called by
                # ConversationAgent), so it stays hidden.  ConversationAgent and
                # PlannerAgent are exposed so the LLM can invoke multi-step
                # orchestration when the task warrants it.
                return getattr(c, "llm_direct_access", False)
            return False

        self._tools: dict[str, IInvocable] = {
            c.name: c for c in (callables or []) if _llm_visible(c)
        }
        # Keep ALL callables (TOOL + SPECIALIST + CORE) so that:
        #   • tools with llm_direct_access=False are reachable by specialists
        #   • CORE agents (ConversationAgent, RouterAgent, PlannerAgent) are
        #     reachable when the LLM calls them via function-calling
        self._all_callables: dict[str, IInvocable] = {
            c.name: c
            for c in (callables or [])
            if getattr(c, "callable_type", None) is not None
            and c.callable_type in (
                CallableType.TOOL,
                CallableType.SPECIALIST,
                CallableType.CORE,
            )
        }

        # Trigger matcher: auto-activates skills from user input on each turn
        from citnega.packages.skills.builtins import BUILTIN_SKILL_INDEX
        from citnega.packages.skills.trigger_matcher import SkillTriggerMatcher
        self._trigger_matcher = SkillTriggerMatcher(BUILTIN_SKILL_INDEX)

        # Post-turn skill improver (None = disabled until wired by bootstrap)
        self._skill_improver: object | None = None

    # ── IFrameworkRunner ──────────────────────────────────────────────────────

    async def run_turn(
        self,
        user_input: str,
        context: ContextObject,
        event_queue: asyncio.Queue[CanonicalEvent],
    ) -> str:
        if self._cancelled:
            raise asyncio.CancelledError("runner was cancelled")

        session_id = self._session.config.session_id
        run_id = context.run_id
        turn_id = str(uuid.uuid4())

        # 1. Resolve model
        model_id = context.active_model_id or self._conv.active_model_id
        if not model_id:
            entries = self._factory.list_entries()
            if not entries:
                raise RuntimeError("No models configured in models.yaml")
            model_id = entries[0].id

        runtime_logger.debug(
            "direct_runner_turn_start",
            session_id=session_id,
            run_id=run_id,
            model_id=model_id,
            mode=self._conv.mode_name,
        )

        # 2. Build provider (with fallback)
        provider, model_id = self._resolve_provider(model_id)
        self._current_model_id = model_id

        # 3. Augment system prompt with session mode + phase
        mode = get_mode(self._conv.mode_name)
        turn_temperature = mode.temperature
        phase = self._conv.plan_phase
        base_prompt = (
            ConversationStore._SYSTEM_PROMPT
            + ConversationStore.build_tools_section(self._tools)
        )
        try:
            system_prompt = mode.augment_system_prompt(base_prompt, phase=phase)
        except TypeError:
            system_prompt = mode.augment_system_prompt(base_prompt)

        # 3b. Auto-activate skills from trigger matching (session-scoped, non-persistent)
        try:
            matched = self._trigger_matcher.match(user_input)
            if matched:
                existing = set(getattr(self._conv, "active_skills", None) or [])
                new_skills = [s for s in matched if s not in existing]
                if new_skills:
                    self._conv.set_active_skills(list(existing | set(new_skills)))
        except Exception:
            pass

        # 3b. Inject strategy context (active skills + mental model clauses)
        _token_budget = int(context.metadata.get("token_budget_remaining", 8000)) if hasattr(context, "metadata") and context.metadata else 8000
        strategy_block = self._build_strategy_context(token_budget=_token_budget)
        if strategy_block:
            system_prompt = system_prompt + strategy_block

        # 3c. Inject ambient workspace context (cwd, git branch/status, time)
        ambient_block = self._build_ambient_context()
        if ambient_block:
            system_prompt = system_prompt + ambient_block

        # 3d. Inject KB context sources into the system prompt
        kb_sources = [s for s in (context.sources or []) if s.source_type == "kb"]
        if kb_sources:
            kb_block = "\n\n".join(s.content for s in kb_sources)
            system_prompt = (
                system_prompt
                + "\n\n---\n**Relevant knowledge base context:**\n"
                + kb_block
                + "\n---"
            )

        # 4. Persist user message NOW (before LLM call) so it survives
        #    process termination mid-stream.  The assistant reply is saved below.
        await self._conv.add_message("user", user_input)

        # 4b. Build message list for the model.
        #     user_input is already the last item in stored history, so we
        #     take the full history slice (which ends with user_input) and
        #     prepend only the system prompt — no re-appending needed.
        all_stored = self._conv.get_messages()
        history_slice = all_stored[-40:] if len(all_stored) > 40 else all_stored
        messages_dicts = [{"role": "system", "content": system_prompt}, *history_slice]
        current_messages = [
            ModelMessage(role=m["role"], content=m["content"]) for m in messages_dicts
        ]

        # 5. Determine thinking config
        entry = self._factory.find_entry(model_id)
        session_thinking = self._conv.thinking_enabled
        use_thinking = (
            session_thinking
            if session_thinking is not None
            else (entry.thinking if entry is not None else False)
        )

        # 6. Build tool schemas for function calling
        tools_schema = self._build_tools_schema()

        # 7. Multi-round tool-calling loop
        # Mode can declare a higher round budget (e.g. explore=12, research=15).
        # self._max_tool_rounds is the constructor default; mode may raise it.
        effective_rounds = max(self._max_tool_rounds, mode.max_tool_rounds)
        full_response: list[str] = []
        # Track whether any thinking was emitted this round so we can close it.
        round_had_thinking = False

        for _round in range(effective_rounds):
            parser = ThinkingStreamParser() if use_thinking else None
            round_had_thinking = False

            request = ModelRequest(
                model_id=model_id,
                messages=current_messages,
                stream=True,
                temperature=turn_temperature,
                tools=tools_schema,
            )

            pending_tool_calls: list[dict] = []
            round_content: list[str] = []

            try:
                async with asyncio.timeout(300.0):  # 5-min hard cap; prevents hung streams
                    async for chunk in provider.stream_generate(request):
                        if self._cancelled:
                            break

                        # 7a. Native thinking field (Ollama gemma4 etc.)
                        if chunk.thinking and use_thinking:
                            round_had_thinking = True
                            await self._emit(
                                event_queue,
                                session_id,
                                run_id,
                                turn_id,
                                chunk.thinking,
                                is_thinking=True,
                            )

                        # 7b. Regular content (may contain <think> tags for tag-based models)
                        if chunk.content:
                            if parser is not None:
                                for is_thinking, text in parser.feed(chunk.content):
                                    if is_thinking:
                                        round_had_thinking = True
                                    await self._emit(
                                        event_queue, session_id, run_id, turn_id, text, is_thinking
                                    )
                                    if not is_thinking:
                                        round_content.append(text)
                            else:
                                round_content.append(chunk.content)
                                await event_queue.put(
                                    TokenEvent(
                                        session_id=session_id,
                                        run_id=run_id,
                                        turn_id=turn_id,
                                        token=chunk.content,
                                    )
                                )

                        # 7c. Accumulate tool calls
                        if chunk.tool_call_delta:
                            if isinstance(chunk.tool_call_delta, list):
                                pending_tool_calls.extend(chunk.tool_call_delta)
                            else:
                                pending_tool_calls.append(chunk.tool_call_delta)

            except asyncio.CancelledError:
                raise
            except TimeoutError:
                # asyncio.timeout() fired — stream hung for > 300 s.
                # Treat as a graceful partial response rather than a hard crash.
                timeout_text = "\n\n[Response timed out — partial output above]"
                round_content.append(timeout_text)
                await event_queue.put(
                    TokenEvent(
                        session_id=session_id,
                        run_id=run_id,
                        turn_id=turn_id,
                        token=timeout_text,
                    )
                )
                break  # exit the tool-calling loop with what we have
            except Exception as exc:
                runtime_logger.error(
                    "direct_runner_stream_error",
                    session_id=session_id,
                    run_id=run_id,
                    model_id=model_id,
                    error=str(exc),
                )
                error_text = f"\n\n[Error: {exc}]"
                round_content.append(error_text)
                await event_queue.put(
                    TokenEvent(
                        session_id=session_id,
                        run_id=run_id,
                        turn_id=turn_id,
                        token=error_text,
                    )
                )

            # 7d. Flush parser remnant and signal end-of-thinking.
            # Emit is_final=True so the TUI ThinkingBlock finalises immediately
            # rather than waiting until on_run_finished.
            if parser is not None:
                remnants = parser.flush()
                for is_thinking, text in remnants:
                    if text:
                        if is_thinking:
                            round_had_thinking = True
                        await self._emit(
                            event_queue, session_id, run_id, turn_id, text, is_thinking
                        )
                        if not is_thinking:
                            round_content.append(text)

            # Signal that the thinking block for this round is complete so the
            # TUI can finalise and map it to the following tool call.
            if round_had_thinking:
                await event_queue.put(
                    ThinkingEvent(
                        session_id=session_id,
                        run_id=run_id,
                        turn_id=turn_id,
                        token="",
                        is_final=True,
                    )
                )
                round_had_thinking = False

            full_response.extend(round_content)

            # 7e. No tool calls → done
            if not pending_tool_calls:
                break

            # 7f. Execute tool calls and build next round messages
            round_text = "".join(round_content)
            # Append assistant message with tool_calls
            current_messages.append(
                ModelMessage(
                    role="assistant",
                    content=round_text,
                    tool_calls=pending_tool_calls,
                )
            )

            tool_results = await self._execute_pending_tool_calls(
                pending_tool_calls,
                session_id=session_id,
                run_id=run_id,
                turn_id=turn_id,
                event_queue=event_queue,
            )
            for tc_id, result_text in tool_results:
                current_messages.append(
                    ModelMessage(
                        role="tool",
                        content=result_text,
                        tool_call_id=tc_id,
                    )
                )

        # 8. Synthesis pass.
        #
        # Runs when the tool-calling loop produced no visible text.  The root
        # cause is almost always that the last message in current_messages has
        # role="tool" — Ollama and every OpenAI-compatible API reject (or
        # silently return empty content for) a conversation ending with a tool
        # result unless followed by an explicit user turn.  We append one here.
        #
        # Layers of defence (each only activates if the previous layer produced
        # no visible text):
        #   L1 — Model call with explicit "please respond" user turn.
        #   L2 — Thinking-only fallback (models that route everything through
        #         chunk.thinking, e.g. Ollama gemma4 in thinking mode).
        #   L3 — Tool-results digest: format every tool result we collected into
        #         a readable response so the user always sees SOMETHING.
        if not any(t.strip() for t in full_response):
            # ── Build synthesis message list ──────────────────────────────────
            synth_messages = list(current_messages)

            # Every API requires the final message to be role="user".
            # If the conversation ends with tool results, append an explicit
            # instruction so the model knows to write a visible response now.
            if not synth_messages or synth_messages[-1].role != "user":
                synth_messages.append(
                    ModelMessage(
                        role="user",
                        content=(
                            "Based on the information and tool results above, "
                            "please provide a clear and complete answer."
                        ),
                    )
                )

            synth_request = ModelRequest(
                model_id=model_id,
                messages=synth_messages,
                stream=True,
                temperature=turn_temperature,
                tools=[],  # never pass tools — we want text, not more calls
            )

            # ── L1: stream synthesis response ─────────────────────────────────
            synth_parser = ThinkingStreamParser() if use_thinking else None
            synth_thinking_buf: list[str] = []
            synth_error: str = ""
            try:
                async for chunk in provider.stream_generate(synth_request):
                    if self._cancelled:
                        break
                    # Buffer native thinking — used only as L2 fallback.
                    # We do NOT emit ThinkingEvent here so there is no duplicate
                    # ThinkingBlock; this thinking text belongs to synthesis only.
                    if chunk.thinking:
                        synth_thinking_buf.append(chunk.thinking)
                    if chunk.content:
                        if synth_parser is not None:
                            for is_t, text in synth_parser.feed(chunk.content):
                                if text and not is_t:
                                    full_response.append(text)
                                    await event_queue.put(
                                        TokenEvent(
                                            session_id=session_id,
                                            run_id=run_id,
                                            turn_id=turn_id,
                                            token=text,
                                        )
                                    )
                        else:
                            full_response.append(chunk.content)
                            await event_queue.put(
                                TokenEvent(
                                    session_id=session_id,
                                    run_id=run_id,
                                    turn_id=turn_id,
                                    token=chunk.content,
                                )
                            )
                # Flush tag-parser remnant
                if synth_parser is not None:
                    for is_t, text in synth_parser.flush():
                        if text and not is_t:
                            full_response.append(text)
                            await event_queue.put(
                                TokenEvent(
                                    session_id=session_id,
                                    run_id=run_id,
                                    turn_id=turn_id,
                                    token=text,
                                )
                            )
            except Exception as exc:
                synth_error = str(exc)
                runtime_logger.error(
                    "direct_runner_synthesis_error",
                    session_id=session_id,
                    run_id=run_id,
                    error=synth_error,
                )

            # ── L2: thinking-only models ──────────────────────────────────────
            # Some models (gemma4, deepseek-r1 via Ollama) route their final
            # answer entirely through chunk.thinking.  Surface that text as the
            # visible response.  Safe: synthesis never emitted ThinkingEvent for
            # this text, so no ThinkingBlock duplication.
            if not any(t.strip() for t in full_response) and synth_thinking_buf:
                synth_text = "".join(synth_thinking_buf)
                full_response.append(synth_text)
                await event_queue.put(
                    TokenEvent(
                        session_id=session_id,
                        run_id=run_id,
                        turn_id=turn_id,
                        token=synth_text,
                    )
                )

            # ── L3: tool-results digest ───────────────────────────────────────
            # Synthesis failed entirely (model error, empty stream, or an API
            # that refused the request).  Rather than showing a blank response,
            # assemble the tool results from current_messages into a readable
            # digest so the user at least sees what was collected.
            if not any(t.strip() for t in full_response):
                digest = self._build_tool_digest(current_messages, synth_error)
                full_response.append(digest)
                await event_queue.put(
                    TokenEvent(
                        session_id=session_id,
                        run_id=run_id,
                        turn_id=turn_id,
                        token=digest,
                    )
                )

        # 9. Persist assistant reply (user message was already saved in step 4)
        assistant_reply = "".join(full_response)
        await self._conv.add_message("assistant", assistant_reply)

        # 10. Auto-persist research/explore findings to KB (best-effort)
        if mode.name in ("research", "explore") and len(assistant_reply) > 200:
            await self._auto_save_to_kb(user_input, assistant_reply, session_id, run_id)

        # 11. Post-turn skill improvement (best-effort, at most 1 skill per turn)
        if self._skill_improver is not None:
            try:
                active_skills_now = list(getattr(self._conv, "active_skills", None) or [])
                if active_skills_now and assistant_reply:
                    from citnega.packages.skills.builtins import BUILTIN_SKILL_INDEX
                    from citnega.packages.skills.impact_analyzer import SkillImpactAnalyzer
                    scores = SkillImpactAnalyzer().analyze(active_skills_now, assistant_reply, [])
                    for score in scores[:1]:
                        improved = await self._skill_improver.maybe_improve(  # type: ignore[union-attr]
                            score, user_input, assistant_reply
                        )
                        if improved and score.skill_name in BUILTIN_SKILL_INDEX:
                            BUILTIN_SKILL_INDEX[score.skill_name]["body"] = improved
            except Exception:
                pass

        runtime_logger.debug(
            "direct_runner_turn_complete",
            session_id=session_id,
            run_id=run_id,
            model_id=model_id,
            response_len=len(assistant_reply),
        )

        return run_id

    # ── Strategy context (mental models + skills) ─────────────────────────────

    # Token thresholds for progressive skill disclosure
    _SKILL_BUDGET_FULL = 4000      # full body
    _SKILL_BUDGET_SUMMARY = 1500   # name + first 3 bullet steps
    # Below summary threshold: name + triggers only (minimal)

    def _build_strategy_context(self, token_budget: int = 8000) -> str:
        """Return active skill bodies and mental model clauses as a prompt block."""
        try:
            parts: list[str] = []

            # Active skills (filtered by current mode)
            active_skills: list[str] = getattr(self._conv, "active_skills", None) or []
            current_mode = self._conv.mode_name
            if active_skills and self._capability_registry is not None:
                skill_bodies: list[str] = []
                per_skill_budget = token_budget // max(len(active_skills), 1)
                for skill_name in active_skills:
                    try:
                        descriptor = self._capability_registry.get_descriptor(
                            f"skill:{skill_name}"
                        )
                        if descriptor is None:
                            continue
                        supported = getattr(
                            getattr(descriptor, "runtime_object", None), "supported_modes", None
                        )
                        if supported and current_mode not in supported:
                            continue
                        body = getattr(
                            getattr(descriptor, "runtime_object", None), "body", None
                        )
                        if not body:
                            continue
                        if per_skill_budget >= self._SKILL_BUDGET_FULL:
                            content = body
                        elif per_skill_budget >= self._SKILL_BUDGET_SUMMARY:
                            lines = body.split("\n")
                            steps = [l for l in lines if l.strip() and l.strip()[0] in "-1234567890"][:3]
                            content = "\n".join(steps) + f"\n...(full: /skill {skill_name})" if steps else body[:300]
                        else:
                            triggers_obj = getattr(getattr(descriptor, "runtime_object", None), "triggers", [])
                            trig_str = ", ".join(list(triggers_obj)[:3]) if triggers_obj else ""
                            content = f"Skill active: {skill_name}" + (f". Triggers: {trig_str}" if trig_str else "")
                        skill_bodies.append(f"### Skill: {skill_name}\n{content}")
                    except Exception:
                        continue
                if skill_bodies:
                    parts.append("## Active Skills\n\n" + "\n\n".join(skill_bodies))

            # Mental model clauses + negations
            mental_model_spec = getattr(self._conv, "mental_model_spec", None)
            if mental_model_spec is not None:
                clauses = getattr(mental_model_spec, "clauses", None) or []
                if clauses:
                    clause_lines = "\n".join(f"- {getattr(c, 'text', str(c))}" for c in clauses)
                    parts.append(f"## Behavioral Guidelines\n\n{clause_lines}")
                negations = getattr(mental_model_spec, "negations", None) or []
                if negations:
                    neg_lines = "\n".join(f"- {n}" for n in negations)
                    parts.append(f"## Behavioral Prohibitions\n\n{neg_lines}")

            if not parts:
                return ""
            return "\n\n" + "\n\n".join(parts)
        except Exception:
            return ""

    # ── Ambient workspace context ─────────────────────────────────────────────

    @staticmethod
    def _build_ambient_context(cwd: str | None = None) -> str:
        """Return a formatted block with cwd, git branch, git status, and time."""
        try:
            work_dir = cwd or os.getcwd()
            now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

            branch = ""
            try:
                result = subprocess.run(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    cwd=work_dir,
                )
                if result.returncode == 0:
                    branch = result.stdout.strip()
            except Exception:
                pass

            status_summary = ""
            try:
                result = subprocess.run(
                    ["git", "status", "--short"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    cwd=work_dir,
                )
                if result.returncode == 0:
                    lines = [l for l in result.stdout.splitlines() if l.strip()]
                    if lines:
                        status_summary = f"{len(lines)} changed file(s)"
                        sample = ", ".join(l.strip() for l in lines[:5])
                        status_summary += f" ({sample}{'…' if len(lines) > 5 else ''})"
                    else:
                        status_summary = "clean"
            except Exception:
                pass

            lines = [f"- Working directory: {work_dir}", f"- Current time: {now_str}"]
            if branch:
                lines.append(f"- Git branch: {branch}")
            if status_summary:
                lines.append(f"- Git status: {status_summary}")

            return (
                "\n\n---\n**Workspace context (auto-injected):**\n"
                + "\n".join(lines)
                + "\n---"
            )
        except Exception:
            return ""

    # ── Auto-save research/explore results to KB ──────────────────────────────

    async def _auto_save_to_kb(
        self,
        query: str,
        reply: str,
        session_id: str,
        run_id: str,
    ) -> None:
        """Persist a truncated summary of research/explore output to the KB."""
        try:
            kb_tool = self._all_callables.get("write_kb") or self._tools.get("write_kb")
            if kb_tool is None:
                return
            title = query[:80].replace("\n", " ").strip()
            summary = reply[:1000]
            from citnega.packages.tools.builtin.write_kb import WriteKBInput  # type: ignore[import]
            from citnega.packages.protocol.callables.context import CallContext

            gateway = self._model_gateway or (
                _RunnerModelGateway(self._factory, self._current_model_id)
                if self._current_model_id
                else None
            )
            ctx = CallContext(
                session_id=session_id,
                run_id=run_id,
                turn_id="auto_save",
                depth=1,
                session_config=self._session.config,
                model_gateway=gateway,
                capability_registry=self._capability_registry,
            )
            await kb_tool.invoke(WriteKBInput(title=title, content=summary), ctx)
        except Exception:
            pass  # KB write failures must never crash a turn

    async def _execute_pending_tool_calls(
        self,
        pending_tool_calls: list[dict],
        *,
        session_id: str,
        run_id: str,
        turn_id: str,
        event_queue: asyncio.Queue,
    ) -> list[tuple[str, str]]:
        if not pending_tool_calls:
            return []

        if self._parallel_tool_execution_enabled() and self._can_fan_out_tool_calls(pending_tool_calls):
            results_by_id: dict[str, str] = {}

            async def _run_one(tool_call: dict) -> None:
                tc_id, result_text = await self._execute_tool_call_delta(
                    tool_call,
                    session_id=session_id,
                    run_id=run_id,
                    turn_id=turn_id,
                    event_queue=event_queue,
                )
                results_by_id[tc_id] = result_text

            async with asyncio.TaskGroup() as task_group:
                for tool_call in pending_tool_calls:
                    task_group.create_task(_run_one(tool_call))

            return [
                (self._tool_call_id(tool_call), results_by_id[self._tool_call_id(tool_call)])
                for tool_call in pending_tool_calls
            ]

        results: list[tuple[str, str]] = []
        for tool_call in pending_tool_calls:
            results.append(
                await self._execute_tool_call_delta(
                    tool_call,
                    session_id=session_id,
                    run_id=run_id,
                    turn_id=turn_id,
                    event_queue=event_queue,
                )
            )
        return results

    async def _execute_tool_call_delta(
        self,
        tool_call: dict,
        *,
        session_id: str,
        run_id: str,
        turn_id: str,
        event_queue: asyncio.Queue,
    ) -> tuple[str, str]:
        fn = tool_call.get("function", {}) if isinstance(tool_call, dict) else {}
        name = fn.get("name", "")
        raw_args = fn.get("arguments", "{}")
        if isinstance(raw_args, dict):
            args = json.dumps(raw_args)
        else:
            args = raw_args or "{}"
        tc_id = self._tool_call_id(tool_call)
        result_text = await self._execute_tool(
            name, args, session_id, run_id, turn_id, event_queue
        )
        return tc_id, result_text

    @staticmethod
    def _tool_call_id(tool_call: dict) -> str:
        return (
            tool_call.get("id", str(uuid.uuid4()))
            if isinstance(tool_call, dict)
            else str(uuid.uuid4())
        )

    def _parallel_tool_execution_enabled(self) -> bool:
        try:
            return load_settings().nextgen.parallel_execution_enabled
        except Exception:
            return False

    def _can_fan_out_tool_calls(self, pending_tool_calls: list[dict]) -> bool:
        seen_scopes: set[str] = set()
        for tool_call in pending_tool_calls:
            fn = tool_call.get("function", {}) if isinstance(tool_call, dict) else {}
            name = str(fn.get("name", "")).strip()
            callable_obj = self._tools.get(name) or self._all_callables.get(name)
            if callable_obj is None:
                return False
            try:
                descriptor = callable_to_descriptor(callable_obj, source="runtime")
            except Exception:
                return False
            if not descriptor.execution_traits.parallel_safe:
                return False
            args = self._safe_json_load(fn.get("arguments", "{}"))
            scope = self._tool_call_scope(name, args)
            if scope and scope in seen_scopes:
                return False
            if scope:
                seen_scopes.add(scope)
        return True

    @staticmethod
    def _safe_json_load(raw_args: object) -> dict[str, Any]:
        if isinstance(raw_args, dict):
            return raw_args
        try:
            decoded = json.loads(raw_args or "{}")
        except Exception:
            return {}
        return decoded if isinstance(decoded, dict) else {}

    @staticmethod
    def _tool_call_scope(name: str, args: dict[str, Any]) -> str:
        for key in ("file_path", "path", "working_dir", "root_path"):
            value = args.get(key)
            if isinstance(value, str) and value.strip():
                return f"{name}:{os.path.abspath(value)}"
        return name if name in {"run_shell", "git_ops", "write_file", "edit_file"} else ""

    # ── Tool calling helpers ──────────────────────────────────────────────────

    def _build_tools_schema(self) -> list[dict]:
        """Convert registered tools to OpenAI function-calling schema."""
        if not self._tools:
            return []
        schemas = []
        for tool in self._tools.values():
            try:
                meta = tool.get_metadata()
                # Keep only the fields Ollama/OpenAI expect
                params = {
                    k: v
                    for k, v in meta.input_schema_json.items()
                    if k in ("type", "properties", "required", "description")
                }
                schemas.append(
                    {
                        "type": "function",
                        "function": {
                            "name": meta.name,
                            "description": meta.description,
                            "parameters": params,
                        },
                    }
                )
            except Exception:
                pass
        return schemas

    async def _execute_tool(
        self,
        name: str,
        args_str: str,
        session_id: str,
        run_id: str,
        turn_id: str,
        event_queue: asyncio.Queue,
    ) -> str:
        """Execute a registered callable by name and return its string result.

        Looks in self._tools first (LLM-accessible).  For agent sub-calls that
        need web tools not in self._tools, falls back to self._all_callables.
        """
        tool = self._tools.get(name) or self._all_callables.get(name)
        if tool is None:
            return f"[Tool error: '{name}' not registered]"

        try:
            args = json.loads(args_str) if args_str else {}
        except json.JSONDecodeError:
            args = {}

        try:
            input_obj = tool.input_schema.model_validate(args)
            # Build a minimal CallContext for tool/specialist execution.
            # Specialists need a working model gateway to make their own model calls.
            # NOTE: We do NOT manually emit CallableStart/EndEvent here.
            # BaseCallable.invoke() emits them via the injected event_emitter, which
            # shares the same underlying asyncio.Queue as event_queue (both route by
            # run_id through the EventEmitter). Manual emission would cause duplicate
            # sidebar blocks in the TUI.
            from citnega.packages.protocol.callables.context import CallContext

            # Prefer the injected full ModelGateway (routing + rate-limiting).
            # Fall back to the thin _RunnerModelGateway wrapper when not available.
            gateway = self._model_gateway or (
                _RunnerModelGateway(self._factory, self._current_model_id)
                if self._current_model_id
                else None
            )
            ctx = CallContext(
                session_id=session_id,
                run_id=run_id,
                turn_id=turn_id,
                depth=1,
                session_config=self._session.config,
                model_gateway=gateway,
                capability_registry=self._capability_registry,
                mode_temperature=get_mode(self._conv.mode_name).temperature,
            )
            result = await tool.invoke(input_obj, ctx)
            if result.success and result.output:
                # For specialist agents, prefer a plain-text field over the full JSON
                # blob — feeding raw JSON to a local LLM produces garbled/empty replies.
                output_text = None
                for field in ("response", "result", "content", "summary", "output"):
                    val = getattr(result.output, field, None)
                    if val and isinstance(val, str):
                        output_text = val
                        break
                if output_text is None:
                    output_text = result.output.model_dump_json()
            elif result.error:
                output_text = f"[Tool error: {result.error.message}]"
            else:
                output_text = ""
        except Exception as exc:
            output_text = f"[Tool execution error: {exc}]"

        return output_text

    # ── IFrameworkRunner stubs ────────────────────────────────────────────────

    async def pause(self, run_id: str) -> None:
        self._paused = True

    async def resume(self, run_id: str) -> None:
        self._paused = False

    async def cancel(self, run_id: str) -> None:
        self._cancelled = True

    async def get_state_snapshot(self) -> StateSnapshot:
        return StateSnapshot(
            session_id=self._session.config.session_id,
            current_run_id=None,
            active_callable=None,
            run_state=RunState.EXECUTING,
            context_token_count=0,
            checkpoint_available=False,
            framework_name="direct",
            captured_at=datetime.now(tz=UTC),
        )

    async def save_checkpoint(self, run_id: str) -> CheckpointMeta:
        return CheckpointMeta(
            checkpoint_id=str(uuid.uuid4()),
            session_id=self._session.config.session_id,
            run_id=run_id,
            created_at=datetime.now(tz=UTC),
            framework_name="direct",
            file_path="/dev/null",
            size_bytes=0,
            state_summary="{}",
        )

    async def restore_checkpoint(self, checkpoint_id: str) -> None:
        pass

    # ── IFrameworkRunner typed accessors ─────────────────────────────────────

    def get_active_model_id(self) -> str | None:
        return self._conv.active_model_id

    def get_mode(self) -> str:
        return self._conv.mode_name

    def set_plan_phase(self, phase: str | None) -> None:
        self._conv.set_plan_phase(phase or "draft")

    def get_plan_phase(self) -> str:
        return self._conv.plan_phase

    async def set_mode(self, mode_name: str) -> None:
        await self._conv.set_mode(mode_name)

    async def set_model(self, model_id: str) -> None:
        await self._conv.set_active_model(model_id)

    async def set_thinking(self, value: bool | None) -> None:
        await self._conv.set_thinking_enabled(value)

    def get_thinking(self) -> bool | None:
        return self._conv.thinking_enabled

    def get_conversation_stats(self) -> ConversationStats:
        from citnega.packages.protocol.models.runner import ConversationStats as _CS

        return _CS(
            message_count=self._conv.message_count,
            token_estimate=self._conv.token_estimate,
            compaction_count=self._conv.compaction_count,
        )

    def get_messages(self) -> list[dict[str, Any]]:
        return self._conv.get_messages()

    def get_tool_history(self) -> list[dict[str, Any]]:
        return self._conv.get_tool_history()

    def get_active_skills(self) -> list[str]:
        return self._conv.active_skills

    def set_active_skills(self, skill_names: list[str]) -> None:
        self._conv.set_active_skills(skill_names)

    def get_mental_model_spec(self) -> dict[str, Any] | None:
        return self._conv.mental_model_spec

    def set_mental_model_spec(self, spec: dict[str, Any] | None) -> None:
        self._conv.set_mental_model_spec(spec)

    def get_compiled_plan_metadata(self) -> dict[str, Any]:
        return self._conv.compiled_plan_metadata

    def set_compiled_plan_metadata(self, metadata: dict[str, Any] | None) -> None:
        self._conv.set_compiled_plan_metadata(metadata)

    async def add_tool_call(
        self,
        name: str,
        input_summary: str,
        output_summary: str,
        success: bool,
        callable_type: str = "tool",
        msg_count: int | None = None,
    ) -> None:
        await self._conv.add_tool_call(
            name, input_summary, output_summary, success,
            callable_type=callable_type, msg_count=msg_count,
        )

    async def compact(self, summary: str, *, keep_recent: int = 10) -> int:
        return await self._conv.compact(summary, keep_recent=keep_recent)

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _build_tool_digest(messages: list[ModelMessage], error: str = "") -> str:
        """
        Build a human-readable summary of tool calls and results from the
        message history.  Used as the L3 fallback when model synthesis fails.
        """
        lines: list[str] = []
        i = 0
        tool_index = 0
        while i < len(messages):
            msg = messages[i]
            if msg.role == "assistant" and msg.tool_calls:
                for tc in msg.tool_calls:
                    fn = tc.get("function", {}) if isinstance(tc, dict) else {}
                    name = fn.get("name") or "unknown_tool"
                    raw_args = fn.get("arguments", "{}")
                    try:
                        args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                        args_preview = ", ".join(
                            f"{k}={str(v)[:60]}" for k, v in (args or {}).items()
                        )
                    except Exception:
                        args_preview = str(raw_args)[:80]
                    tool_index += 1
                    lines.append(f"**{tool_index}. {name}**({args_preview})")
            elif msg.role == "tool" and msg.content:
                result = msg.content.strip()
                if len(result) > 400:
                    result = result[:400] + " …"
                lines.append(f"   → {result}")
            i += 1

        if not lines:
            if error:
                return f"*(Model did not produce a response. Error: {error})*"
            return "*(Tool calls completed — model did not produce a summary.)*"

        header = "**Tool results:**\n\n"
        if error:
            header = f"*(Synthesis failed: {error})*\n\n**Tool results:**\n\n"
        return header + "\n\n".join(lines)

    def _resolve_provider(self, model_id: str):
        """Return (provider, effective_model_id) with best-effort fallback."""
        try:
            return self._factory.build(model_id), model_id
        except KeyError:
            entries = self._factory.list_entries()
            if not entries:
                raise RuntimeError(f"Model '{model_id}' not found and no fallback available.")
            fallback_id = entries[0].id
            runtime_logger.warning(
                "direct_runner_model_fallback",
                requested=model_id,
                fallback=fallback_id,
            )
            return self._factory.build(fallback_id), fallback_id

    @staticmethod
    async def _emit(
        queue: asyncio.Queue,
        session_id: str,
        run_id: str,
        turn_id: str,
        text: str,
        is_thinking: bool,
    ) -> None:
        if is_thinking:
            await queue.put(
                ThinkingEvent(
                    session_id=session_id,
                    run_id=run_id,
                    turn_id=turn_id,
                    token=text,
                )
            )
        else:
            await queue.put(
                TokenEvent(
                    session_id=session_id,
                    run_id=run_id,
                    turn_id=turn_id,
                    token=text,
                )
            )
