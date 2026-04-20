---
name: research_protocol
description: Multi-source, citation-first research protocol for deep investigation tasks.
triggers:
  - research
  - investigate
  - deep dive
  - what is
  - how does
  - explain
  - find out
  - look into
preferred_tools:
  - search_web
  - read_webpage
  - fetch_url
  - read_kb
  - write_kb
preferred_agents:
  - research_agent
supported_modes:
  - research
  - explore
tags:
  - research
  - evidence-based
---

## Research Protocol

When this skill is active, treat every research request as a structured investigation:

**Step 1 — Check prior knowledge:**
- Call `read_kb` first to check if relevant prior research exists.
- If found, note what is already known before starting new searches.

**Step 2 — Multi-angle search:**
- Run `search_web` with at least 3 different query angles:
  1. The direct question
  2. A contrarian/critical framing ("risks of X", "criticism of Y")
  3. A temporal framing ("X in 2024", "latest developments in Y")
- Invoke `research_agent` for structured multi-source synthesis.

**Step 3 — Source quality rules:**
- Prefer primary sources (official docs, peer-reviewed papers, original announcements) over secondary sources (blogs, summaries).
- Note the publication date for every source — time-sensitive claims require recent sources.
- When sources conflict, present both views and note the disagreement.

**Step 4 — Structured output format:**
1. **Executive summary** (2–3 sentences)
2. **Findings** — each factual claim cited as [Source: Title](URL)
3. **Competing perspectives** — where sources disagree
4. **Gaps & uncertainties** — what is unknown or unverified
5. **Sources** — list all URLs used

**Step 5 — Persist findings:**
- Call `write_kb` to save key findings with the query as the title.
- This prevents redundant searches in future sessions.

Never present training data as current facts. If information may be outdated, say so explicitly and search before answering.
