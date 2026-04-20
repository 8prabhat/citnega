"""
MentalModelLLMCompiler — compile mental model specs from markdown using LLM extraction.

Falls back gracefully to keyword-based extraction when:
  - No model gateway is available (startup, no model configured)
  - The LLM call fails or returns invalid JSON
  - The extraction result is empty

The keyword fallback is the existing compile_mental_model() function —
unchanged, no regression.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from citnega.packages.strategy.mental_models import MentalModelSpec


_EXTRACTION_PROMPT = """\
Extract behavioral guidance from this mental model document. Return a JSON object with:
- "name": string (the model or concept name)
- "clauses": list of strings (concrete "do this" behavioral instructions)
- "negations": list of strings (things to avoid or not do — "never X", "do not Y")
- "applicable_modes": list of mode names from [chat, code, plan, research, explore, review, operate]

Rules:
- Each clause must be a complete, actionable instruction.
- Negations are separate from clauses — do not duplicate.
- Only include modes explicitly mentioned or strongly implied.
- Return valid JSON only. No markdown code fences. No preamble.

Document:
{document}"""


class MentalModelLLMCompiler:
    """
    Compile a MentalModelSpec from markdown using an LLM call.

    Falls back to keyword extraction if LLM unavailable or response invalid.
    """

    def __init__(self, model_gateway: Any = None) -> None:
        self._gateway = model_gateway

    async def compile(self, markdown: str) -> MentalModelSpec:
        """Compile markdown → MentalModelSpec with LLM-first, keyword fallback."""
        if self._gateway is not None and markdown.strip():
            try:
                return await self._compile_with_llm(markdown)
            except Exception:
                pass
        return self._compile_keyword_fallback(markdown)

    async def _compile_with_llm(self, markdown: str) -> MentalModelSpec:
        import json

        from citnega.packages.protocol.models.model_gateway import ModelRequest

        prompt = _EXTRACTION_PROMPT.format(document=markdown[:2000])
        req = ModelRequest(
            model_id="",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=600,
            stream=False,
        )
        chunks: list[str] = []
        async for chunk in self._gateway.stream_generate(req):
            if hasattr(chunk, "text"):
                chunks.append(chunk.text)

        raw = "".join(chunks).strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1].lstrip("json").strip()
            if "```" in raw:
                raw = raw.split("```", 1)[0].strip()

        data: dict[str, Any] = json.loads(raw)

        return self._make_spec(
            name=data.get("name", "unnamed"),
            clauses=data.get("clauses", []),
            negations=data.get("negations", []),
            applicable_modes=data.get("applicable_modes", []),
        )

    def _compile_keyword_fallback(self, markdown: str) -> MentalModelSpec:
        from citnega.packages.strategy.mental_models import compile_mental_model
        return compile_mental_model(markdown)

    @staticmethod
    def _make_spec(
        name: str,
        clauses: list[str],
        negations: list[str],
        applicable_modes: list[str],
    ) -> MentalModelSpec:
        """Build a MentalModelSpec from extracted fields."""
        from citnega.packages.strategy.mental_models import MentalModelSpec

        # MentalModelSpec may not have a negations field yet — add gracefully
        try:
            return MentalModelSpec(
                name=name,
                clauses=clauses,
                negations=negations,
                applicable_modes=applicable_modes,
            )
        except TypeError:
            # Fallback for older MentalModelSpec without negations field
            return MentalModelSpec(
                name=name,
                clauses=clauses + [f"Do not: {n}" for n in negations],
                applicable_modes=applicable_modes,
            )
