"""
Session modes — concrete ISessionMode implementations + registry.

Modes are stateless singletons registered in ``_REGISTRY``.  Callers
use ``get_mode(name)`` — they never construct concrete classes directly.

Adding a new mode: implement ``ISessionMode``, instantiate it, and add
it to ``_REGISTRY``.  No other file needs to change (OCP).
"""

from __future__ import annotations

from citnega.packages.protocol.interfaces.session_mode import ISessionMode

# ── Concrete modes ────────────────────────────────────────────────────────────


class ChatMode(ISessionMode):
    """Default conversational mode — no structural constraints."""

    @property
    def name(self) -> str:
        return "chat"

    @property
    def display_label(self) -> str:
        return ""

    @property
    def description(self) -> str:
        return "Default conversational mode."

    def augment_system_prompt(self, base_prompt: str) -> str:
        return base_prompt  # no-op


class PlanMode(ISessionMode):
    """
    Two-phase planning mode.

    Phase 1 (draft): the model generates ONLY a numbered plan — no execution.
    The user reviews the plan and chooses to proceed or cancel.
    Phase 2 (execute): the model executes the approved plan step by step.

    The controller drives the phases; this mode supplies the correct system
    prompt for each phase via ``augment_system_prompt(base, phase=...)``.
    """

    PHASE_DRAFT = "draft"
    PHASE_EXECUTE = "execute"

    @property
    def name(self) -> str:
        return "plan"

    @property
    def display_label(self) -> str:
        return "[PLAN]"

    @property
    def description(self) -> str:
        return "Two-phase: draft a plan → review → execute."

    @property
    def temperature(self) -> float:
        return 0.4

    def augment_system_prompt(self, base_prompt: str, phase: str = PHASE_DRAFT) -> str:
        if phase == self.PHASE_EXECUTE:
            suffix = (
                "\n\n## Plan Execution Mode\n"
                "The user has reviewed and approved a plan. "
                "Execute it step by step, clearly indicating each step as you go. "
                "Be thorough and complete."
            )
        else:  # draft phase
            suffix = (
                "\n\n## Plan Draft Mode\n"
                "Your task is to produce a plan ONLY — do NOT execute it.\n"
                "Format:\n"
                "**Plan:**\n"
                "1. [First step]\n"
                "2. [Second step]\n"
                "…\n\n"
                "Keep each step concise and actionable. "
                "End your response immediately after the last step. "
                "Do not write any introduction, explanation, or execution."
            )
        return base_prompt + suffix


class ExploreMode(ISessionMode):
    """
    Exploration mode — agentic, tool-driven, multi-perspective deep research.

    The model is required to gather real information via tools before answering:
    web search for current facts, file reads for codebase context, specialist
    agents for domain-specific depth.  max_tool_rounds is raised to 12 so the
    loop has room to follow multiple threads.
    """

    @property
    def name(self) -> str:
        return "explore"

    @property
    def display_label(self) -> str:
        return "[EXPLORE]"

    @property
    def description(self) -> str:
        return "Agentic deep exploration — calls tools and agents, multiple angles, edge cases."

    @property
    def max_tool_rounds(self) -> int:
        return 12

    @property
    def temperature(self) -> float:
        return 0.8

    def augment_system_prompt(self, base_prompt: str) -> str:
        suffix = (
            "\n\n## Explore Mode — Agentic Deep Research\n\n"
            "You are in **explore mode**. This is NOT a conversational response mode — "
            "it is an **active investigation** mode. You MUST gather information using "
            "tools before writing your final answer.\n\n"
            "### Mandatory exploration protocol\n\n"
            "**Step 1 — Orient** (do this first, before any analysis):\n"
            "  - If the question involves current events, recent facts, or anything that "
            "could have changed: call `search_web` immediately with 2–3 targeted queries.\n"
            "  - If the question involves a codebase or files: call `list_dir`, "
            "`search_files`, and `repo_map` to understand the structure first.\n"
            "  - If relevant prior research exists: call `read_kb` to retrieve it.\n\n"
            "**Step 2 — Deep dive** (parallel where possible):\n"
            "  - Call `read_webpage` or `fetch_url` for any key sources found.\n"
            "  - For security topics: invoke `security_agent` — it has specialised tools.\n"
            "  - For research/analysis topics: invoke `research_agent` for structured investigation.\n"
            "  - For code topics: invoke `code_agent` to examine implementation details.\n"
            "  - Run multiple tool calls **in a single response turn** when sub-tasks are independent.\n\n"
            "**Step 3 — Synthesise**:\n"
            "  - After gathering real data, write a thorough response covering:\n"
            "    • At least two or three distinct perspectives or interpretations\n"
            "    • Assumptions you are making and where they may not hold\n"
            "    • Edge cases, counter-examples, and trade-offs\n"
            "    • What you found vs. what remains uncertain\n"
            "  - For each factual claim from a web source, cite it inline as "
            "[Source: Title](URL).\n"
            "  - Add a **Sources** section at the end listing all URLs used.\n\n"
            "**NEVER** skip Step 1 and 2 to go straight to a text answer. "
            "If you lack a tool for something, say so explicitly — but first exhaust "
            "the tools you do have. Depth and evidence beat fast opinions every time.\n\n"
            "You have up to 12 tool-calling rounds — use them."
        )
        return base_prompt + suffix


class ResearchMode(ISessionMode):
    """
    Deep research mode — fully agentic, structured, evidence-driven.

    The model MUST use tools to gather live information before writing.
    Raises max_tool_rounds to 15 to allow multi-thread investigation.
    """

    @property
    def name(self) -> str:
        return "research"

    @property
    def display_label(self) -> str:
        return "[RESEARCH]"

    @property
    def description(self) -> str:
        return "Fully agentic deep research — web search, agents, structured report."

    @property
    def max_tool_rounds(self) -> int:
        return 15

    @property
    def temperature(self) -> float:
        return 0.3

    def augment_system_prompt(self, base_prompt: str) -> str:
        suffix = (
            "\n\n## Research Mode — Fully Agentic\n\n"
            "You are in **research mode**. You MUST actively use tools to gather "
            "current, primary information before writing your report.\n\n"
            "### Required research sequence\n\n"
            "1. **Gather** — before writing anything, run:\n"
            "   - `search_web` (2–4 queries from different angles)\n"
            "   - `read_kb` (retrieve any prior session notes)\n"
            "   - `read_webpage` / `fetch_url` for key sources found in search\n"
            "   - Invoke `research_agent` for structured multi-source investigation\n\n"
            "2. **Verify** — cross-check conflicting claims across sources; "
            "note where sources agree and disagree.\n\n"
            "3. **Write** — produce a structured report:\n"
            "   - **Executive summary** (2–3 sentences)\n"
            "   - **Findings** — headed sections; use inline citation format "
            "[Source: Title](URL) after each factual claim\n"
            "   - **Competing perspectives** (present disagreements fairly)\n"
            "   - **Gaps & uncertainties** (what is unknown or disputed)\n"
            "   - **Conclusions & trade-offs**\n"
            "   - **Sources** — list all URLs used at the end of the report\n\n"
            "4. **Save** — call `write_kb` to persist key findings for future sessions.\n\n"
            "You have up to 15 tool-calling rounds. Use `research_agent` as your "
            "primary investigator — it parallelises searches and handles source synthesis. "
            "Never guess when you can verify. Never summarise from memory when you can search."
        )
        return base_prompt + suffix


class CodeMode(ISessionMode):
    """
    Code-focused mode for programming, debugging, and codebase operations.

    In this mode the model is instructed to:
      - Use filesystem tools proactively (read_file, list_dir, search_files)
      - Make surgical edits via edit_file rather than rewriting whole files
      - Verify changes by running tests / linting with run_shell
      - Keep git_ops in mind for status/diff/commit
      - Be concise — code speaks louder than explanation
    """

    @property
    def max_tool_rounds(self) -> int:
        return 10

    @property
    def name(self) -> str:
        return "code"

    @property
    def display_label(self) -> str:
        return "[CODE]"

    @property
    def description(self) -> str:
        return "Code-focused mode: reads/writes files, runs shell commands, uses git."

    @property
    def temperature(self) -> float:
        return 0.2

    def augment_system_prompt(self, base_prompt: str) -> str:
        suffix = (
            "\n\n## Code Mode\n"
            "You are in **code mode** — a programming-focused environment with full "
            "filesystem, shell, and git access.\n\n"
            "**How to work:**\n"
            "1. **Explore first** — use `list_dir` / `search_files` to orient yourself "
            "before reading or writing.\n"
            "2. **Read before editing** — call `read_file` to get exact content; "
            "then use `edit_file` (find/replace) for surgical changes.\n"
            "3. **Write new files** with `write_file` when creating from scratch.\n"
            "4. **Run commands** with `run_shell` for tests, linting, builds, or any "
            "shell operation.\n"
            "5. **Version control** — use `git_ops` for status, diff, log, add, commit.\n"
            "6. **Persistent memory** — save key findings to the knowledge base with "
            "`write_kb`; retrieve them with `read_kb`.\n\n"
            "**Rules:**\n"
            "- Follow existing code style — no unnecessary reformatting.\n"
            "- Prefer minimal, targeted edits over rewrites.\n"
            "- Always show diffs or summaries of changes made.\n"
            "- If a task seems risky (deleting files, force-push), confirm with the user first."
        )
        return base_prompt + suffix


class ReviewMode(ISessionMode):
    """
    Professional code review mode — evidence-driven, tool-mandated.

    Requires the model to read the diff and context before commenting.
    Raises max_tool_rounds to 8 to allow thorough evidence gathering.
    """

    @property
    def name(self) -> str:
        return "review"

    @property
    def display_label(self) -> str:
        return "[REVIEW]"

    @property
    def description(self) -> str:
        return "Code review mode: prioritize bugs, regressions, and missing tests."

    @property
    def max_tool_rounds(self) -> int:
        return 8

    @property
    def temperature(self) -> float:
        return 0.3

    def augment_system_prompt(self, base_prompt: str) -> str:
        suffix = (
            "\n\n## Review Mode — Mandatory Protocol\n\n"
            "You are a senior code reviewer. You MUST gather evidence before commenting.\n\n"
            "### Required steps (do not skip any)\n\n"
            "**Step 1 — Read the diff** (mandatory first action):\n"
            "  - Call `git_ops` with operation='diff' to see all changed lines.\n"
            "  - If specific files are named, call `read_file` on each.\n\n"
            "**Step 2 — Read context** (call in parallel):\n"
            "  - Read surrounding code in changed files.\n"
            "  - Check test files for the changed modules.\n"
            "  - Run `repo_map` to understand architectural context.\n\n"
            "**Step 3 — Run static checks**:\n"
            "  - Call `quality_gate` to get lint, type, and complexity signals.\n\n"
            "**Step 4 — Write findings** (structured format only):\n"
            "  For each finding, cite the exact file and line number.\n\n"
            "  **[SEVERITY] file.py:line — issue description**\n"
            "  Why it matters: ...\n"
            "  Recommendation: ...\n\n"
            "Severity levels: CRITICAL (data loss/security) | HIGH (bug/regression) "
            "| MEDIUM (correctness/coverage) | LOW (style/clarity) | INFO (observation).\n\n"
            "**Never** comment on code you have not read. **Never** guess at line numbers. "
            "**Always** cite the diff or file read that supports each finding.\n\n"
            "You have up to 8 tool-calling rounds — use them to build evidence before writing."
        )
        return base_prompt + suffix


class OperateMode(ISessionMode):
    """
    Operational mode — runbook discipline with mandatory verification.

    Every mutating action is stated, executed, then verified before proceeding.
    Raises max_tool_rounds to 8 to allow thorough pre/post checks.
    """

    @property
    def name(self) -> str:
        return "operate"

    @property
    def display_label(self) -> str:
        return "[OPERATE]"

    @property
    def description(self) -> str:
        return "Operational mode: execute controlled multi-step runbooks and checks."

    @property
    def max_tool_rounds(self) -> int:
        return 8

    @property
    def temperature(self) -> float:
        return 0.2

    def augment_system_prompt(self, base_prompt: str) -> str:
        suffix = (
            "\n\n## Operate Mode — Runbook Protocol\n\n"
            "You are executing a controlled operational procedure. "
            "Every action must be verified before proceeding.\n\n"
            "### Mandatory execution protocol\n\n"
            "**Before each mutating step:**\n"
            "  - State the exact command or action you are about to take.\n"
            "  - State the expected outcome.\n"
            "  - State the rollback plan if it fails.\n\n"
            "**After each mutating step:**\n"
            "  - Verify success: call `run_shell` or `git_ops` to confirm the expected state.\n"
            "  - If verification fails, STOP and report the discrepancy before continuing.\n\n"
            "**Tool protocol:**\n"
            "  - Use `run_shell` for all system commands.\n"
            "  - Use `git_ops` for all version control operations.\n"
            "  - Use `read_file` / `list_dir` to verify file state after writes.\n"
            "  - Never assume a step succeeded — always check.\n\n"
            "**Safety rules:**\n"
            "  - Do not run destructive operations (rm -rf, DROP TABLE, force push) "
            "without explicit user confirmation in this conversation.\n"
            "  - If a step is ambiguous, ask before executing — not after.\n\n"
            "You have up to 8 tool-calling rounds per response. "
            "Use verification rounds generously."
        )
        return base_prompt + suffix


class AutonomousMode(ISessionMode):
    """
    Autonomous agent mode — self-directed, goal-completion-focused.

    Used automatically for sessions with session_type='autonomous'.
    The agent is instructed to:
      - Pursue the stated goal independently until complete.
      - Use OrchestratorAgent for multi-step tasks with replanning on failure.
      - Self-monitor progress and verify outcomes after each action.
      - Call any available tool or specialist without asking permission.
      - Report blockers only when genuinely stuck after retrying.

    Tool budget is 30 rounds (set by runner); all tools are available (no
    mode-based exclusions). Temperature is low to keep execution deterministic.
    """

    @property
    def name(self) -> str:
        return "autonomous"

    @property
    def display_label(self) -> str:
        return "[AUTO]"

    @property
    def description(self) -> str:
        return "Autonomous long-running agent — self-directed goal completion."

    @property
    def max_tool_rounds(self) -> int:
        return 30

    @property
    def temperature(self) -> float:
        return 0.2

    def augment_system_prompt(self, base_prompt: str) -> str:
        suffix = (
            "\n\n## Autonomous Agent Mode\n\n"
            "You are running as an **autonomous agent**. There is no human in the loop "
            "for this session. Your job is to **complete the stated goal** independently "
            "and report the outcome.\n\n"
            "### Execution principles\n\n"
            "1. **Act, don't ask** — use every tool and specialist available without "
            "requesting permission. You have full access to all registered tools.\n\n"
            "2. **Multi-step tasks → use OrchestratorAgent** — for goals requiring "
            "2+ sequential steps, invoke `orchestrator_agent` with `replan_on_failure=true` "
            "and `fail_fast=false`. This enables adaptive replanning when a step fails.\n\n"
            "3. **Verify outcomes** — after each mutating action (file write, API call, "
            "shell command), confirm the result before proceeding to the next step.\n\n"
            "4. **Replan on failure** — if a tool or agent call fails, try an alternative "
            "approach before giving up. Exhaust at least two alternatives before reporting "
            "a blocker.\n\n"
            "5. **Self-monitor progress** — after every 3–4 tool calls, briefly assess: "
            "am I making progress toward the goal? If not, pivot strategy.\n\n"
            "6. **Report blockers, not questions** — if genuinely stuck after retrying, "
            "state what you tried, why it failed, and what information would unblock you.\n\n"
            "7. **Summarise at the end** — when the goal is achieved, write a brief "
            "completion summary: what was done, what was produced, any caveats.\n\n"
            "You have up to 30 tool-calling rounds. Use them efficiently — "
            "parallel tool calls in a single turn when sub-tasks are independent."
        )
        return base_prompt + suffix


class AutoResearchMode(ISessionMode):
    """
    Autonomous deep research mode — KB-first, multi-angle, cross-verified.

    Capabilities:
      - KB-first check avoids re-researching known topics
      - 3 angle-queries per sub-question for broad coverage
      - Source quality scoring before reading (recency, authority, relevance)
      - Cross-verification across sources (VERIFIED vs UNVERIFIED)
      - Structured fact extraction with provenance (avoids context explosion)
      - Self-assessment completeness score with adaptive re-search
      - Mandatory structured 7-section report output
    """

    @property
    def name(self) -> str:
        return "auto_research"

    @property
    def display_label(self) -> str:
        return "[AUTO-RESEARCH]"

    @property
    def description(self) -> str:
        return (
            "Autonomous deep research loop — KB-first, multi-angle, "
            "cross-verified, cited structured report."
        )

    @property
    def max_tool_rounds(self) -> int:
        return 40

    @property
    def temperature(self) -> float:
        return 0.4

    def augment_system_prompt(self, base_prompt: str, **kwargs) -> str:
        suffix = (
            "\n\n## Auto-Research Mode — Structured Research Protocol\n\n"
            "You are an autonomous research agent executing a structured 9-phase methodology.\n\n"
            "**Phase 1 — Decompose:** Break the goal into 3–6 sub-questions and hypotheses.\n"
            "**Phase 2 — KB-first:** Call `read_kb` for each sub-question; skip already-answered ones.\n"
            "**Phase 3 — Parallel search:** Issue 2–3 angle-queries per unsatisfied sub-question via `search_web`.\n"
            "**Phase 4 — Score sources:** Before reading, score each URL on recency (1-5), "
            "authority (1-5), relevance (1-5); read top scorers only.\n"
            "**Phase 5 — Extract with provenance:** For each page, extract facts as:\n"
            "  `FACT: <claim> SOURCE: <url> DATE: <date> CONFIDENCE: <high/medium/low>`\n"
            "**Phase 6 — Cross-verify:** Flag claims found in 1 source as `[UNVERIFIED]`; "
            "2+ sources as `[VERIFIED]`.\n"
            "**Phase 7 — Write KB:** Call `write_kb` with structured facts, "
            'tags: `["auto_research", "<topic>", "verified"|"unverified"]`.\n'
            "**Phase 8 — Self-assess:** Score completeness 0–10. If <8, identify gaps and "
            "loop back to Phase 3 (max 2 extra passes).\n"
            "**Phase 9 — Synthesise:** Write structured report:\n"
            "  - Executive Summary (3 sentences)\n"
            "  - Findings (headed sections, inline citations `[Title](URL)`)\n"
            "  - Competing Perspectives (where sources disagree)\n"
            "  - Unverified Claims (single-source only)\n"
            "  - Gaps (what Phase 8 flagged)\n"
            "  - Sources list\n\n"
            "Tools available: `search_web`, `read_webpage`, `web_scraper`, `read_kb`, `write_kb`, "
            "`render_chart`, `fetch_url`, `get_datetime`.\n"
            "Invoke `auto_research_agent` to run the full structured investigation.\n"
            "Tool budget: 40 rounds. Use parallel tool calls for independent sub-questions."
        )
        return base_prompt + suffix


# ── Registry (single source of truth — DRY) ──────────────────────────────────

_REGISTRY: dict[str, ISessionMode] = {
    m.name: m
    for m in (
        ChatMode(),
        PlanMode(),
        ExploreMode(),
        ResearchMode(),
        CodeMode(),
        ReviewMode(),
        OperateMode(),
        AutonomousMode(),
        AutoResearchMode(),
    )
}

VALID_MODES: list[str] = list(_REGISTRY)


def get_mode(name: str) -> ISessionMode:
    """
    Return the ``ISessionMode`` for *name*.

    Falls back to ``ChatMode`` for unknown names — never raises.
    """
    return _REGISTRY.get(name, _REGISTRY["chat"])


def all_modes() -> list[ISessionMode]:
    """Return all registered modes in definition order."""
    return list(_REGISTRY.values())
