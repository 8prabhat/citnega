"""SRE and operations skills."""

from __future__ import annotations

OPS_SKILLS: list[dict] = [
    {
        "name": "incident_response",
        "description": "Incident response runbook — triage, scope, mitigate, communicate, root-cause.",
        "triggers": [
            "incident", "outage", "alert", "on-call", "page",
            "service down", "degraded", "P1", "P2", "SEV1", "SEV2",
        ],
        "preferred_tools": ["log_analyzer", "run_shell", "api_tester"],
        "preferred_agents": ["sre_agent"],
        "supported_modes": ["operate", "code"],
        "tags": ["SRE", "incident-response"],
        "body": """\
## Incident Response Protocol

**Step 1 — Triage (first 5 minutes):**
- What is the user-facing impact? (down / degraded / data-loss risk)
- What is the blast radius? (1 user / region / all users)
- Assign severity: SEV1 (critical, all hands) | SEV2 (major, on-call) | SEV3 (minor)
- Call `log_analyzer` immediately on relevant service logs.

**Step 2 — Scope:**
- When did it start? (check logs for first error)
- What changed recently? (deployments, config changes, upstream dependencies)
- Call `api_tester` to verify which endpoints are affected.

**Step 3 — Mitigate (stop the bleeding):**
- State rollback/mitigation command before executing.
- Execute via `run_shell`. Verify recovery immediately after.
- Communicate status update to stakeholders every 15 minutes.

**Step 4 — Root cause:**
- 5-Whys analysis. Stop at the systemic cause, not the proximate one.
- Reproduce in non-production if possible before claiming root cause.

**Step 5 — Post-incident:**
- Write post-mortem within 48 hours. Use `postmortem` skill.
- Create action items with owners and due dates.
""",
    },
    {
        "name": "postmortem",
        "description": "Blameless post-mortem — timeline, contributing factors, action items.",
        "triggers": [
            "post-mortem", "postmortem", "retrospective", "blameless review",
            "incident review", "RCA", "root cause analysis",
        ],
        "preferred_tools": ["write_docx", "write_kb"],
        "preferred_agents": ["sre_agent", "writing_agent"],
        "supported_modes": ["chat", "code"],
        "tags": ["SRE", "postmortem"],
        "body": """\
## Blameless Post-Mortem Protocol

**Structure:**

**1. Summary:**
- Incident date/time (start and end), duration, severity.
- Services affected, user impact (% affected, error rate, latency).

**2. Timeline:**
- Chronological table: Time | Event | Who noticed / acted
- Include: first alert, first customer report, mitigation actions, resolution.

**3. Root cause:**
- The single technical root cause (not "human error").
- Contributing factors (what made the system fragile / hard to detect).

**4. Impact:**
- Quantified: user requests failed, SLA breach (minutes), revenue impact if known.

**5. What went well:**
- Detection, communication, rollback speed — acknowledge what worked.

**6. What could improve:**
- Gaps in monitoring, runbooks, testing, or deployment process.

**7. Action items:**
| Action | Owner | Priority | Due Date |
|--------|-------|----------|----------|

- P1 actions: fix within 1 week. P2: within 1 month.
- Call `write_kb` to save the post-mortem for future reference.

**Blameless rule:** Focus on system and process failures, not individual mistakes.
""",
    },
]
