"""Advanced finance skills (beyond the basic variance_analysis in _business.py)."""

from __future__ import annotations

FINANCE_ADVANCED_SKILLS: list[dict] = [
    {
        "name": "financial_model",
        "description": "Build financial models: DCF valuation, LBO, three-statement model, cap table.",
        "triggers": [
            "financial model", "DCF", "LBO", "valuation model", "three-statement model",
            "P&L model", "discounted cash flow", "leveraged buyout",
            "cap table", "revenue model", "financial projection",
        ],
        "preferred_tools": ["create_excel", "pandas_analyze", "render_chart", "write_pdf", "write_docx"],
        "preferred_agents": ["financial_controller_agent"],
        "supported_modes": ["chat", "plan"],
        "tags": ["finance", "modelling", "valuation"],
        "body": """\
## Financial Modelling Protocol

**Step 1 — Model Setup:**
- Define the purpose: valuation, planning, fundraising, M&A analysis.
- Set time horizon: monthly (first 2 years) → quarterly (years 3–5).
- Use `create_excel` with separate tabs: Assumptions | Income Statement | Balance Sheet | Cash Flow | Outputs.

**Step 2 — Revenue Build:**
- Driver-based model: units sold × price, or ARR × growth rate, or seats × ACV.
- Segment by product line, geography, or customer type.
- Growth assumptions must be explicitly justified (market size × capture rate or comparable comps).

**Step 3 — Cost Structure:**
- COGS: direct costs as % of revenue or per-unit cost.
- OpEx: headcount plan (HC × fully-loaded cost) + non-headcount (software, marketing, etc.).
- Link all cost lines to assumptions tab.

**Step 4 — Three-Statement Integration:**
- Income Statement → Net Income feeds Retained Earnings on Balance Sheet.
- Balance Sheet changes drive Cash Flow statement.
- Closing Cash = Opening Cash + Operating CF + Investing CF + Financing CF.
- Balance Sheet must balance every period.

**Step 5 — DCF Valuation (if applicable):**
- Project Free Cash Flow (EBIT × (1−tax) + D&A − CapEx − ΔWorking Capital).
- WACC: risk-free rate + beta × equity risk premium + debt cost × (1−tax) × weight.
- Terminal value: Gordon Growth Model or Exit Multiple method (cross-check both).
- Sensitivity table: show Enterprise Value across WACC ± 1% and terminal growth rate ± 0.5%.

**Step 6 — Output Presentation:**
- Summary tab with key metrics: Revenue CAGR, EBITDA margin, IRR, MOIC, Payback period.
- Scenario analysis: base / upside / downside.
- Charts via `render_chart`.

**Standards:**
- Every assumption must have a source or rationale.
- No hardcoded numbers in formula cells — all inputs in assumptions tab.
- Model must recalculate cleanly with no circular references.
""",
    },
    {
        "name": "budget_planning",
        "description": "Annual budget planning: zero-based budgeting, CapEx/OpEx split, headcount plan, scenario modelling.",
        "triggers": [
            "budget planning", "annual budget", "budget cycle", "zero-based budget",
            "capex planning", "opex budget", "department budget", "headcount budget",
            "budget forecast", "annual operating plan", "AOP",
        ],
        "preferred_tools": ["create_excel", "pandas_analyze", "write_docx", "render_chart"],
        "preferred_agents": ["financial_controller_agent"],
        "supported_modes": ["chat", "plan"],
        "tags": ["finance", "budgeting", "planning"],
        "body": """\
## Budget Planning Protocol

**Step 1 — Strategic Context:**
- Align budget with company OKRs for the year.
- Identify: growth bets (increased investment), efficiency plays (cost reduction), maintenance (flat).
- Define budget philosophy: zero-based (justify every cost) vs. incremental (prior year + % adjustment).

**Step 2 — Revenue Budget:**
- Build from pipeline and sales capacity model.
- Stress-test: what does the budget require from sales? (bookings, ARR, NRR)
- Cross-check against market conditions and sales cycle lead times.

**Step 3 — CapEx vs. OpEx:**
- CapEx: assets with multi-year useful life (infrastructure, tooling, equipment). Capitalise and depreciate.
- OpEx: period expenses (salaries, SaaS, marketing, T&E). Expensed immediately.
- For software: determine if it meets capitalisation criteria under accounting standards.

**Step 4 — Headcount Plan (use `create_excel`):**
- For each hire: role, team, start month, grade, salary, benefits load (typically 20–30% on top of salary).
- Distinguish: approved headcount (funded now) vs. conditional headcount (funded if milestone hit).
- Total to fully-loaded cost per month.

**Step 5 — Non-Headcount Budget:**
- Software/tools: review contracts, renewal dates, eliminate duplicates.
- Marketing: allocate by channel with expected CAC and pipeline contribution.
- Travel & Expenses: by department, with policy limits.
- Professional services: legal, accounting, consulting.

**Step 6 — Scenario Modelling:**
- Base: expected outcomes.
- Conservative: 20% revenue miss — what costs are controllable?
- Stretch: 20% revenue beat — where would we reinvest?

**Step 7 — Budget Document:**
- Produce via `write_docx`: executive summary, assumptions, department budgets, headcount plan.
- Charts for: monthly OpEx trend, CapEx schedule, headcount ramp.
""",
    },
    {
        "name": "investor_reporting",
        "description": "Investor reporting: board pack, KPI dashboard, cohort analysis, management accounts narrative.",
        "triggers": [
            "investor report", "board pack", "shareholder report", "KPI dashboard",
            "management accounts", "board meeting", "investor update",
            "monthly investor report", "board deck", "LP report",
        ],
        "preferred_tools": ["create_ppt", "write_pdf", "render_chart", "create_excel", "write_docx"],
        "preferred_agents": ["financial_controller_agent"],
        "supported_modes": ["chat", "plan"],
        "tags": ["finance", "investor-relations", "reporting"],
        "body": """\
## Investor Reporting Protocol

**Standard Board Pack Structure:**

**1. Executive Summary (CEO):**
- Headline narrative: 3 things that went well, 3 challenges, top priority for next period.
- Key decisions needed from the board.

**2. Financial Highlights (CFO):**
- Revenue: actual vs. budget, actual vs. prior period. ARR/MRR for SaaS.
- Gross margin trend.
- Cash burn / runway.
- Key variances: explain anything > ±10% vs. budget.

**3. KPI Dashboard:**
Build in `create_excel` and chart with `render_chart`:
- Growth metrics: MoM/YoY revenue growth, new ARR, expansion ARR, churned ARR.
- Efficiency metrics: CAC, LTV, LTV:CAC ratio, payback period.
- Operational metrics: DAU/MAU, NPS, support ticket volume and resolution time.
- Each KPI: actual | budget | prior period | trend arrow.

**4. Cohort Analysis:**
- Revenue retention by cohort (NRR %): do customers expand over time?
- Gross revenue retention (GRR %): what % of revenue renews?
- Payback cohorts: how quickly does each vintage pay back CAC?

**5. Business Unit / Product Review:**
- Key developments by product line or segment.
- Pipeline health (for sales-led businesses).

**6. People Update:**
- Headcount: actual vs. plan.
- Key hires and departures.
- Organisational changes.

**7. Risks & Mitigations:**
- Top 5 risks: probability × impact matrix.
- Mitigation actions and owner.

**8. Forward Look:**
- Next period targets.
- Key milestones and dates.
- Decisions / approvals required from board.

**Standards:**
- Numbers must reconcile to management accounts.
- Every variance must have a cause-and-effect explanation.
- Produce final pack via `create_ppt` for board presentation + `write_pdf` for distribution.
""",
    },
]
