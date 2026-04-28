"""HR and people operations skills."""

from __future__ import annotations

HR_SKILLS: list[dict] = [
    {
        "name": "recruitment_pipeline",
        "description": "End-to-end recruitment pipeline: JD, sourcing, screening, interviews, offer, onboarding checklist.",
        "triggers": [
            "recruitment", "hire", "hiring", "candidate", "job description",
            "interview process", "talent acquisition", "sourcing", "headhunting",
            "JD", "job posting", "screen resume",
        ],
        "preferred_tools": ["write_docx", "create_excel", "read_file", "email_composer", "search_files"],
        "preferred_agents": ["hr_agent"],
        "supported_modes": ["chat", "plan"],
        "tags": ["hr", "recruitment", "talent"],
        "body": """\
## Recruitment Pipeline Protocol

**Step 1 — Job Specification:**
- Clarify: role title, level, team, reporting line, key responsibilities, required vs. preferred skills.
- Write a JD with: summary, responsibilities (6–8 bullets), requirements (must-have / nice-to-have split), compensation range (if shareable), and DEI statement.
- Use `write_docx` to produce the final JD document.

**Step 2 — Sourcing Strategy:**
- Define channels: LinkedIn, job boards, internal referrals, agencies, GitHub/Stack Overflow (for tech roles).
- Set outreach sequence: initial message → follow-up (Day 5) → final attempt (Day 10).

**Step 3 — Screening Criteria:**
- Build a scorecard in `create_excel` with weighted criteria mapped to the JD requirements.
- Define a minimum pass score for phone screen progression.

**Step 4 — Interview Process:**
- Design rounds: phone screen → technical/skills → values → final panel.
- For each round: list the competencies assessed, suggested questions, and evaluation rubric.
- Use STAR format for behavioural questions (Situation, Task, Action, Result).

**Step 5 — Offer & Close:**
- Draft offer letter template covering: title, start date, compensation, benefits, reporting line, contingencies.
- Prepare counter-offer response playbook.

**Step 6 — Pre-Boarding Checklist:**
- Hardware provisioning, system access, team introductions, day-1 schedule, buddy assignment.

**Standards:**
- No gender-coded language in JDs (use tools like Textio guidelines).
- All screening criteria must be objective and role-relevant.
- Document every decision for audit compliance.
""",
    },
    {
        "name": "performance_review",
        "description": "Structured performance review: evidence gathering, ratings, development plan, calibration.",
        "triggers": [
            "performance review", "appraisal", "360 feedback", "performance management",
            "OKR review", "annual review", "mid-year review", "performance calibration",
            "PIP", "performance improvement plan", "rating", "stack rank",
        ],
        "preferred_tools": ["write_docx", "create_excel", "read_file", "email_composer"],
        "preferred_agents": ["hr_agent"],
        "supported_modes": ["chat"],
        "tags": ["hr", "performance", "talent"],
        "body": """\
## Performance Review Protocol

**Step 1 — Evidence Gathering:**
- Collect: self-assessment, manager observations, peer feedback (360), objective completion data.
- Review the employee's OKRs/goals set at the start of the period.
- Use `read_file` to pull any existing notes or prior reviews.

**Step 2 — Assessment Framework:**
Use STAR format for every evidence point:
- **Situation:** context
- **Task:** what was required
- **Action:** what they specifically did
- **Result:** measurable outcome

**Step 3 — Rating:**
- Rate against each competency on the agreed scale (e.g. 1–5 or Below/Meets/Exceeds/Outstanding).
- Provide at least 2 evidence items per rating.
- Cross-reference with peer-level calibration benchmarks.

**Step 4 — Calibration:**
- Flag any significant deviations from team norms with justification.
- Document calibration decisions for consistency and legal compliance.

**Step 5 — Development Plan:**
- Identify 2–3 growth areas with specific actions, resources, and timelines.
- Identify 1–2 strengths to leverage for career progression.

**Step 6 — Delivery:**
- Draft the formal review document via `write_docx`.
- Prepare talking points for the review conversation.
- Schedule follow-up check-ins (30/60/90 days post-review).

**Standards:**
- No personality judgements — only observable behaviours and measurable outcomes.
- No language that could constitute discrimination (age, gender, protected characteristics).
- Every rating must have documented evidence.
""",
    },
    {
        "name": "org_design",
        "description": "Organisational design: spans and layers analysis, RACI, team structure, transition plan.",
        "triggers": [
            "org design", "org chart", "org structure", "restructure", "reorganisation",
            "spans and layers", "RACI", "team structure", "headcount model",
            "operating model", "reporting lines",
        ],
        "preferred_tools": ["write_docx", "create_excel", "search_files", "read_file"],
        "preferred_agents": ["hr_agent"],
        "supported_modes": ["chat", "plan"],
        "tags": ["hr", "org-design", "strategy"],
        "body": """\
## Org Design Protocol

**Step 1 — Current State Analysis:**
- Map existing org chart: headcount by team, reporting lines, spans of control.
- Identify pain points: duplicated functions, under-spanned managers (>8 directs), over-layered hierarchy.
- Use `create_excel` for the headcount and spans analysis.

**Step 2 — Design Principles:**
- Define guiding principles: customer proximity, speed of decision, cost efficiency, talent development.
- Align with company stage: startup (flat) vs. scale-up (functional) vs. enterprise (matrix/divisional).

**Step 3 — Future State Design:**
- Propose target org structure with rationale for each change.
- Calculate new spans of control (target: 6–8 for most management layers).
- Identify roles created, eliminated, and changed.

**Step 4 — RACI Matrix:**
- For key cross-functional processes, build RACI (Responsible / Accountable / Consulted / Informed).
- Flag any processes with no clear Accountable owner.

**Step 5 — Transition Plan:**
- Sequence changes to minimise business disruption.
- Define communication plan: who is told what, and when.
- Identify at-risk talent requiring retention conversations.
- Timeline: design finalisation → leadership alignment → communication → implementation.

**Step 6 — Document:**
- Produce final org design document via `write_docx` with: rationale, before/after org charts, headcount delta, RACI, and transition timeline.
""",
    },
    {
        "name": "onboarding_plan",
        "description": "New hire onboarding plan: pre-arrival, day 1, week 1, 30/60/90-day goals.",
        "triggers": [
            "onboarding", "new hire", "day one", "first week plan", "welcome pack",
            "ramp plan", "new employee", "onboard", "orientation",
        ],
        "preferred_tools": ["write_docx", "email_composer", "read_file", "search_files"],
        "preferred_agents": ["hr_agent"],
        "supported_modes": ["chat"],
        "tags": ["hr", "onboarding", "talent"],
        "body": """\
## Onboarding Plan Protocol

**Pre-Arrival (T-5 to T-0):**
- Hardware provisioning: laptop, peripherals, access cards.
- System access: email, Slack/Teams, code repos, HR system, finance tools.
- Send welcome email with: first-day logistics, parking/transport, dress code, buddy name.
- Brief direct team: new hire name, role, start date, ask them to prepare a warm welcome.

**Day 1 — Welcome & Orientation:**
- 09:00 — Greet at reception, office tour, desk setup.
- 10:00 — HR paperwork: contracts, payroll, benefits enrolment.
- 11:00 — IT setup walkthrough with buddy.
- 12:00 — Team lunch.
- 14:00 — 1:1 with manager: role overview, expectations, 30/60/90 plan intro.
- 16:00 — Company culture/values session.

**Week 1 — Context Building:**
- Meet all immediate team members (30-min 1:1s).
- Shadow key workflows relevant to the role.
- Read foundational docs: strategy deck, product roadmap, org chart, key processes.
- Complete mandatory training: security, compliance, GDPR/data handling.

**30/60/90 Day Goals:**
- **Day 30:** Understand the role, team, tools, and key stakeholders. No deliverables yet — listening mode.
- **Day 60:** First meaningful contribution. Identify 1–2 early-win opportunities.
- **Day 90:** Operating independently. Deliver first significant outcome. Present a 90-day reflection.

**Buddy Programme:**
- Assign a peer buddy (not the manager) for informal questions.
- Buddy check-in schedule: daily Week 1, weekly Weeks 2–4, bi-weekly Month 2–3.

**Document:** Use `write_docx` to produce the personalised onboarding plan document.
""",
    },
]
