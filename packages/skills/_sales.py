"""Sales and revenue skills."""

from __future__ import annotations

SALES_SKILLS: list[dict] = [
    {
        "name": "deal_review",
        "description": "Deal review using MEDDIC/BANT: qualification, risk assessment, next steps, win probability.",
        "triggers": [
            "deal review", "opportunity review", "pipeline review", "win/loss",
            "MEDDIC", "BANT", "sales stage", "deal qualification", "opportunity qualification",
            "forecast review",
        ],
        "preferred_tools": ["write_docx", "create_excel", "read_kb", "write_kb", "email_composer"],
        "preferred_agents": ["sales_agent"],
        "supported_modes": ["chat", "plan"],
        "tags": ["sales", "revenue", "deals"],
        "body": """\
## Deal Review Protocol (MEDDIC)

**MEDDIC Qualification Framework:**

- **M — Metrics:** What is the quantified business impact? (e.g. "saves 10 hours/week per team of 20 = $200k annual saving")
- **E — Economic Buyer:** Who controls the budget? Have you spoken to them directly?
- **D — Decision Criteria:** What criteria will be used to make the decision? (technical, commercial, legal)
- **D — Decision Process:** What are the steps to a signed contract? Who is involved at each stage?
- **I — Identify Pain:** What is the compelling event? What happens if they do nothing?
- **C — Champion:** Who inside the account is selling for you when you're not in the room?

**Deal Health Assessment:**
For each MEDDIC element, score: Strong (3) / Present (2) / Weak (1) / Unknown (0).
Total ≤8: re-qualify or disqualify. 9–15: active pursuit. 16–18: strong.

**Risk Register:**
- Identify top 3 risks to closing (e.g. budget freeze, competitor, champion turnover).
- Define mitigation action for each.

**Competitive Position:**
- What competitors are in the deal?
- What is your differentiation for this specific buyer's criteria?
- Do you have a "trap" set (criteria that favour you and disadvantage competitors)?

**Next Steps:**
- Define the precise mutual action plan: joint steps with dates and owners.
- Avoid "I'll follow up next week" — every next step must be scheduled and two-sided.

**Document via `write_docx`. Track in `create_excel` for pipeline reporting.**
""",
    },
    {
        "name": "proposal_writing",
        "description": "Sales proposal or RFP response: executive summary, value proposition, solution, pricing, next steps.",
        "triggers": [
            "proposal", "RFP response", "sales proposal", "statement of work", "SOW",
            "tender", "bid response", "commercial proposal", "quote",
        ],
        "preferred_tools": ["write_docx", "create_ppt", "read_kb", "write_kb", "email_composer"],
        "preferred_agents": ["sales_agent", "writing_agent"],
        "supported_modes": ["chat", "plan"],
        "tags": ["sales", "proposals", "revenue"],
        "body": """\
## Proposal Writing Protocol

**Structure every proposal with:**

**1. Executive Summary (½ page):**
- What you understand about their problem.
- Your recommended solution in 2 sentences.
- The quantified business outcome they will achieve.
- Why you are the right partner (3 bullets max).

**2. Problem Understanding:**
- Demonstrate you understand their specific situation (not generic).
- Reference pain points they shared in discovery.
- Quantify the cost of inaction.

**3. Proposed Solution:**
- What you are proposing (clear scope).
- How it solves their specific problem (connect dots explicitly).
- Implementation approach and timeline.
- What is NOT included (out of scope — avoid later disputes).

**4. Proof:**
- 2–3 relevant customer case studies with: company profile (similar to buyer), challenge, solution, quantified result.
- Certifications, accreditations, or third-party validation.

**5. Investment (Pricing):**
- Clear pricing table: line items, unit costs, total.
- Payment terms.
- What is included vs. optional add-ons.
- ROI calculation showing payback period.

**6. Terms Summary:**
- Contract duration, renewal, termination.
- SLA commitments.
- Data/security commitments.

**7. Next Steps:**
- Specific action with owner and date.
- Proposed contract signature date.
- Onboarding start date.

**Standards:**
- Executive summary is the most important section — write it last.
- Use their language and terminology throughout.
- Proof points must be specific and quantified — no vague testimonials.
""",
    },
    {
        "name": "pipeline_analysis",
        "description": "Pipeline health analysis: stage conversion rates, velocity, forecast accuracy, revenue at risk.",
        "triggers": [
            "pipeline", "sales pipeline", "forecast", "sales forecast", "pipeline health",
            "conversion rate", "funnel", "pipeline analysis", "win rate", "sales velocity",
        ],
        "preferred_tools": ["create_excel", "render_chart", "pandas_analyze", "write_docx", "read_kb"],
        "preferred_agents": ["sales_agent", "data_analyst_agent"],
        "supported_modes": ["chat", "plan"],
        "tags": ["sales", "analytics", "revenue"],
        "body": """\
## Pipeline Analysis Protocol

**Step 1 — Pipeline Hygiene Check:**
- Flag deals with: no next step date, no economic buyer identified, stage not updated in 14+ days.
- Remove dead deals (lost, ghosted, no budget) to get clean pipeline.

**Step 2 — Stage Conversion Analysis (use `create_excel` or `pandas_analyze`):**
For each stage transition:
- Volume entering stage (count and $ARR).
- Volume converting to next stage.
- Conversion rate %.
- Average days in stage.
- Compare to: prior period, target, and industry benchmark.

**Step 3 — Sales Velocity:**
Sales Velocity = (Number of Opportunities × Average Deal Value × Win Rate) / Average Sales Cycle (days)

- Calculate current velocity.
- Identify which lever has the most improvement opportunity.

**Step 4 — Forecast:**
- Commit: deals with signed paperwork or verbal committed by buyer.
- Best Case: deals expected to close this period with work needed.
- Pipeline: deals possible but not probable this period.
- Apply historical win rates per stage to calculate weighted forecast.

**Step 5 — Revenue at Risk:**
- Identify top 10 deals by ARR.
- For each: MEDDIC score, close date confidence, risk factors.
- Calculate: "If we lose these 3 deals, we miss target by $X."

**Step 6 — Report:**
- Pipeline waterfall chart via `render_chart`.
- Stage conversion funnel.
- Forecast vs. target summary.
- Top deals at risk table.
- Document via `write_docx`.
""",
    },
    {
        "name": "account_plan",
        "description": "Strategic account plan: account overview, stakeholder map, growth opportunities, action plan.",
        "triggers": [
            "account plan", "strategic account", "account strategy", "key account",
            "customer success plan", "QBR", "quarterly business review", "account management",
        ],
        "preferred_tools": ["write_docx", "create_excel", "read_kb", "write_kb", "email_composer"],
        "preferred_agents": ["sales_agent"],
        "supported_modes": ["chat", "plan"],
        "tags": ["sales", "account-management", "strategy"],
        "body": """\
## Account Plan Protocol

**Structure every account plan with:**

**1. Account Overview:**
- Company: size, industry, revenue, geography, public/private.
- Our relationship: contract start date, products used, ARR, NPS/health score.
- Relationship history: key events, escalations, expansions, case studies.

**2. Stakeholder Map:**
- List all contacts: name, role, influence level (Champion / Supporter / Neutral / Detractor / Blocker).
- Identify gaps: who don't we know that we should?
- Political map: who influences whom?

**3. Account Goals:**
- Their business goals for the next 12 months (from their public reports/conversations).
- How our product connects to each goal.

**4. Growth Opportunities:**
- Expansion: additional seats, new teams, new use cases.
- Cross-sell: complementary products.
- Upsell: higher tier/feature set.
- Quantify: $ARR opportunity for each.

**5. Competitive Position:**
- Who else is in the account?
- Are we at risk of displacement anywhere?

**6. 12-Month Action Plan:**
- Quarterly objectives (e.g. Q1: renew + expand team A; Q2: introduce product B to team C).
- Key activities: EBRs, executive introductions, usage reviews, training.
- Mutual success plan with customer sign-off.

**Document via `write_docx`. Update quarterly.**
""",
    },
]
