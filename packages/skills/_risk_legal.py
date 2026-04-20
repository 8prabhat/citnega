"""Risk management and legal skills."""

from __future__ import annotations

RISK_LEGAL_SKILLS: list[dict] = [
    {
        "name": "risk_assessment",
        "description": "Risk assessment protocol — identify threats, rate impact/likelihood, map controls.",
        "triggers": [
            "risk assessment", "risk register", "threat model",
            "identify risks", "risk analysis", "risk review",
        ],
        "preferred_tools": ["read_file", "create_excel", "write_pdf"],
        "preferred_agents": ["risk_manager_agent"],
        "supported_modes": ["review", "code"],
        "tags": ["risk-management", "compliance"],
        "body": """\
## Risk Assessment Protocol

**Step 1 — Identify risks:**
- Use STRIDE (Spoofing, Tampering, Repudiation, Info Disclosure, DoS, Elevation) for IT.
- Use PESTLE (Political, Economic, Social, Tech, Legal, Environmental) for business.
- Minimum 10 risks per domain. Use workshops, checklists, and prior incidents.

**Step 2 — Rate inherent risk (before controls):**
- Likelihood: 1 (rare) → 5 (almost certain)
- Impact: 1 (negligible) → 5 (catastrophic)
- Inherent score = Likelihood × Impact

**Step 3 — Map controls:**
- For each risk: list existing controls (preventive / detective / corrective).
- Rate control effectiveness: Strong (reduces score by 2+) / Moderate (1) / Weak (0).

**Step 4 — Residual risk:**
- Residual score = Inherent score − control reduction.
- CRITICAL (≥15): escalate immediately. HIGH (10–14): action plan required.

**Step 5 — Output:**
- Call `create_excel` with risk register: Risk ID | Category | Description | Likelihood | Impact | Score | Controls | Residual | Owner | Status.
- Call `write_pdf` for executive risk summary.
""",
    },
    {
        "name": "control_testing",
        "description": "Control effectiveness testing — test design, evidence collection, exception reporting.",
        "triggers": [
            "control test", "audit test", "compliance check",
            "test controls", "control effectiveness", "walkthrough",
        ],
        "preferred_tools": ["read_file", "write_docx", "create_excel"],
        "preferred_agents": ["risk_manager_agent", "security_agent"],
        "supported_modes": ["review"],
        "tags": ["risk-management", "audit"],
        "body": """\
## Control Testing Protocol

**Step 1 — Select controls:**
- Prioritise: high-risk controls, new controls, controls with prior exceptions.
- Define testing approach: Inquiry | Observation | Inspection | Re-performance.

**Step 2 — Test design:**
For each control:
- Control objective: what risk does this control mitigate?
- Test procedure: exact steps to verify the control is operating.
- Sample size: low risk=10, medium=25, high=40 (or 100% for critical).
- Expected evidence: what documents/logs prove the control worked?

**Step 3 — Execute tests:**
- Call `read_file` on relevant logs, reports, or approval records.
- Document each test: date, tester, population, sample, result.

**Step 4 — Report exceptions:**
- Exception: control not operating as designed for ≥1 sample item.
- For each exception: description, root cause, frequency (isolated vs systemic), impact.
- Rate: Control Deficiency | Significant Deficiency | Material Weakness.

**Step 5 — Management response:**
- For each exception: agreed remediation action, owner, target date.
- Call `create_excel` for control testing workpaper.
""",
    },
    {
        "name": "contract_review",
        "description": "Contract review protocol — parties, obligations, risk clauses, redline recommendations.",
        "triggers": [
            "review contract", "NDA review", "MSA review", "legal review",
            "redline", "contract analysis", "terms review", "agreement review",
        ],
        "preferred_tools": ["read_file", "write_docx", "write_pdf"],
        "preferred_agents": ["lawyer_agent"],
        "supported_modes": ["review"],
        "tags": ["legal", "contracts"],
        "body": """\
## Contract Review Protocol

**Step 1 — Read the full document:**
- Call `read_file` on the contract. Never comment without reading it fully.
- Identify: parties, effective date, governing law, jurisdiction.

**Step 2 — Analyse key sections:**
- **Scope and deliverables:** clear, measurable, with acceptance criteria?
- **Payment terms:** amount, timing, late payment penalties, invoicing requirements.
- **IP ownership:** who owns work product, background IP, improvements?
- **Confidentiality:** duration, exceptions, return/destruction obligations.
- **Liability:** caps, exclusions, indemnities — are they mutual?
- **Termination:** grounds for termination, notice periods, consequences.
- **Data protection:** GDPR/relevant law compliance, DPA required?
- **Dispute resolution:** jurisdiction, arbitration vs litigation.

**Step 3 — Flag issues:**
- **HIGH RISK:** one-sided liability caps, uncapped indemnities, broad IP assignment, no termination rights.
- **MEDIUM RISK:** unclear scope, short notice periods, automatic renewal without notice.
- **LOW RISK:** style/clarity issues, missing standard boilerplate.

**Step 4 — Recommendations:**
For each issue: clause reference | issue | recommended revision | rationale.

**Disclaimer:** This is legal analysis, not legal advice. Consult qualified counsel for binding decisions.
""",
    },
    {
        "name": "legal_research_protocol",
        "description": "Legal research protocol — primary sources, jurisdiction, competing views, application.",
        "triggers": [
            "legal research", "case law", "precedent", "regulation",
            "statute", "compliance research", "regulatory guidance",
        ],
        "preferred_tools": ["search_web", "read_webpage", "write_kb", "read_kb"],
        "preferred_agents": ["lawyer_agent"],
        "supported_modes": ["research"],
        "tags": ["legal", "research"],
        "body": """\
## Legal Research Protocol

**Step 1 — Define the question:**
- State the exact legal question. Identify jurisdiction(s).
- Check `read_kb` for prior research on this topic before new searches.

**Step 2 — Primary sources first:**
- Statutes and regulations: search official government/legislative databases.
- Case law: search for leading cases on the exact point.
- Regulatory guidance: check relevant regulator's published guidance.
- Note: publication date and whether superseded by later authority.

**Step 3 — Secondary sources:**
- Use law review articles, practitioner guides, and bar association materials.
- Distinguish: binding authority vs persuasive authority vs academic opinion.

**Step 4 — Competing views:**
- If the law is unsettled, present both sides with supporting authority.
- Note circuit splits or jurisdictional differences.

**Step 5 — Apply to facts:**
- Identify the relevant legal test or standard.
- Apply each element of the test to the specific facts.
- State the likely outcome and confidence level.

**Step 6 — Persist:**
- Call `write_kb` with: question, jurisdiction, key authorities, conclusion.

**Always note:** knowledge cutoff and recommend verification for recent developments.
""",
    },
]
