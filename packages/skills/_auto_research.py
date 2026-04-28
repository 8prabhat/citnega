"""Auto-research skill — structured autonomous research methodology."""

from __future__ import annotations

AUTO_RESEARCH_SKILLS: list[dict] = [
    {
        "name": "auto_research",
        "description": (
            "Autonomous deep research: KB-first check, multi-angle queries, source quality "
            "scoring, cross-verification, provenance tracking, structured cited report."
        ),
        "triggers": [
            "auto research",
            "deep research",
            "comprehensive research",
            "investigate",
            "research in depth",
            "find all information",
            "full report on",
            "look into this",
            "research this topic",
            "thorough research",
            "multi-source research",
            "cross-verify",
            "investigative report",
        ],
        "preferred_tools": [
            "search_web",
            "read_webpage",
            "web_scraper",
            "read_kb",
            "write_kb",
        ],
        "preferred_agents": ["auto_research_agent"],
        "supported_modes": ["auto_research", "research", "explore"],
        "tags": ["research", "evidence-based", "autonomous", "cited"],
        "body": """\
## Auto-Research Skill

Activate when: user asks for deep/comprehensive research, investigation, or full reports.

Protocol:
1. **KB-first** — call `read_kb` before searching; avoid re-researching known topics
2. **Decompose** — break goal into 3–6 sub-questions
3. **Multi-angle search** — 3 different angle-queries per sub-question via `search_web`
4. **Score sources** — rate recency, authority, relevance before reading
5. **Extract with provenance** — FACT/SOURCE/DATE/CONFIDENCE per claim
6. **Cross-verify** — flag single-source claims as [UNVERIFIED]; 2+ sources as [VERIFIED]
7. **Write KB** — persist verified findings with tags ["auto_research", topic]
8. **Self-assess** — score completeness 0-10; re-search gaps if < 8/10
9. **Synthesise** — Executive Summary / Findings (cited) / Competing Views / Gaps / Sources

Use `auto_research_agent` to execute the full structured investigation.
""",
    },
]
