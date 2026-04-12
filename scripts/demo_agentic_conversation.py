"""
demo_agentic_conversation.py
============================
Live agentic conversation that runs through the REAL Citnega pipeline:
  - Real Ollama LLM (qwen3-coder:30b by default)
  - Real tool calling: list_dir → search_files → read_file (driven by the model)
  - Real specialist agent (ResearchSynthesizerAgent) that calls tools itself
  - All canonical events printed live as they stream from the event queue

Usage::

    .venv/bin/python3 scripts/demo_agentic_conversation.py
    .venv/bin/python3 scripts/demo_agentic_conversation.py --model gemma4-26b-local
    .venv/bin/python3 scripts/demo_agentic_conversation.py --model qwen3-coder-30b-local
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import textwrap
import uuid
from pathlib import Path
from typing import AsyncIterator

# ── repo root on path ──────────────────────────────────────────────────────────
_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from pydantic import BaseModel, Field

from citnega.packages.agents.specialists._specialist_base import SpecialistBase, SpecialistOutput
from citnega.packages.protocol.callables.context import CallContext
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType
from citnega.packages.protocol.events.callable import CallableEndEvent, CallableStartEvent
from citnega.packages.protocol.events.lifecycle import RunCompleteEvent, RunStateEvent
from citnega.packages.protocol.events.streaming import TokenEvent
from citnega.packages.protocol.events.thinking import ThinkingEvent
from citnega.packages.protocol.models.sessions import SessionConfig

# ── ANSI colours ──────────────────────────────────────────────────────────────
RST  = "\033[0m";  BOLD = "\033[1m";  DIM  = "\033[2m"
CYN  = "\033[36m"; GRN  = "\033[32m"; YLW  = "\033[33m"
RED  = "\033[31m"; BLU  = "\033[34m"; MGT  = "\033[35m"

def _hr(w=72): print(DIM + "─" * w + RST)
def _section(t, c=CYN): print(); _hr(); print(c + BOLD + f"  {t}" + RST); _hr()


# ── Specialist agent (calls tools directly — no model gateway needed) ─────────

class ResearchInput(BaseModel):
    topic: str = Field(description="Topic to research in the codebase.")

class ResearchSynthesizerAgent(SpecialistBase):
    """
    Specialist that wires together list_dir + search_files + read_file and
    synthesises the findings into a report — no live LLM required for itself.
    """
    name          = "research_synthesizer"
    description   = "Researches citnega source code and synthesizes findings."
    callable_type = CallableType.SPECIALIST
    input_schema  = ResearchInput
    output_schema = SpecialistOutput
    policy        = CallablePolicy(timeout_seconds=60.0, requires_approval=False)
    SYSTEM_PROMPT  = "You synthesize code research into concise reports."
    TOOL_WHITELIST = ["list_dir", "search_files", "read_file"]

    async def _execute(self, input: ResearchInput, context: CallContext) -> SpecialistOutput:
        tools_used: list[str] = []
        findings:   list[str] = []
        builtin = _REPO / "packages" / "tools" / "builtin"

        # 1 — list the tools directory
        tool = self._get_tool("list_dir")
        if tool:
            r = await tool.invoke(tool.input_schema(dir_path=str(builtin)), context)
            if r.success:
                tools_used.append("list_dir")
                findings.append("Directory:\n" + r.output.result[:400])

        # 2 — find every BaseCallable subclass
        tool = self._get_tool("search_files")
        if tool:
            r = await tool.invoke(
                tool.input_schema(
                    root_path=str(builtin),
                    pattern=r"class \w+\(BaseCallable\)",
                    glob_filter="*.py",
                    max_results=20,
                ),
                context,
            )
            if r.success:
                tools_used.append("search_files")
                findings.append("BaseCallable subclasses:\n" + r.output.result[:600])

        # 3 — read search_web.py
        tool = self._get_tool("read_file")
        if tool:
            r = await tool.invoke(
                tool.input_schema(file_path=str(builtin / "search_web.py"), max_bytes=1800),
                context,
            )
            if r.success:
                tools_used.append("read_file")
                findings.append("search_web.py:\n" + r.output.result[:800])

        report = (
            f"[ResearchSynthesizerAgent] Report on '{input.topic}'\n\n"
            + "\n\n---\n\n".join(findings)
            + f"\n\nTools invoked: {', '.join(tools_used)}"
        )
        return SpecialistOutput(response=report, tool_calls_made=tools_used)


# ── Stub policy / emitter / tracer (no side effects) ─────────────────────────

class _Enforcer:
    async def enforce(self, *a, **k): pass
    async def run_with_timeout(self, c, coro, *a, **k): return await coro
    async def check_output_size(self, *a, **k): pass

class _Emitter:
    def __init__(self): self.events = []
    def emit(self, e): self.events.append(e)

class _Tracer:
    def record(self, *a, **k): pass


def _mk_tool(cls, em=None):
    em = em or _Emitter()
    return cls(_Enforcer(), em, _Tracer())


# ── Live event printer ─────────────────────────────────────────────────────────

class LivePrinter:
    """Consumes the ApplicationService event stream and prints as they arrive."""

    def __init__(self):
        self._response_chars = 0
        self._thinking_chars = 0
        self._tool_cols: dict[str, int] = {}  # name → start col for progress

    async def stream(self, service, run_id: str) -> str:
        """Print events live; return full response text."""
        full_response: list[str] = []
        thinking_buf:  list[str] = []
        in_thinking = False

        async for event in service.stream_events(run_id):
            if isinstance(event, ThinkingEvent):
                if not in_thinking:
                    print(DIM + "\n  ◌ thinking…  " + RST, end="", flush=True)
                    in_thinking = True
                thinking_buf.append(event.token)
                if event.is_final:
                    total = sum(len(t) for t in thinking_buf)
                    print(DIM + f"[{total} chars]" + RST, flush=True)
                    thinking_buf.clear()
                    in_thinking = False

            elif isinstance(event, TokenEvent):
                if in_thinking:
                    print()
                    in_thinking = False
                token = event.token
                print(GRN + token + RST, end="", flush=True)
                full_response.append(token)

            elif isinstance(event, CallableStartEvent):
                name = event.callable_name or "?"
                summary = (event.input_summary or "")[:72]
                print(
                    f"\n\n  {YLW}⚙  TOOL CALLED:{RST} {BOLD}{name}{RST}"
                    f"\n     {DIM}args: {summary}{RST}"
                )

            elif isinstance(event, CallableEndEvent):
                name = event.callable_name or "?"
                ok   = event.error_code is None
                icon = f"{GRN}✔{RST}" if ok else f"{RED}✗{RST}"
                out  = (event.output_summary or "")[:80]
                print(
                    f"  {icon} {BOLD}{name}{RST} done"
                    f"  {DIM}({event.duration_ms} ms)  → {out}{RST}\n"
                )

            elif isinstance(event, RunStateEvent):
                state = event.to_state.value
                colours = {
                    "context_assembling": DIM,
                    "executing":  GRN + BOLD,
                    "completed":  GRN,
                    "failed":     RED,
                    "cancelled":  YLW,
                }
                c = colours.get(state, DIM)
                print(DIM + f"\n  ◎ run → {c}{state}{RST}", flush=True)

            elif isinstance(event, RunCompleteEvent):
                break

        print()
        return "".join(full_response)


# ── Part 1: Multi-tool turn via real model ────────────────────────────────────

async def part1_model_driven_tools(service, model_id: str) -> None:
    _section("PART 1 — Real model drives multiple tools", CYN)

    # Create session and set model
    cfg = SessionConfig(
        session_id=str(uuid.uuid4()),
        name="agentic-demo",
        framework="direct",
        default_model_id=model_id,
    )
    session = await service.create_session(cfg)
    sid = session.config.session_id
    await service.set_session_model(sid, model_id)

    prompt = (
        "Use your available tools to do the following steps IN ORDER, "
        "calling each tool separately:\n"
        "1. List the contents of the directory at path: "
        f"{_REPO}/packages/tools/builtin\n"
        "2. Search that same directory for all Python class definitions that "
        "inherit from BaseCallable (pattern: class \\w+\\(BaseCallable\\), "
        "glob: *.py)\n"
        "3. Read the file at path: "
        f"{_REPO}/packages/tools/builtin/search_web.py\n"
        "After all three tool calls, summarise: how many tools are in the "
        "directory, what they are named, and what search backends the "
        "search_web tool supports."
    )

    print()
    print(BLU + BOLD + "┌── USER " + "─" * 62 + RST)
    for line in textwrap.wrap(prompt, 68):
        print(BLU + "│  " + RST + line)
    print(BLU + BOLD + "└" + "─" * 70 + RST)
    print()

    run_id = await service.run_turn(sid, prompt)
    printer = LivePrinter()
    response = await printer.stream(service, run_id)

    if response.strip():
        print(GRN + BOLD + "┌── FINAL RESPONSE " + "─" * 52 + RST)
        for line in textwrap.wrap(response.strip(), 68):
            print(GRN + "│  " + RST + line)
        print(GRN + BOLD + "└" + "─" * 70 + RST)


# ── Part 2: Specialist agent calling 3 tools directly ────────────────────────

async def part2_specialist_agent(service) -> None:
    _section("PART 2 — ResearchSynthesizerAgent (specialist calls 3 tools)", BLU)

    from citnega.packages.tools.builtin.list_dir     import ListDirTool
    from citnega.packages.tools.builtin.search_files import SearchFilesTool
    from citnega.packages.tools.builtin.read_file    import ReadFileTool

    emitter = _Emitter()
    enforcer = _Enforcer()
    tracer   = _Tracer()

    tool_registry = {
        "list_dir":     ListDirTool(enforcer,     emitter, tracer),
        "search_files": SearchFilesTool(enforcer,  emitter, tracer),
        "read_file":    ReadFileTool(enforcer,     emitter, tracer),
    }
    agent = ResearchSynthesizerAgent(enforcer, emitter, tracer, tool_registry)

    sid = str(uuid.uuid4())
    ctx = CallContext(
        session_id=sid,
        run_id=str(uuid.uuid4()),
        turn_id=str(uuid.uuid4()),
        depth=0,
        parent_callable=None,
        session_config=SessionConfig(
            session_id=sid,
            name="specialist-demo",
            framework="direct",
            default_model_id="none",
        ),
        model_gateway=None,
    )

    topic = "search_web tool — what backends does it support?"
    print()
    print(BLU + BOLD + "┌── INVOKING AGENT: research_synthesizer " + "─" * 30 + RST)
    print(BLU + "│  topic: " + RST + topic)
    print(BLU + BOLD + "└" + "─" * 70 + RST)
    print()

    print(MGT + "  Executing specialist agent…" + RST)
    result = await agent.invoke(agent.input_schema(topic=topic), ctx)

    # Print each tool call event from the emitter
    for ev in emitter.events:
        if isinstance(ev, CallableStartEvent):
            print(
                f"\n  {YLW}⚙  TOOL CALLED:{RST} {BOLD}{ev.callable_name}{RST}"
            )
        elif isinstance(ev, CallableEndEvent):
            ok   = ev.error_code is None
            icon = f"{GRN}✔{RST}" if ok else f"{RED}✗{RST}"
            print(f"  {icon} {BOLD}{ev.callable_name}{RST} done  {DIM}({ev.duration_ms} ms){RST}")

    print()
    if result.success and result.output:
        out: SpecialistOutput = result.output
        print(GRN + BOLD + "┌── AGENT REPORT " + "─" * 54 + RST)
        for line in out.response.strip().splitlines():
            print(GRN + "│  " + RST + line[:68])
        print(GRN + "│" + RST)
        print(GRN + "│  " + RST + f"Tools called: {YLW}{', '.join(out.tool_calls_made)}{RST}")
        print(GRN + BOLD + "└" + "─" * 70 + RST)
    else:
        print(RED + f"  Agent error: {result.error}" + RST)


# ── Part 3: Second model turn (multi-turn context retained) ───────────────────

async def part3_followup_turn(service, model_id: str, sid: str) -> None:
    _section("PART 3 — Follow-up turn (context retained from Part 1)", CYN)

    followup = (
        "Based on your earlier tool research: which tool would you recommend "
        "for searching the web without an API key, and why? Keep the answer "
        "to 2-3 sentences."
    )

    print()
    print(BLU + BOLD + "┌── USER " + "─" * 62 + RST)
    print(BLU + "│  " + RST + followup)
    print(BLU + BOLD + "└" + "─" * 70 + RST)
    print()

    run_id = await service.run_turn(sid, followup)
    printer = LivePrinter()
    response = await printer.stream(service, run_id)

    if response.strip():
        print(GRN + BOLD + "┌── FINAL RESPONSE " + "─" * 52 + RST)
        for line in textwrap.wrap(response.strip(), 68):
            print(GRN + "│  " + RST + line)
        print(GRN + BOLD + "└" + "─" * 70 + RST)


# ── Entry point ───────────────────────────────────────────────────────────────

async def main(model_id: str) -> None:
    print()
    print(BOLD + CYN + "═" * 72 + RST)
    print(BOLD + CYN + "  CITNEGA — LIVE AGENTIC CONVERSATION" + RST)
    print(BOLD + CYN + f"  Model: {model_id}" + RST)
    print(BOLD + CYN + "═" * 72 + RST)

    from citnega.apps.cli.bootstrap import cli_bootstrap

    async with cli_bootstrap() as service:
        # Part 1 — model drives tools
        await part1_model_driven_tools(service, model_id)

        # Grab the session id that was just used so Part 3 can follow up
        sessions = await service.list_sessions()
        sessions.sort(key=lambda s: s.last_active_at or "", reverse=True)
        latest_sid = sessions[0].config.session_id if sessions else None

        # Part 2 — specialist agent
        await part2_specialist_agent(service)

        # Part 3 — follow-up turn on same session (context retained)
        if latest_sid:
            await part3_followup_turn(service, model_id, latest_sid)

    _section("ALL DONE", GRN)
    print("  Real LLM tool calls ✔   Specialist agent ✔   Multi-turn context ✔\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Citnega agentic demo")
    parser.add_argument(
        "--model",
        default="qwen3-coder-30b-local",
        help="Model ID from models.yaml (default: qwen3-coder-30b-local)",
    )
    args = parser.parse_args()
    asyncio.run(main(args.model))
