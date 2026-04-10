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
import json
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from citnega.packages.model_gateway.provider_factory import ProviderFactory
from citnega.packages.model_gateway.yaml_config import ModelYAMLConfig
from citnega.packages.observability.logging_setup import runtime_logger
from citnega.packages.protocol.events import CanonicalEvent
from citnega.packages.protocol.events.callable import CallableEndEvent, CallableStartEvent
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
    from citnega.packages.protocol.callables.interfaces import IInvocable
    from citnega.packages.protocol.models.context import ContextObject
    from citnega.packages.protocol.models.sessions import Session

_MAX_TOOL_ROUNDS = 5   # prevent infinite tool-call loops


class DirectModelRunner(IFrameworkRunner):
    """
    Thin runner that talks directly to an IModelProvider.

    One instance per session, created by DirectModelAdapter.
    Supports multi-round tool calling with registered IInvocable tools.
    """

    def __init__(
        self,
        session: "Session",
        yaml_config: ModelYAMLConfig,
        conversation_store: ConversationStore,
        callables: "list[IInvocable] | None" = None,
    ) -> None:
        self._session   = session
        self._factory   = ProviderFactory(yaml_config)
        self._conv      = conversation_store
        self._cancelled = False
        self._paused    = False
        # Only expose TOOL-type callables to the model for function calling
        from citnega.packages.protocol.callables.types import CallableType  # noqa: PLC0415
        self._tools: dict[str, IInvocable] = {
            c.name: c for c in (callables or [])
            if hasattr(c, "callable_type") and c.callable_type == CallableType.TOOL
        }

    # ── IFrameworkRunner ──────────────────────────────────────────────────────

    async def run_turn(
        self,
        user_input: str,
        context: "ContextObject",
        event_queue: asyncio.Queue[CanonicalEvent],
    ) -> str:
        if self._cancelled:
            raise asyncio.CancelledError("runner was cancelled")

        session_id = self._session.config.session_id
        run_id     = context.run_id
        turn_id    = str(uuid.uuid4())

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

        # 3. Augment system prompt with session mode + phase
        mode  = get_mode(self._conv.mode_name)
        phase = self._conv.plan_phase
        try:
            system_prompt = mode.augment_system_prompt(ConversationStore._SYSTEM_PROMPT, phase=phase)
        except TypeError:
            system_prompt = mode.augment_system_prompt(ConversationStore._SYSTEM_PROMPT)

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

        # 4. Build initial message list
        messages_dicts = self._conv.build_messages_for_model(
            user_input, system_prompt=system_prompt
        )
        current_messages = [
            ModelMessage(role=m["role"], content=m["content"])
            for m in messages_dicts
        ]

        # 5. Determine thinking config
        entry            = self._factory.find_entry(model_id)
        session_thinking = self._conv.thinking_enabled
        use_thinking     = session_thinking if session_thinking is not None else (
            entry.thinking if entry is not None else False
        )

        # 6. Build tool schemas for function calling
        tools_schema = self._build_tools_schema()

        # 7. Multi-round tool-calling loop
        full_response: list[str] = []

        for _round in range(_MAX_TOOL_ROUNDS):
            parser = ThinkingStreamParser() if use_thinking else None

            request = ModelRequest(
                model_id=model_id,
                messages=current_messages,
                stream=True,
                temperature=0.7,
                tools=tools_schema,
            )

            pending_tool_calls: list[dict] = []
            round_content:      list[str]  = []

            try:
                async for chunk in provider.stream_generate(request):
                    if self._cancelled:
                        break

                    # 7a. Native thinking field (Ollama gemma4 etc.)
                    if chunk.thinking and use_thinking:
                        await self._emit(event_queue, session_id, run_id, turn_id,
                                         chunk.thinking, is_thinking=True)

                    # 7b. Regular content (may contain <think> tags for tag-based models)
                    if chunk.content:
                        if parser is not None:
                            for is_thinking, text in parser.feed(chunk.content):
                                await self._emit(event_queue, session_id, run_id, turn_id,
                                                 text, is_thinking)
                                if not is_thinking:
                                    round_content.append(text)
                        else:
                            round_content.append(chunk.content)
                            await event_queue.put(TokenEvent(
                                session_id=session_id,
                                run_id=run_id,
                                turn_id=turn_id,
                                token=chunk.content,
                            ))

                    # 7c. Accumulate tool calls
                    if chunk.tool_call_delta:
                        if isinstance(chunk.tool_call_delta, list):
                            pending_tool_calls.extend(chunk.tool_call_delta)
                        else:
                            pending_tool_calls.append(chunk.tool_call_delta)

            except asyncio.CancelledError:
                raise
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
                await event_queue.put(TokenEvent(
                    session_id=session_id, run_id=run_id, turn_id=turn_id, token=error_text,
                ))

            # 7d. Flush parser remnant
            if parser is not None:
                for is_thinking, text in parser.flush():
                    if text:
                        await self._emit(event_queue, session_id, run_id, turn_id,
                                         text, is_thinking)
                        if not is_thinking:
                            round_content.append(text)

            full_response.extend(round_content)

            # 7e. No tool calls → done
            if not pending_tool_calls:
                break

            # 7f. Execute tool calls and build next round messages
            round_text = "".join(round_content)
            # Append assistant message with tool_calls
            current_messages.append(ModelMessage(
                role="assistant",
                content=round_text,
                tool_calls=pending_tool_calls,
            ))

            for tc in pending_tool_calls:
                fn      = tc.get("function", {}) if isinstance(tc, dict) else {}
                name    = fn.get("name", "")
                args    = fn.get("arguments", "{}")
                tc_id   = tc.get("id", str(uuid.uuid4())) if isinstance(tc, dict) else str(uuid.uuid4())

                result_text = await self._execute_tool(
                    name, args, session_id, run_id, turn_id, event_queue
                )
                current_messages.append(ModelMessage(
                    role="tool",
                    content=result_text,
                    tool_call_id=tc_id,
                ))

        # 8. Persist turn
        assistant_reply = "".join(full_response)
        await self._conv.add_message("user", user_input)
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
                meta   = tool.get_metadata()
                # Keep only the fields Ollama/OpenAI expect
                params = {
                    k: v for k, v in meta.input_schema_json.items()
                    if k in ("type", "properties", "required", "description")
                }
                schemas.append({
                    "type": "function",
                    "function": {
                        "name":        meta.name,
                        "description": meta.description,
                        "parameters":  params,
                    },
                })
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
        """Execute a registered tool by name and return its string result."""
        tool = self._tools.get(name)
        if tool is None:
            return f"[Tool error: '{name}' not registered]"

        # Emit CallableStartEvent so TUI shows a ToolCallBlock
        await event_queue.put(CallableStartEvent(
            session_id=session_id,
            run_id=run_id,
            turn_id=turn_id,
            callable_name=name,
            callable_type=tool.callable_type,
            input_summary=args_str[:128],
            depth=1,
            parent_callable=None,
        ))

        try:
            args = json.loads(args_str) if args_str else {}
        except json.JSONDecodeError:
            args = {}

        try:
            input_obj = tool.input_schema.model_validate(args)
            # Build a minimal CallContext for tool execution
            from citnega.packages.protocol.callables.context import CallContext  # noqa: PLC0415
            ctx = CallContext(
                session_id=session_id,
                run_id=run_id,
                turn_id=turn_id,
                depth=1,
                session_config=self._session.config,
                model_gateway=None,
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

        # Emit CallableEndEvent
        await event_queue.put(CallableEndEvent(
            session_id=session_id,
            run_id=run_id,
            turn_id=turn_id,
            callable_name=name,
            callable_type=tool.callable_type,
            output_summary=output_text[:128],
            duration_ms=0,
            policy_result="passed" if not output_text.startswith("[Tool error") else "failed",
        ))

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
            captured_at=datetime.now(tz=timezone.utc),
        )

    async def save_checkpoint(self, run_id: str) -> CheckpointMeta:
        return CheckpointMeta(
            checkpoint_id=str(uuid.uuid4()),
            session_id=self._session.config.session_id,
            run_id=run_id,
            created_at=datetime.now(tz=timezone.utc),
            framework_name="direct",
            file_path="/dev/null",
            size_bytes=0,
            state_summary="{}",
        )

    async def restore_checkpoint(self, checkpoint_id: str) -> None:
        pass

    # ── Model / mode switching (called by adapter) ────────────────────────────

    async def set_model(self, model_id: str) -> None:
        await self._conv.set_active_model(model_id)

    async def set_mode(self, mode_name: str) -> None:
        await self._conv.set_mode(mode_name)

    def set_plan_phase(self, phase: str) -> None:
        self._conv.set_plan_phase(phase)

    async def set_thinking(self, value: bool | None) -> None:
        await self._conv.set_thinking_enabled(value)

    def get_thinking(self) -> bool | None:
        return self._conv.thinking_enabled

    # ── Private helpers ───────────────────────────────────────────────────────

    def _resolve_provider(self, model_id: str):
        """Return (provider, effective_model_id) with best-effort fallback."""
        try:
            return self._factory.build(model_id), model_id
        except KeyError:
            entries = self._factory.list_entries()
            if not entries:
                raise RuntimeError(
                    f"Model '{model_id}' not found and no fallback available."
                )
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
            await queue.put(ThinkingEvent(
                session_id=session_id, run_id=run_id, turn_id=turn_id, token=text,
            ))
        else:
            await queue.put(TokenEvent(
                session_id=session_id, run_id=run_id, turn_id=turn_id, token=text,
            ))
