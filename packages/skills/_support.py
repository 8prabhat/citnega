"""Customer support skills."""

from __future__ import annotations

SUPPORT_SKILLS: list[dict] = [
    {
        "name": "ticket_triage",
        "description": "Support ticket triage: classify by urgency and impact, route to right team, set SLA expectations.",
        "triggers": [
            "ticket triage", "support ticket", "customer issue", "bug report",
            "P1 ticket", "escalation", "customer complaint", "support case",
            "incident ticket", "triage",
        ],
        "preferred_tools": ["read_kb", "write_kb", "read_file", "write_file", "email_composer"],
        "preferred_agents": ["customer_support_agent"],
        "supported_modes": ["chat", "operate"],
        "tags": ["support", "triage", "customer"],
        "body": """\
## Ticket Triage Protocol

**Step 1 — Classify Severity:**

| Severity | Urgency | Impact | Example | SLA |
|----------|---------|--------|---------|-----|
| P1 — Critical | Immediate | System down, data loss, security breach | Production outage affecting all users | 1 hour response, 4 hour resolution |
| P2 — High | < 2 hours | Major feature broken, workaround not available | Login broken for subset of users | 4 hour response |
| P3 — Medium | < 8 hours | Feature degraded, workaround exists | Slow performance, UI glitch | 24 hour response |
| P4 — Low | < 24 hours | Cosmetic, question, minor inconvenience | Typo in UI, how-to question | 48 hour response |

**Step 2 — Gather Information:**
Required before escalating or resolving:
- Affected user(s): email, account ID, account tier.
- Error message (exact text + screenshot if available).
- Steps to reproduce.
- When did it start?
- Is this isolated or affecting multiple users?
- Impact: how many users? Revenue at risk?
- Workaround: available or not?

**Step 3 — Route to Correct Team:**
- P1/P2 bugs → Engineering on-call + escalate to account owner.
- Billing → Finance team.
- Security → Security team (do not share publicly).
- Product feedback → Product team (log with evidence).
- How-to questions → Knowledge Base first → Support engineer.

**Step 4 — Customer Communication:**
- Acknowledge within SLA with: "We've received your report, here is what we know and what we're doing."
- Update every 2 hours for P1, every 4 hours for P2.
- Resolution message: what was the issue, what was fixed, what steps customer should take.
- Post-resolution: check-in 24 hours later.

**Step 5 — Document:**
- Log all P1/P2 tickets for monthly support review.
- Recurring issues → knowledge article + product feedback.
""",
    },
    {
        "name": "knowledge_article",
        "description": "Write a knowledge base article: problem description, root cause, step-by-step solution, verification.",
        "triggers": [
            "knowledge base article", "KB article", "FAQ", "how-to guide",
            "support article", "self-serve article", "troubleshooting guide",
            "knowledge base", "help article",
        ],
        "preferred_tools": ["write_docx", "write_kb", "read_kb", "read_file"],
        "preferred_agents": ["customer_support_agent", "writing_agent"],
        "supported_modes": ["chat"],
        "tags": ["support", "documentation", "knowledge"],
        "body": """\
## Knowledge Article Protocol

**Structure every KB article with:**

**1. Title:**
- Action-oriented: "How to [do X]" or "[Error message]: How to fix it."
- Include the exact error message if applicable (users search for these).

**2. Overview (2–3 sentences):**
- What this article covers.
- Who it's for.
- When to use this article vs. contacting support.

**3. Problem Description:**
- What the user experiences (symptoms, error messages, unexpected behaviour).
- Conditions when it occurs (OS, browser, plan tier, configuration).

**4. Root Cause (if applicable):**
- Plain-language explanation of why this happens.
- No jargon. If technical, add a "Technical Details" collapsible section.

**5. Solution (Step-by-Step):**
- Numbered steps — one action per step.
- Include: exact button names, menu paths, expected outcomes after each step.
- Screenshots or video for complex steps.
- Multiple solutions if issue has multiple causes — label them: "Option A (most common)" etc.

**6. Verification:**
- How to confirm the issue is resolved.
- "After completing these steps, you should see [expected state]."

**7. Still Need Help?**
- Link to related articles.
- How to contact support with what information to include.

**Writing Standards:**
- Plain language. Reading level ≤ grade 8.
- Active voice. Short sentences (≤20 words).
- No acronyms without definition on first use.
- Review quarterly — mark stale articles for update.
""",
    },
    {
        "name": "feedback_synthesis",
        "description": "Customer feedback synthesis: theme identification, sentiment analysis, quantified insights, product recommendations.",
        "triggers": [
            "feedback synthesis", "NPS", "customer feedback", "survey analysis",
            "CSAT", "VoC", "voice of customer", "feedback analysis",
            "customer satisfaction", "churn analysis",
        ],
        "preferred_tools": ["pandas_analyze", "render_chart", "write_docx", "read_kb", "write_kb", "create_excel"],
        "preferred_agents": ["customer_support_agent", "data_analyst_agent"],
        "supported_modes": ["research", "chat"],
        "tags": ["support", "analytics", "customer"],
        "body": """\
## Customer Feedback Synthesis Protocol

**Step 1 — Data Collection:**
- Sources: NPS surveys, CSAT scores, support tickets, churn interviews, app reviews, sales call notes.
- Time period: define clearly (e.g. last 90 days, last quarter).
- Segment by: customer tier, tenure, use case, geography.

**Step 2 — Quantitative Summary (use `pandas_analyze` or `create_excel`):**
- NPS score: Promoters (9–10) / Passives (7–8) / Detractors (0–6). NPS = %Promoters − %Detractors.
- CSAT: % satisfied (4–5 out of 5).
- Volume by category: bugs / billing / UX / missing features / positive feedback.
- Trend: month-over-month or quarter-over-quarter changes.

**Step 3 — Qualitative Theme Extraction:**
- Read a random sample (minimum 50 responses or all if < 50).
- Code responses: assign each to a theme.
- Themes: create inductively from the data, not pre-defined categories.
- Count occurrences per theme.

**Step 4 — Insight Statements:**
For each major theme (>5% of responses):
- **Observation:** "X% of detractors mentioned [theme]."
- **Root cause hypothesis:** "This appears to be because [reason]."
- **Business impact:** "Customers citing this theme have [X% higher] churn rate."

**Step 5 — Prioritisation:**
Plot themes on a 2×2: Frequency (y) vs. Sentiment Impact (x).
- Top-right (high frequency, high negative sentiment): address immediately.
- Top-left (high frequency, positive): amplify and protect.

**Step 6 — Report:**
- Charts via `render_chart`: NPS trend, theme distribution, satisfaction by segment.
- Findings document via `write_docx`.
- Store in KB via `write_kb`.
- End with: top 3 product recommendations with supporting evidence counts.
""",
    },
]
