"""Core engineering skills: security, code review, research, debugging, deployment."""

from __future__ import annotations

CORE_SKILLS: list[dict] = [
    {
        "name": "security_review",
        "description": "Comprehensive security review protocol for code changes and file systems.",
        "triggers": [
            "security review", "audit", "scan for secrets",
            "check vulnerabilities", "security audit", "penetration", "pen test",
        ],
        "preferred_tools": [
            "vuln_scanner", "secrets_scanner", "hash_integrity",
            "os_fingerprint", "process_inspector",
        ],
        "preferred_agents": ["security_agent"],
        "supported_modes": ["review", "code"],
        "tags": ["security", "audit"],
        "body": """\
## Security Review Protocol

When this skill is active, follow these steps for every security-related request:

**Step 1 — Static code analysis:**
- Invoke `security_agent` on the working directory or changed files.
- Run `vuln_scanner` to detect: hardcoded credentials, SQL injection, unsafe `eval()`,
  `subprocess.shell=True`, `verify=False` in HTTP clients, insecure deserialization.
- Run `secrets_scanner` on any `.env`, config, or credential files.

**Step 2 — Integrity checks:**
- Run `hash_integrity` on critical files if a baseline exists.
- Check for unexpected SUID bits or world-writable files if on Linux.

**Step 3 — System posture (if applicable):**
- Run `os_fingerprint` to confirm the target OS and architecture.
- Run `process_inspector` if suspicious processes should be checked.

**Step 4 — Report findings by severity:**
Structure every finding as:

**[SEVERITY] file.py:line — brief description**
- Risk: what an attacker could do if exploited
- Recommendation: concrete remediation step

Severity levels: CRITICAL | HIGH | MEDIUM | LOW | INFO

**Never** mark a finding CRITICAL without explaining the exploit path.
**Always** include file and line number citations from tool output.
""",
    },
    {
        "name": "code_review",
        "description": "Structured code review protocol — diff-first, evidence-driven, severity-graded.",
        "triggers": [
            "code review", "PR review", "review changes",
            "review this", "review the diff", "review pull request",
        ],
        "preferred_tools": ["git_ops", "read_file", "quality_gate", "repo_map"],
        "preferred_agents": ["code_agent", "qa_agent"],
        "supported_modes": ["review"],
        "tags": ["review", "code quality"],
        "body": """\
## Code Review Protocol

When this skill is active, perform a structured review:

**Step 1 — Read the diff (mandatory first action):**
- Call `git_ops` with `operation=diff`. Never comment on code you have not read.

**Step 2 — Read surrounding context (parallel):**
- Read test files for changed modules. Read interfaces or base classes referenced.
- Call `repo_map` for architectural context.

**Step 3 — Run automated checks:**
- Call `quality_gate` to get lint warnings, type errors, and complexity metrics.

**Step 4 — Produce findings table:**

| Severity | File:Line | Finding | Recommendation |
|----------|-----------|---------|----------------|

Look specifically for: bugs, regressions, missing tests, security issues,
performance problems, breaking API changes.

End with a **verdict**: Approved / Needs minor changes / Needs major revision.
""",
    },
    {
        "name": "research_protocol",
        "description": "Multi-source, citation-first research protocol for deep investigation tasks.",
        "triggers": [
            "research", "investigate", "deep dive", "what is",
            "how does", "explain", "find out", "look into",
        ],
        "preferred_tools": [
            "search_web", "read_webpage", "fetch_url", "read_kb", "write_kb",
        ],
        "preferred_agents": ["research_agent"],
        "supported_modes": ["research", "explore"],
        "tags": ["research", "evidence-based"],
        "body": """\
## Research Protocol

**Step 1 — Check prior knowledge:**
- Call `read_kb` first. If relevant prior research exists, note it before new searches.

**Step 2 — Multi-angle search (minimum 3 angles):**
1. The direct question
2. A contrarian framing ("risks of X", "criticism of Y")
3. A temporal framing ("X in 2025", "latest developments in Y")
- Invoke `research_agent` for structured multi-source synthesis.

**Step 3 — Source quality rules:**
- Prefer primary sources over secondary (blogs, summaries).
- Note publication dates — time-sensitive claims need recent sources.
- When sources conflict, present both views.

**Step 4 — Output format:**
1. Executive summary (2–3 sentences)
2. Findings — each factual claim cited as [Source: Title](URL)
3. Competing perspectives
4. Gaps & uncertainties
5. Sources list

**Step 5 — Persist:**
- Call `write_kb` to save key findings for future sessions.
""",
    },
    {
        "name": "debug_session",
        "description": "Systematic debugging protocol — traceback-first, evidence-driven, root-cause focused.",
        "triggers": [
            "debug", "fix bug", "error", "traceback",
            "exception", "not working", "broken", "fails", "crash",
        ],
        "preferred_tools": ["read_file", "run_shell", "git_ops", "search_files"],
        "preferred_agents": ["code_agent", "qa_agent"],
        "supported_modes": ["code"],
        "tags": ["debugging", "bug fix"],
        "body": """\
## Debug Session Protocol

**Step 1 — Read the full error:**
- Read the complete traceback. Identify: exception type, failing line, call chain.

**Step 2 — Read the failing code:**
- Call `read_file` on the file containing the failing line.
- Read ±20 lines around the failing line. Read called functions from the traceback.

**Step 3 — Check recent changes:**
- Call `git_ops` with `operation=log` for the failing file.
- Call `git_ops` with `operation=diff` to see exact recent changes.

**Step 4 — Reproduce:**
- Call `run_shell` to execute the minimal reproduction case before fixing.

**Step 5 — Fix and verify:**
- Apply the minimal targeted fix. Re-run reproduction case. Run module tests.

**Step 6 — Document:**
- Summarize: what broke, why, what the fix does. Was this a regression?

**Rules:** Fix root cause, not symptom. No suppressed errors. No workarounds.
""",
    },
    {
        "name": "deploy_checklist",
        "description": "Pre/post-deployment checklist — quality gates, step-by-step execution, health verification.",
        "triggers": [
            "deploy", "release", "ship", "go live",
            "push to production", "rollout", "publish",
        ],
        "preferred_tools": [
            "run_shell", "git_ops", "quality_gate", "secrets_scanner", "read_file",
        ],
        "preferred_agents": ["release_agent"],
        "supported_modes": ["operate"],
        "tags": ["deployment", "release", "operations"],
        "body": """\
## Deployment Checklist Protocol

**PRE-FLIGHT (required before any deployment step):**
1. `quality_gate` — no type errors, no lint failures, coverage threshold met.
2. `git_ops status` — no uncommitted changes.
3. `secrets_scanner` — zero secrets in code.
4. `dependency_auditor` — no known-vulnerable packages.
5. `git_ops diff` — final sanity check.

**DEPLOYMENT (verify-after discipline):**
For each step: state the command → state expected outcome → execute →
verify → if verification fails: STOP and report.

**POST-DEPLOYMENT:**
1. Run smoke tests.
2. Check service logs with `log_analyzer`.
3. Confirm deployed version matches expected tag/commit.
4. Call `write_kb` to record: what deployed, when, anomalies observed.

**Before starting:** note the rollback command. Never deploy without a known undo path.
""",
    },
]
