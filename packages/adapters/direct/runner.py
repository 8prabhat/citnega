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
from typing import TYPE_CHECKING, Any
import uuid

from citnega.packages.model_gateway.provider_factory import ProviderFactory
from citnega.packages.observability.logging_setup import runtime_logger
from citnega.packages.protocol.events.streaming import TokenEvent
from citnega.packages.protocol.events.thinking import ThinkingEvent
from citnega.packages.protocol.interfaces.adapter import IFrameworkRunner
from citnega.packages.protocol.models.checkpoints import CheckpointMeta
from citnega.packages.protocol.models.model_gateway import ModelMessage, ModelRequest
from citnega.packages.protocol.models.runs import RunState, StateSnapshot
from citnega.packages.runtime.context.conversation_store import ConversationStore
from citnega.packages.runtime.session_modes import get_mode
from citnega.packages.runtime.thinking_parser import ThinkingStreamParser

if TYPE_CHECKING:
    from citnega.packages.model_gateway.yaml_config import ModelYAMLConfig
    from citnega.packages.protocol.callables.interfaces import IInvocable
    from citnega.packages.protocol.events import CanonicalEvent
    from citnega.packages.protocol.models.context import ContextObject
    from citnega.packages.protocol.models.model_gateway import ModelRequest, ModelResponse
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
        # Specialists called by the runner use generate(); streaming not needed here.
        raise NotImplementedError("stream_generate not supported in _RunnerModelGateway")

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
        phase = self._conv.plan_phase
        base_prompt = (
            ConversationStore._SYSTEM_PROMPT
            + ConversationStore.build_tools_section(self._tools)
        )
        try:
            system_prompt = mode.augment_system_prompt(base_prompt, phase=phase)
        except TypeError:
            system_prompt = mode.augment_system_prompt(base_prompt)

        # 3b. Inject KB context sources into the system prompt
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
        full_response: list[str] = []

        for _round in range(self._max_tool_rounds):
            parser = ThinkingStreamParser() if use_thinking else None

            request = ModelRequest(
                model_id=model_id,
                messages=current_messages,
                stream=True,
                temperature=0.7,
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

            # 7d. Flush parser remnant
            if parser is not None:
                for is_thinking, text in parser.flush():
                    if text:
                        await self._emit(
                            event_queue, session_id, run_id, turn_id, text, is_thinking
                        )
                        if not is_thinking:
                            round_content.append(text)

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

            for tc in pending_tool_calls:
                fn = tc.get("function", {}) if isinstance(tc, dict) else {}
                name = fn.get("name", "")
                raw_args = fn.get("arguments", "{}")
                # Ollama may return arguments as a dict already; normalise to JSON string
                if isinstance(raw_args, dict):
                    args = json.dumps(raw_args)
                else:
                    args = raw_args or "{}"
                tc_id = (
                    tc.get("id", str(uuid.uuid4())) if isinstance(tc, dict) else str(uuid.uuid4())
                )

                result_text = await self._execute_tool(
                    name, args, session_id, run_id, turn_id, event_queue
                )
                current_messages.append(
                    ModelMessage(
                        role="tool",
                        content=result_text,
                        tool_call_id=tc_id,
                    )
                )

        # 8. Persist assistant reply (user message was already saved in step 4)
        assistant_reply = "".join(full_response)
        await self._conv.add_message("assistant", assistant_reply)

        runtime_logger.debug(
            "direct_runner_turn_complete",
            session_id=session_id,
            run_id=run_id,
            model_id=model_id,
            response_len=len(assistant_reply),
        )

        return run_id

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
            )
            result = await tool.invoke(input_obj, ctx)
            if result.success and result.output:
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
        self._conv.set_plan_phase(phase)

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

    async def add_tool_call(
        self,
        name: str,
        input_summary: str,
        output_summary: str,
        success: bool,
        callable_type: str = "tool",
    ) -> None:
        await self._conv.add_tool_call(
            name, input_summary, output_summary, success, callable_type=callable_type
        )

    async def compact(self, summary: str, *, keep_recent: int = 10) -> int:
        return await self._conv.compact(summary, keep_recent=keep_recent)

    # ── Private helpers ───────────────────────────────────────────────────────

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
