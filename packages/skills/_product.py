"""Product management skills."""

from __future__ import annotations

PRODUCT_SKILLS: list[dict] = [
    {
        "name": "product_spec",
        "description": "Write a Product Requirements Document (PRD) with user stories, acceptance criteria, and success metrics.",
        "triggers": [
            "product spec", "PRD", "product requirements", "feature spec",
            "requirements doc", "PRFAQ", "product brief", "feature brief",
        ],
        "preferred_tools": ["write_docx", "read_file", "search_web", "read_kb", "write_kb"],
        "preferred_agents": ["product_manager_agent"],
        "supported_modes": ["chat", "plan"],
        "tags": ["product", "requirements", "documentation"],
        "body": """\
## Product Spec (PRD) Protocol

**Structure every PRD with these sections in order:**

**1. Problem Statement:**
- What problem are we solving? For whom?
- What is the current experience? What is the gap?
- Quantify the problem: how many users affected, how often, at what cost?

**2. Goals & Non-Goals:**
- Goals: specific, measurable outcomes this feature will achieve.
- Non-Goals: explicitly what this feature will NOT do (prevents scope creep).

**3. User Personas:**
- 1–3 primary personas with: role, context, pain point, desired outcome.

**4. User Stories:**
Format: *As a [persona], I want [action] so that [outcome].*
- Must-have (MVP): clearly labelled.
- Should-have (v1.1): clearly labelled.
- Could-have (future): noted but not scoped.

**5. Acceptance Criteria:**
For each user story, define:
- Given [context] / When [action] / Then [expected outcome]
- Edge cases and error states.

**6. Success Metrics:**
- Primary metric (the north star).
- Secondary metrics (guardrails — must not regress).
- Measurement method and target value.

**7. Open Questions:**
- List unresolved decisions with owner and target resolution date.

**8. Appendix:**
- Links to research, designs, technical specs, stakeholder sign-off.

**Standards:**
- Never skip the Non-Goals section.
- Every user story must have at least one acceptance criterion.
- Success metrics must be measurable within 30 days of launch.
""",
    },
    {
        "name": "roadmap_planning",
        "description": "Build a prioritised product roadmap using RICE/ICE scoring and Now/Next/Later horizons.",
        "triggers": [
            "roadmap", "product roadmap", "quarterly planning", "OKRs", "product strategy",
            "feature prioritisation", "backlog grooming", "sprint planning", "Now Next Later",
        ],
        "preferred_tools": ["create_ppt", "create_excel", "write_docx", "read_kb", "write_kb"],
        "preferred_agents": ["product_manager_agent"],
        "supported_modes": ["chat", "plan"],
        "tags": ["product", "roadmap", "strategy"],
        "body": """\
## Roadmap Planning Protocol

**Step 1 — Horizon Framing (Now / Next / Later):**
- **Now (0–3 months):** committed work, in flight or fully scoped.
- **Next (3–6 months):** planned work, high confidence, directionally scoped.
- **Later (6–12+ months):** strategic bets, low certainty, subject to change.

**Step 2 — Theme Identification:**
- Group features into 3–5 strategic themes aligned with company OKRs.
- Every item on the roadmap should map to a theme.

**Step 3 — Prioritisation (RICE Scoring):**
For each candidate feature:
- **R**each: how many users affected per quarter?
- **I**mpact: 3 (massive) / 2 (high) / 1 (medium) / 0.5 (low) / 0.25 (minimal)
- **C**onfidence: % confidence in estimates (100% = high evidence)
- **E**ffort: person-weeks to build

RICE Score = (Reach × Impact × Confidence) / Effort

Use `create_excel` to build the RICE scoring model.

**Step 4 — Dependency Mapping:**
- Identify hard dependencies between items.
- Flag external dependencies (third-party, platform, legal).

**Step 5 — Stakeholder Alignment:**
- Present roadmap in Now/Next/Later slide format via `create_ppt`.
- Include: theme summary, top 3 items per horizon, key trade-offs made.
- Schedule review cadence: monthly roadmap check-in, quarterly re-prioritisation.

**Standards:**
- Every roadmap item must map to a user problem or business metric.
- No "nice to have" items without a RICE score.
- Roadmaps are a communication tool — not a commitment calendar.
""",
    },
    {
        "name": "user_research",
        "description": "User research plan: interview guide, synthesis framework, insight statements, personas.",
        "triggers": [
            "user research", "user interviews", "UX research", "usability study",
            "persona", "customer insight", "jobs to be done", "JTBD",
            "voice of customer", "VoC", "customer discovery",
        ],
        "preferred_tools": ["write_docx", "read_kb", "write_kb", "search_web"],
        "preferred_agents": ["product_manager_agent", "ux_design_agent"],
        "supported_modes": ["research", "chat"],
        "tags": ["product", "research", "ux"],
        "body": """\
## User Research Protocol

**Step 1 — Research Plan:**
- Define research question (what specific question are we answering?).
- Choose method: generative (discovery) vs. evaluative (validation).
- Recruit: 5–8 participants per persona segment (diminishing returns after 5).
- Timeline: recruit (1 week) → conduct (1 week) → synthesise (3 days).

**Step 2 — Interview Guide:**
Structure:
1. Warm-up (5 min): role, background, context.
2. Exploration (30 min): open-ended questions about behaviour, not opinions.
   - "Walk me through the last time you…"
   - "What did you do when…?"
   - "Tell me about a time when this was particularly hard."
3. Wrap-up (5 min): anything else to share, referrals.

**Avoid:** leading questions, solution-pitching, asking "would you use this?"

**Step 3 — Synthesis (Affinity Mapping):**
- Extract observations (what users said/did) — not interpretations.
- Group observations into themes.
- Write insight statements: "We observed that [behaviour] because [motivation], leading to [consequence]."

**Step 4 — Personas:**
For each segment, produce a persona card with:
- Name, role, context.
- Goals and motivations.
- Pain points and frustrations.
- Behaviours and workarounds.
- Quote that captures their perspective.

**Step 5 — Report:**
- Use `write_docx` to produce the research report.
- Store insights in KB via `write_kb` for future reference.
- End with: implications for product, open questions, recommended next research.
""",
    },
    {
        "name": "competitive_analysis",
        "description": "Competitive analysis: feature matrix, positioning map, SWOT, pricing comparison, strategic recommendations.",
        "triggers": [
            "competitive analysis", "competitor", "market analysis", "landscape",
            "competitive intelligence", "SWOT", "positioning", "market map",
            "benchmark", "competitor research",
        ],
        "preferred_tools": ["search_web", "write_docx", "create_excel", "read_kb", "write_kb"],
        "preferred_agents": ["product_manager_agent", "research_agent"],
        "supported_modes": ["research", "chat"],
        "tags": ["product", "research", "strategy"],
        "body": """\
## Competitive Analysis Protocol

**Step 1 — Identify Competitors:**
- Direct competitors (same problem, same solution approach).
- Indirect competitors (same problem, different approach).
- Substitute solutions (different problem framing, but competes for the same budget/time).

Use `search_web` to research each competitor.

**Step 2 — Feature Matrix:**
Build in `create_excel`:
- Rows: features/capabilities.
- Columns: your product + each competitor.
- Cells: ✓ / ✗ / Partial / Coming Soon.
- Highlight your unique differentiators in green, gaps in red.

**Step 3 — Positioning Map:**
- Choose 2 axes that matter to buyers (e.g. Price vs. Simplicity, Enterprise vs. SMB).
- Plot all competitors on the map.
- Identify white space opportunities.

**Step 4 — SWOT Analysis:**
For each key competitor:
- **Strengths:** what they do better than you.
- **Weaknesses:** where they fall short.
- **Opportunities:** market trends they're not exploiting.
- **Threats:** moves they could make that would hurt you.

**Step 5 — Pricing Comparison:**
- Map pricing tiers, per-seat vs. usage-based, free tier availability.
- Calculate total cost of ownership (TCO) for a typical customer.

**Step 6 — Strategic Recommendations:**
- "Where should we compete?" (double down on differentiators)
- "Where should we avoid competing?" (accept losses to focused competitors)
- "What moves should we watch?" (early warning indicators)

**Document:** Use `write_docx` and store in KB via `write_kb`.
""",
    },
]
