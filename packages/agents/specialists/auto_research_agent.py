"""
AutoResearchAgent — 9-phase structured autonomous research loop.

Capabilities:
  - KB-first check before every search pass (avoids re-researching known topics)
  - Multi-angle queries: 3 angle-queries per sub-question
  - Source quality scoring: recency + authority + relevance before reading
  - Structured fact extraction with full provenance per claim
  - Cross-verification: facts from 2+ sources → VERIFIED; single-source → UNVERIFIED
  - Adaptive depth: re-search only low-confidence gaps
  - Self-assessed completeness with stopping criteria
  - Mandatory 7-section structured report output
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.agents.specialists._specialist_base import SpecialistBase, SpecialistOutput
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class AutoResearchInput(BaseModel):
    goal: str = Field(description="Research goal or question to investigate comprehensively.")
    depth: str = Field(
        default="deep",
        description="'quick' | 'standard' | 'deep'. Controls source-read count per pass.",
    )
    max_sources: int = Field(
        default=5,
        description="Maximum top-scored sources to read per search pass.",
    )
    confidence_threshold: float = Field(
        default=0.8,
        description="Stop when self-assessed completeness ≥ threshold × 10 (i.e. ≥ 8/10 by default).",
    )


_SYNTHESIS_PROMPT = """\
You are a research synthesis specialist. Using ONLY the structured facts below (do NOT add
knowledge from training), write a rigorous report in exactly this format:

## Executive Summary
(3 sentences — key answer, main finding, one caveat)

## Findings
(headed sections; cite each claim as [Title](URL))

## Competing Perspectives
(where sources agree vs. disagree; mark clearly)

## Unverified Claims
(claims with only a single source — flag with [UNVERIFIED])

## Gaps
(what was not answered by the research; what would need more investigation)

## Sources
(numbered list of all URLs used)

Be precise. Do not speculate beyond the evidence. Use [VERIFIED] / [UNVERIFIED] markers inline.
"""

_FACT_RE = re.compile(
    r"FACT:\s*(?P<claim>[^\n]+)\s*SOURCE:\s*(?P<url>\S+)\s*DATE:\s*(?P<date>\S+)\s*CONFIDENCE:\s*(?P<conf>\S+)",
    re.IGNORECASE,
)


class AutoResearchAgent(SpecialistBase):
    name = "auto_research_agent"
    description = (
        "Autonomous deep research: KB-first check, multi-angle queries, source quality scoring, "
        "cross-verification, provenance tracking, self-assessed completeness, structured cited report. "
        "Use for comprehensive investigative research requiring depth, citations, and structure. "
        "Prefer over research_agent when the user asks for 'deep research', 'full report', "
        "'investigate', or 'comprehensive' analysis."
    )
    callable_type = CallableType.SPECIALIST
    input_schema = AutoResearchInput
    output_schema = SpecialistOutput
    policy = CallablePolicy(
        timeout_seconds=300.0,
        requires_approval=False,
        network_allowed=True,
        max_output_bytes=1024 * 1024,
        max_depth_allowed=4,
    )

    SYSTEM_PROMPT = (
        "You are a rigorous research analyst. Extract structured facts with full provenance.\n"
        "For each fact use format:\n"
        "  FACT: <claim> SOURCE: <url> DATE: <date> CONFIDENCE: <high/medium/low>\n"
        "Rate source quality: recency (1-5), authority (1-5), relevance (1-5).\n"
        "Always distinguish VERIFIED (2+ sources) from UNVERIFIED (single source) claims."
    )
    TOOL_WHITELIST = [
        "search_web", "read_webpage", "fetch_url", "web_scraper",
        "read_kb", "write_kb", "get_datetime", "render_chart",
    ]

    # ── Entry point ───────────────────────────────────────────────────────────

    async def _execute(self, input: AutoResearchInput, context: CallContext) -> SpecialistOutput:
        child_ctx = context.child(self.name, self.callable_type)
        goal = input.goal
        tool_calls_made: list[str] = []
        all_urls: list[str] = []

        # Phase 1 — Decompose goal into sub-questions
        sub_questions = await self._decompose_goal(goal, child_ctx)

        # Phase 2 — KB-first: check existing knowledge
        satisfied, kb_context = await self._kb_preflight(sub_questions, goal, child_ctx, tool_calls_made)

        # Phase 3-7 loop (with up to 2 extra re-search passes from Phase 8)
        extracted_facts: list[dict] = []
        extra_passes_remaining = 2

        async def _search_extract_verify(unsatisfied: list[str]) -> None:
            nonlocal extracted_facts, tool_calls_made, all_urls

            # Phase 3: parallel search
            urls_with_meta = await self._parallel_search(
                unsatisfied, goal, child_ctx, tool_calls_made
            )
            all_urls.extend(u["url"] for u in urls_with_meta if u["url"] not in all_urls)

            # Phase 4: score sources
            top_urls = await self._score_sources(
                urls_with_meta, goal, input.max_sources, child_ctx
            )

            # Phase 5: read and extract facts
            new_facts = await self._read_and_extract(
                top_urls, goal, child_ctx, tool_calls_made
            )
            extracted_facts.extend(new_facts)

            # Phase 6: cross-verify (pure Python)
            _cross_verify(extracted_facts)

            # Phase 7: write verified facts to KB
            await self._write_to_kb(extracted_facts, goal, child_ctx, tool_calls_made)

        unsatisfied = [q for i, q in enumerate(sub_questions) if i not in satisfied]
        await _search_extract_verify(unsatisfied)

        # Phase 8 — Self-assess; loop back if needed
        while extra_passes_remaining > 0:
            score, gaps = await self._self_assess(
                sub_questions, extracted_facts, goal, child_ctx
            )
            threshold_score = input.confidence_threshold * 10
            if score >= threshold_score or not gaps:
                break
            extra_passes_remaining -= 1
            await _search_extract_verify(gaps)

        # Phase 9 — Synthesise structured report
        report = await self._synthesise(extracted_facts, goal, child_ctx)

        return SpecialistOutput(
            response=report,
            tool_calls_made=tool_calls_made,
            sources=all_urls,
        )

    # ── Phase 1: Decompose ────────────────────────────────────────────────────

    async def _decompose_goal(self, goal: str, ctx: CallContext) -> list[str]:
        prompt = (
            f"Break this research goal into 3–6 numbered sub-questions that together would "
            f"fully answer it:\n\nGoal: {goal}\n\n"
            f"Reply ONLY with a numbered list, one sub-question per line."
        )
        raw = await self._call_model(prompt, ctx)
        questions = []
        for line in raw.splitlines():
            line = line.strip()
            match = re.match(r"^\d+[\.\)]\s*(.+)", line)
            if match:
                questions.append(match.group(1).strip())
        return questions or [goal]

    # ── Phase 2: KB-first ─────────────────────────────────────────────────────

    async def _kb_preflight(
        self,
        sub_questions: list[str],
        goal: str,
        ctx: CallContext,
        tool_calls_made: list[str],
    ) -> tuple[set[int], str]:
        satisfied: set[int] = set()
        kb_context_parts: list[str] = []

        kb_tool = self._get_tool("read_kb")
        if not kb_tool:
            return satisfied, ""

        try:
            from citnega.packages.tools.builtin.read_kb import ReadKBInput

            for i, q in enumerate(sub_questions):
                result = await kb_tool.invoke(ReadKBInput(query=q, max_results=3), ctx)
                if result.success and result.output:
                    text = result.get_output_field("result")
                    if text and "(Knowledge base not connected)" not in text and len(text) > 50:
                        satisfied.add(i)
                        kb_context_parts.append(f"KB answer for '{q}':\n{text}")
            if kb_context_parts:
                tool_calls_made.append("read_kb")
        except Exception:
            pass

        return satisfied, "\n\n".join(kb_context_parts)

    # ── Phase 3: Parallel search ──────────────────────────────────────────────

    async def _parallel_search(
        self,
        sub_questions: list[str],
        goal: str,
        ctx: CallContext,
        tool_calls_made: list[str],
    ) -> list[dict]:
        search_tool = self._get_tool("search_web")
        if not search_tool:
            return []

        # Generate 3 angle-queries per sub-question
        all_queries: list[str] = []
        for q in sub_questions[:4]:  # cap at 4 sub-questions per pass
            angle_prompt = (
                f"Generate 3 distinct web search queries from different angles for:\n{q}\n\n"
                f"Context goal: {goal}\n\n"
                f"Reply ONLY with 3 queries, one per line, no numbering."
            )
            raw = await self._call_model(angle_prompt, ctx)
            queries = [line.strip() for line in raw.splitlines() if line.strip()][:3]
            all_queries.extend(queries or [q])

        # Execute searches
        seen_urls: set[str] = set()
        results: list[dict] = []
        try:
            from citnega.packages.tools.builtin.search_web import SearchWebInput

            for query in all_queries[:9]:  # cap total searches to 9
                result = await search_tool.invoke(
                    SearchWebInput(query=query, max_results=5), ctx
                )
                if result.success and result.output:
                    raw_text = result.get_output_field("result")
                    # Parse "Title: ...\nURL: ...\nSnippet: ..." blocks
                    for block in re.split(r"\n(?=\d+\.\s)", raw_text):
                        url_match = re.search(r"URL:\s*(https?://\S+)", block)
                        title_match = re.search(r"Title:\s*(.+)", block)
                        snippet_match = re.search(r"Snippet:\s*(.+)", block)
                        url = url_match.group(1) if url_match else ""
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            results.append({
                                "url": url,
                                "title": title_match.group(1).strip() if title_match else url,
                                "snippet": snippet_match.group(1).strip() if snippet_match else "",
                            })
            if results:
                tool_calls_made.append("search_web")
        except Exception:
            pass

        return results

    # ── Phase 4: Score sources ────────────────────────────────────────────────

    async def _score_sources(
        self,
        urls_with_meta: list[dict],
        goal: str,
        max_sources: int,
        ctx: CallContext,
    ) -> list[dict]:
        if not urls_with_meta:
            return []

        # Build a compact representation for batch scoring
        items = "\n".join(
            f"{i+1}. Title: {m['title']}\n   URL: {m['url']}\n   Snippet: {m['snippet'][:150]}"
            for i, m in enumerate(urls_with_meta[:20])
        )
        prompt = (
            f"Rate each source for researching: {goal}\n\n"
            f"Sources:\n{items}\n\n"
            f"For each, output JSON on one line: "
            f'{{\"i\": <1-based index>, \"recency\": 1-5, \"authority\": 1-5, \"relevance\": 1-5}}\n'
            f"Higher = better. Output only the JSON lines, nothing else."
        )
        try:
            raw = await self._call_model(prompt, ctx)
            scores: dict[int, float] = {}
            for line in raw.splitlines():
                line = line.strip()
                if line.startswith("{"):
                    try:
                        obj = json.loads(line)
                        idx = int(obj.get("i", 0)) - 1
                        total = (
                            float(obj.get("recency", 3))
                            + float(obj.get("authority", 3))
                            + float(obj.get("relevance", 3))
                        )
                        scores[idx] = total
                    except Exception:
                        pass

            ranked = sorted(
                range(len(urls_with_meta)),
                key=lambda i: scores.get(i, 9.0),
                reverse=True,
            )
            return [urls_with_meta[i] for i in ranked[:max_sources]]
        except Exception:
            return urls_with_meta[:max_sources]

    # ── Phase 5: Read and extract ─────────────────────────────────────────────

    async def _read_and_extract(
        self,
        top_sources: list[dict],
        goal: str,
        ctx: CallContext,
        tool_calls_made: list[str],
    ) -> list[dict]:
        read_tool = self._get_tool("read_webpage")
        if not read_tool or not top_sources:
            return []

        extracted: list[dict] = []
        try:
            from citnega.packages.tools.builtin.read_webpage import ReadWebpageInput

            for source in top_sources:
                url = source["url"]
                page_result = await read_tool.invoke(
                    ReadWebpageInput(url=url, max_chars=4000), ctx
                )
                if not page_result.success or not page_result.output:
                    continue
                page_text = page_result.get_output_field("result")

                extract_prompt = (
                    f"Research goal: {goal}\n\n"
                    f"Page from {url}:\n{page_text[:3500]}\n\n"
                    f"Extract all relevant facts using this format (one per line):\n"
                    f"FACT: <claim> SOURCE: {url} DATE: <date or 'unknown'> "
                    f"CONFIDENCE: <high/medium/low>\n\n"
                    f"Extract only facts directly relevant to the research goal. "
                    f"Do not paraphrase — quote or closely summarize the source."
                )
                raw = await self._call_model(extract_prompt, ctx)
                for match in _FACT_RE.finditer(raw):
                    extracted.append({
                        "claim": match.group("claim").strip(),
                        "url": match.group("url").strip(),
                        "date": match.group("date").strip(),
                        "confidence": match.group("conf").strip().lower(),
                        "verified": False,
                    })

            if extracted:
                tool_calls_made.append("read_webpage")
        except Exception:
            pass

        return extracted

    # ── Phase 8: Self-assess ──────────────────────────────────────────────────

    async def _self_assess(
        self,
        sub_questions: list[str],
        facts: list[dict],
        goal: str,
        ctx: CallContext,
    ) -> tuple[float, list[str]]:
        facts_summary = "\n".join(
            f"- {f['claim']} ({'VERIFIED' if f['verified'] else 'UNVERIFIED'})"
            for f in facts[:30]
        )
        prompt = (
            f"Research goal: {goal}\n\n"
            f"Sub-questions that needed answering:\n"
            + "\n".join(f"{i+1}. {q}" for i, q in enumerate(sub_questions))
            + f"\n\nFacts gathered so far:\n{facts_summary}\n\n"
            f"On a scale of 0-10, how completely do the facts answer all sub-questions?\n"
            f"Then list any sub-questions still unanswered as gap search queries.\n\n"
            f"Reply in this format:\n"
            f"SCORE: <0-10>\n"
            f"GAPS:\n- <gap query 1>\n- <gap query 2>\n..."
        )
        try:
            raw = await self._call_model(prompt, ctx)
            score_match = re.search(r"SCORE:\s*(\d+(?:\.\d+)?)", raw)
            score = float(score_match.group(1)) if score_match else 5.0

            gaps: list[str] = []
            in_gaps = False
            for line in raw.splitlines():
                if line.strip().startswith("GAPS:"):
                    in_gaps = True
                    continue
                if in_gaps and line.strip().startswith("-"):
                    gaps.append(line.strip().lstrip("- ").strip())

            return score, gaps
        except Exception:
            return 5.0, []

    # ── Phase 7: Write to KB ──────────────────────────────────────────────────

    async def _write_to_kb(
        self,
        facts: list[dict],
        goal: str,
        ctx: CallContext,
        tool_calls_made: list[str],
    ) -> None:
        write_tool = self._get_tool("write_kb")
        if not write_tool:
            return

        verified = [f for f in facts if f.get("verified")]
        if not verified:
            return

        content = f"Research goal: {goal}\n\nVerified findings:\n" + "\n".join(
            f"- {f['claim']} [SOURCE: {f['url']}] [DATE: {f['date']}]"
            for f in verified[:20]
        )
        try:
            from citnega.packages.tools.builtin.write_kb import WriteKBInput

            result = await write_tool.invoke(
                WriteKBInput(
                    title=f"auto_research: {goal[:60]}",
                    content=content,
                    tags=["auto_research", "verified"],
                ),
                ctx,
            )
            if result.success:
                tool_calls_made.append("write_kb")
        except Exception:
            pass

    # ── Phase 9: Synthesise ───────────────────────────────────────────────────

    async def _synthesise(
        self,
        facts: list[dict],
        goal: str,
        ctx: CallContext,
    ) -> str:
        if not facts:
            return (
                f"## Research Report: {goal}\n\n"
                "No information could be gathered. "
                "Search tools may be unavailable or returned no results."
            )

        facts_text = "\n".join(
            f"[{'VERIFIED' if f['verified'] else 'UNVERIFIED'}] "
            f"FACT: {f['claim']} | SOURCE: {f['url']} | DATE: {f['date']} | "
            f"CONFIDENCE: {f['confidence']}"
            for f in facts
        )
        prompt = (
            f"Research goal: {goal}\n\n"
            f"Structured facts gathered:\n{facts_text}\n\n"
            f"{_SYNTHESIS_PROMPT}"
        )
        return await self._call_model(prompt, ctx, system_override=_SYNTHESIS_PROMPT)


# ── Phase 6: Cross-verify (pure Python, zero LLM cost) ───────────────────────


def _cross_verify(facts: list[dict]) -> None:
    """Mark facts as verified if the same claim appears from 2+ distinct URLs."""
    from collections import defaultdict

    claim_sources: dict[str, set[str]] = defaultdict(set)
    for f in facts:
        key = _normalise_claim(f["claim"])
        claim_sources[key].add(f["url"])

    for f in facts:
        key = _normalise_claim(f["claim"])
        f["verified"] = len(claim_sources[key]) >= 2


def _normalise_claim(claim: str) -> str:
    """Rough normalisation for claim deduplication — lowercase, strip punctuation."""
    return re.sub(r"[^\w\s]", "", claim.lower()).strip()
