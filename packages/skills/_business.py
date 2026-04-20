"""Business analyst and financial controller skills."""

from __future__ import annotations

BUSINESS_SKILLS: list[dict] = [
    {
        "name": "requirements_gathering",
        "description": "Structured requirements elicitation — stakeholder interviews, user stories, acceptance criteria.",
        "triggers": [
            "requirements", "user story", "user stories", "gap analysis",
            "BRD", "FRD", "functional requirements", "elicit requirements",
        ],
        "preferred_tools": ["read_file", "write_docx", "create_excel"],
        "preferred_agents": ["business_analyst_agent"],
        "supported_modes": ["chat", "code", "plan"],
        "tags": ["business-analysis", "requirements"],
        "body": """\
## Requirements Gathering Protocol

**Step 1 — Understand current state (as-is):**
- Read any existing documentation: call `read_file` on specs, process maps, or meeting notes.
- Ask: Who are the stakeholders? What problem are we solving? What pain points exist today?

**Step 2 — Elicit requirements:**
- Structure questions by user persona: roles, goals, pain points, success criteria.
- Distinguish: Functional requirements (what the system does) vs Non-functional (performance, security, scale).
- Identify: explicit requirements (stated) and implicit (assumed but unstated).

**Step 3 — Write user stories:**
Format: **As a [persona], I want to [action] so that [benefit].**
- Add acceptance criteria for each story: **Given / When / Then** format.
- Flag dependencies and edge cases.

**Step 4 — Gap analysis:**
- Compare as-is vs to-be: what exists, what is missing, what must change.
- Produce a gap table: Gap | Impact | Priority | Owner.

**Step 5 — Document:**
- Call `write_docx` or `create_excel` with structured output.
- Include: assumptions made, open questions, out-of-scope items.
""",
    },
    {
        "name": "stakeholder_report",
        "description": "Executive stakeholder report — BLUF format, findings, recommendations, next steps.",
        "triggers": [
            "stakeholder report", "executive summary", "status update",
            "management report", "board report", "progress report",
        ],
        "preferred_tools": ["write_docx", "write_pdf", "create_ppt"],
        "preferred_agents": ["business_analyst_agent", "writing_agent"],
        "supported_modes": ["chat"],
        "tags": ["business-analysis", "reporting"],
        "body": """\
## Stakeholder Report Protocol

**Structure (BLUF — Bottom Line Up Front):**

**1. Executive Summary (3 sentences max):**
- What happened / what is the status?
- What is the impact or key finding?
- What decision or action is needed?

**2. Background (1 paragraph):**
- Context for readers who need it. Skip for readers who don't.

**3. Findings / Status:**
- Use tables, bullet points, and RAG status (Red/Amber/Green).
- Quantify where possible: numbers, percentages, dates.

**4. Recommendations:**
- Numbered list. Each recommendation: clear, actionable, owned.
- Format: [Action] by [Owner] by [Date] to achieve [Outcome].

**5. Next Steps:**
- 3–5 items max. Short-term (this week) and medium-term (this month).

**Output rules:**
- Call `write_docx` or `create_ppt` for the final deliverable.
- No jargon without definition. No passive voice. No weasel words.
""",
    },
    {
        "name": "variance_analysis",
        "description": "Financial variance analysis — actual vs budget, driver explanation, recommendations.",
        "triggers": [
            "variance analysis", "budget vs actual", "P&L review",
            "month-end", "financial analysis", "actuals vs forecast",
        ],
        "preferred_tools": ["pandas_analyze", "pivot_table", "create_excel", "write_pdf", "render_chart"],
        "preferred_agents": ["financial_controller_agent"],
        "supported_modes": ["code", "chat"],
        "tags": ["finance", "reporting"],
        "body": """\
## Variance Analysis Protocol

**Step 1 — Load data:**
- Call `pandas_analyze` on actuals and budget files.
- Verify: same period, same chart of accounts, same currency.

**Step 2 — Calculate variances:**
For each line item:
- Variance (£) = Actual − Budget
- Variance (%) = (Actual − Budget) / |Budget| × 100
- Flag: Favourable (F) or Adverse (A)
- Material threshold: >10% AND >£/$ 10,000 (adjust for scale).

**Step 3 — Explain drivers:**
For each material variance:
- Volume driver: did we do more/less than planned?
- Price/rate driver: did unit cost or rate change?
- Mix driver: did the composition of activity change?
- One-off items: flag non-recurring items separately.

**Step 4 — Visualise:**
- Call `render_chart` with a bar chart: actual vs budget by category.
- Call `render_chart` for monthly trend line if multi-period data available.

**Step 5 — Output:**
- Call `create_excel`: Actuals sheet | Budget sheet | Variance sheet | Summary.
- Call `write_pdf` for management narrative.

**Format rule:** Numbers to 2 decimal places. Consistent currency symbol. Thousands separator.
""",
    },
    {
        "name": "audit_protocol",
        "description": "Financial audit protocol — materiality, risk, test of controls, substantive testing.",
        "triggers": [
            "audit", "financial audit", "workpaper", "audit evidence",
            "audit planning", "substantive testing", "audit opinion",
        ],
        "preferred_tools": ["read_file", "pandas_analyze", "create_excel", "write_pdf"],
        "preferred_agents": ["financial_controller_agent"],
        "supported_modes": ["review", "code"],
        "tags": ["audit", "finance"],
        "body": """\
## Financial Audit Protocol

**Step 1 — Planning:**
- Set materiality threshold (typically 1–2% of total assets or 5% of pre-tax profit).
- Identify high-risk areas: revenue recognition, estimates, related-party transactions.
- Understand the entity: business model, control environment, prior audit findings.

**Step 2 — Risk assessment:**
- Identify assertions at risk: Completeness | Existence | Valuation | Cut-off | Presentation.
- For each assertion: inherent risk + control risk = combined risk.

**Step 3 — Test of controls:**
- Select key controls for high-risk assertions.
- Design and perform tests (see `control_testing` skill for procedure).
- If controls are effective: reduce substantive testing.

**Step 4 — Substantive testing:**
- Analytical procedures: compare current vs prior year, investigate variances >materiality.
- Tests of detail: vouch sample transactions to source documents.
- Call `pandas_analyze` on the trial balance / ledger data.
- Call `create_excel` to document sample selection and results.

**Step 5 — Findings:**
- Misstatements: actual vs likely (extrapolate from sample).
- Compare total likely misstatement to materiality threshold.
- Document: management's response and proposed adjustment.

**Step 6 — Conclusion:**
- Unmodified opinion: no material misstatement.
- Qualified / Adverse / Disclaimer: document basis clearly.
- Call `write_pdf` for the audit workpaper summary.
""",
    },
]
