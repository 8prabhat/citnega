"""
ScaffoldGenerator — LLM-first, fallback-second code generator.

Key features
------------
* ``generate(spec)``           — one-shot: returns complete source string.
* ``generate_streaming(spec, on_chunk)`` — streams tokens to the caller as
  they arrive; returns the full source string when done.
* ``generate_with_retry(spec, tester, max_retries)`` — runs tests after each
  generation attempt; if tests fail, re-calls the LLM with the error message
  so it can self-correct.  Falls back to templates only when all retries are
  exhausted.

LLM prompt strategy
-------------------
* Includes a *complete working example* for each kind so the model understands
  the pattern and import paths.
* Instructs the model to implement real logic (not TODOs or pass statements)
  that matches the description.
* Passes test-failure output back on retry so the model can fix specific bugs.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from citnega.packages.workspace.templates import FallbackTemplates, ScaffoldSpec

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


class ScaffoldGenerator:
    """
    Generates source code for a new callable artifact.

    Args:
        model_gateway: An IModelGateway instance, or None to use fallback only.
    """

    def __init__(self, model_gateway=None) -> None:
        self._gateway = model_gateway

    # ── Public API ─────────────────────────────────────────────────────────────

    async def generate(self, spec: ScaffoldSpec) -> str:
        """One-shot generation. Tries LLM first; falls back to templates."""
        if self._gateway is not None:
            try:
                return await self._generate_with_llm(spec, prior_error=None)
            except Exception:
                pass
        return self._generate_fallback(spec)

    async def generate_streaming(
        self,
        spec: ScaffoldSpec,
        on_chunk: Callable[[str], Awaitable[None]],
        prior_error: str | None = None,
    ) -> str:
        """
        Stream tokens to ``on_chunk`` as the LLM generates.

        Returns the complete source string when done.
        Falls back to a non-streaming call if streaming is unavailable.
        """
        if self._gateway is not None:
            try:
                return await self._stream_with_llm(spec, on_chunk, prior_error=prior_error)
            except Exception:
                pass
        source = self._generate_fallback(spec)
        # Deliver the whole thing as one chunk for a consistent experience
        await on_chunk(source)
        return source

    async def generate_with_retry(
        self,
        spec: ScaffoldSpec,
        tester,  # CallableTester instance
        loader,  # DynamicLoader instance
        on_chunk: Callable[[str], Awaitable[None]] | None = None,
        on_status: Callable[[str], Awaitable[None]] | None = None,
        max_retries: int = 2,
    ) -> tuple[str, object | None, object]:
        """
        Generate code, test it, and retry with the error on failure.

        Args:
            spec:        ScaffoldSpec describing what to create.
            tester:      CallableTester to run after each generation.
            loader:      DynamicLoader to instantiate the generated class.
            on_chunk:    Async callback receiving streamed LLM tokens.
            on_status:   Async callback receiving status strings like
                         "Generating (attempt 1/3)…", "Testing…".
            max_retries: Maximum number of additional LLM calls after the
                         first attempt.

        Returns:
            (source_code, instance_or_None, test_result)
        """
        from citnega.packages.workspace.validator import CodeValidator

        prior_error: str | None = None
        last_source: str = self._generate_fallback(spec)
        last_test = None
        instance = None

        for attempt in range(1, max_retries + 2):  # +2: first attempt + retries
            if on_status:
                await on_status(f"Generating code (attempt {attempt}/{max_retries + 1})…")

            # Generate
            if on_chunk is not None:
                source = await self.generate_streaming(spec, on_chunk, prior_error=prior_error)
            else:
                if (self._gateway is not None and attempt == 1) or self._gateway is not None:
                    try:
                        source = await self._generate_with_llm(spec, prior_error=prior_error)
                    except Exception:
                        source = self._generate_fallback(spec)
                else:
                    source = self._generate_fallback(spec)

            last_source = source

            # Syntax / struct validate first
            val = CodeValidator().validate(source, spec.class_name, spec.kind)
            if not val.ok:
                prior_error = "Validation errors:\n" + "\n".join(val.errors)
                if on_status:
                    await on_status(f"Validation failed — retrying…\n{prior_error}")
                continue

            # Load instance
            try:
                instance = self._load_instance(source, spec, loader)
            except Exception as exc:
                prior_error = f"Import error: {exc}"
                if on_status:
                    await on_status(f"Import failed — retrying…\n{prior_error}")
                continue

            # Runtime test
            if on_status:
                await on_status("Testing generated code…")
            test_result = await tester.test(instance)
            last_test = test_result

            if test_result.passed:
                if on_status:
                    await on_status(
                        f"Tests passed in {test_result.duration_ms} ms. "
                        f"Output: {test_result.output[:120]}"
                    )
                return source, instance, test_result

            # Tests failed — feed error back to LLM for next attempt
            prior_error = (
                f"The generated code raised an exception during testing:\n"
                f"{test_result.error}\n"
                f"Fix the bug and regenerate the complete module."
            )
            if on_status:
                await on_status(f"Tests failed (attempt {attempt}) — retrying with fix…")

        # All attempts exhausted
        return last_source, instance, last_test

    # ── LLM paths ─────────────────────────────────────────────────────────────

    async def _generate_with_llm(
        self,
        spec: ScaffoldSpec,
        prior_error: str | None = None,
    ) -> str:
        from citnega.packages.protocol.models.model_gateway import (
            ModelMessage,
            ModelRequest,
        )

        prompt = self._build_prompt(spec, prior_error=prior_error)
        response = await self._gateway.generate(
            ModelRequest(
                messages=[
                    ModelMessage(role="system", content=_SYSTEM_PROMPT),
                    ModelMessage(role="user", content=prompt),
                ],
                stream=False,
                temperature=0.2,
            )
        )
        return self._strip_fences(response.content)

    async def _stream_with_llm(
        self,
        spec: ScaffoldSpec,
        on_chunk: Callable[[str], Awaitable[None]],
        prior_error: str | None = None,
    ) -> str:
        from citnega.packages.protocol.models.model_gateway import (
            ModelMessage,
            ModelRequest,
        )

        prompt = self._build_prompt(spec, prior_error=prior_error)
        tokens: list[str] = []

        async for chunk in self._gateway.stream_generate(
            ModelRequest(
                messages=[
                    ModelMessage(role="system", content=_SYSTEM_PROMPT),
                    ModelMessage(role="user", content=prompt),
                ],
                stream=True,
                temperature=0.2,
            )
        ):
            if chunk.content:
                tokens.append(chunk.content)
                await on_chunk(chunk.content)

        return self._strip_fences("".join(tokens))

    # ── fallback path ─────────────────────────────────────────────────────────

    def _generate_fallback(self, spec: ScaffoldSpec) -> str:
        if spec.kind == "tool":
            return FallbackTemplates.render_tool(spec)
        if spec.kind == "agent":
            return FallbackTemplates.render_agent(spec)
        if spec.kind == "workflow":
            return FallbackTemplates.render_workflow(spec)
        raise ValueError(f"Unknown scaffold kind: {spec.kind!r}")

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _load_instance(source: str, spec: ScaffoldSpec, loader) -> object:
        """Compile and instantiate the generated class via DynamicLoader."""
        import pathlib
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            p = pathlib.Path(tmp) / f"{spec.name}.py"
            p.write_text(source, encoding="utf-8")
            loaded = loader.load_directory(pathlib.Path(tmp))
        if spec.name not in loaded:
            raise ImportError(
                f"Class '{spec.class_name}' was not found after import. "
                f"Loaded names: {list(loaded.keys())}"
            )
        return loaded[spec.name]

    def _build_prompt(
        self,
        spec: ScaffoldSpec,
        prior_error: str | None = None,
    ) -> str:
        params_text = ""
        if spec.parameters:
            lines = [
                f"  - {p['name']} ({p.get('type', 'str')}): {p.get('description', '')}"
                for p in spec.parameters
            ]
            params_text = "Parameters:\n" + "\n".join(lines)

        kind_example = _EXAMPLES.get(spec.kind, "")

        retry_section = ""
        if prior_error:
            retry_section = (
                f"\n\n## PREVIOUS ATTEMPT FAILED — FIX THIS ERROR\n"
                f"```\n{prior_error}\n```\n"
                f"Generate a corrected version that does NOT reproduce this error.\n"
            )

        return f"""\
Generate a single, complete, runnable Python module for a citnega {spec.kind}.

## Specification
- Class name  : {spec.class_name}
- name attr   : {spec.name!r}
- Description : {spec.description!r}
{params_text}
{f"System prompt: {spec.system_prompt!r}" if spec.system_prompt else ""}
{f"Tool whitelist: {spec.tool_whitelist}" if spec.tool_whitelist else ""}
{f"Sub-agents: {spec.sub_agents}" if spec.sub_agents else ""}

## Working Example (follow this pattern exactly)
{kind_example}

## Rules
1. Output ONLY raw Python — no markdown fences, no prose.
2. IMPLEMENT real logic that matches the description. No `pass`, no `# TODO`.
3. Use only Python stdlib + the citnega imports shown in the example.
4. Every class-level attribute (name, description, callable_type, input_schema,
   output_schema, policy) MUST be present.
5. The _execute method MUST be `async def _execute(self, input, context)`.
6. Return the correct output model (ToolOutput for tools, SpecialistOutput for agents/workflows).
{retry_section}"""

    @staticmethod
    def _strip_fences(text: str) -> str:
        text = text.strip()
        text = re.sub(r"^```(?:python)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
        return text.strip()


# ── Rich working examples fed to the LLM ──────────────────────────────────────

_EXAMPLES: dict[str, str] = {
    "tool": '''\
```python
"""reverse_string — reverse the characters in a string."""
from __future__ import annotations
from pydantic import BaseModel, Field
from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.context import CallContext
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

class ReverseStringInput(BaseModel):
    text: str = Field(description="Text to reverse.")

class ReverseStringTool(BaseCallable):
    name          = "reverse_string"
    description   = "Reverse the characters in the input string."
    callable_type = CallableType.TOOL
    input_schema  = ReverseStringInput
    output_schema = ToolOutput
    policy        = tool_policy(timeout_seconds=5.0)

    async def _execute(self, input: ReverseStringInput, context: CallContext) -> ToolOutput:
        return ToolOutput(result=input.text[::-1])
```''',
    "agent": '''\
```python
"""sentiment_agent — classify the sentiment of user text."""
from __future__ import annotations
from pydantic import BaseModel, Field
from citnega.packages.agents.specialists._specialist_base import SpecialistBase, SpecialistOutput
from citnega.packages.protocol.callables.context import CallContext
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType

class SentimentAgentInput(BaseModel):
    text: str = Field(description="Text to analyse.")

class SentimentAgent(SpecialistBase):
    name          = "sentiment_agent"
    description   = "Classify the sentiment of text as positive, neutral, or negative."
    callable_type = CallableType.SPECIALIST
    input_schema  = SentimentAgentInput
    output_schema = SpecialistOutput
    policy        = CallablePolicy(timeout_seconds=60.0, requires_approval=False)

    SYSTEM_PROMPT  = (
        "You are a sentiment analysis expert. "
        "Given text, respond with ONE of: positive, neutral, negative, "
        "followed by a one-sentence explanation."
    )
    TOOL_WHITELIST: list[str] = []

    async def _execute(self, input: SentimentAgentInput, context: CallContext) -> SpecialistOutput:
        response = await self._call_model(input.text, context)
        return SpecialistOutput(response=response)
```''',
    "workflow": '''\
```python
"""research_and_summarise — research a topic and produce a summary."""
from __future__ import annotations
from pydantic import BaseModel, Field
from citnega.packages.agents.specialists._specialist_base import SpecialistBase, SpecialistOutput
from citnega.packages.protocol.callables.context import CallContext
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType

class ResearchAndSummariseInput(BaseModel):
    topic: str = Field(description="Topic to research and summarise.")

class ResearchAndSummariseWorkflow(SpecialistBase):
    name          = "research_and_summarise"
    description   = "Research a topic using available tools and produce a clear summary."
    callable_type = CallableType.SPECIALIST
    input_schema  = ResearchAndSummariseInput
    output_schema = SpecialistOutput
    policy        = CallablePolicy(timeout_seconds=300.0, requires_approval=False)

    SYSTEM_PROMPT = (
        "You are a research workflow orchestrator. "
        "Use the available tools to gather information, then produce a clear, "
        "well-structured summary of the findings."
    )
    TOOL_WHITELIST: list[str] = []

    async def _execute(self, input: ResearchAndSummariseInput, context: CallContext) -> SpecialistOutput:
        prompt = f"Research the following topic and summarise your findings:\\n{input.topic}"
        response = await self._call_model(prompt, context)
        return SpecialistOutput(response=response)
```''',
}

_SYSTEM_PROMPT = """\
You are an expert Python developer for the citnega AI-agent framework.
You write COMPLETE, RUNNABLE Python modules — no TODO comments, no placeholder logic,
no `pass` statements in _execute.

When asked for a tool: implement the actual functionality using Python stdlib.
When asked for an agent/workflow: write a meaningful SYSTEM_PROMPT and implement _execute.

Follow the working example provided exactly. Use the same import paths.
Output ONLY raw Python source code — no markdown fences, no prose, no explanations.
"""
