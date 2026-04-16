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
    """
    Default conversational mode — no structural constraints.
    """

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
    Exploration mode — model takes a broad, multi-perspective approach.

    Use this for research, learning, and open-ended questions where
    depth and breadth matter more than brevity.
    """

    @property
    def name(self) -> str:
        return "explore"

    @property
    def display_label(self) -> str:
        return "[EXPLORE]"

    @property
    def description(self) -> str:
        return "Broad exploration — multiple angles, edge cases, deep analysis."

    def augment_system_prompt(self, base_prompt: str) -> str:
        suffix = (
            "\n\n## Explore Mode\n"
            "Approach every question with intellectual breadth:\n"
            "- Consider at least two or three distinct perspectives or interpretations.\n"
            "- Identify assumptions and challenge them where appropriate.\n"
            "- Surface edge cases, counter-examples, or related concepts.\n"
            "- When relevant, compare alternatives and explain trade-offs.\n"
            "Show your reasoning openly. Depth and rigour are valued over brevity."
        )
        return base_prompt + suffix


class ResearchMode(ISessionMode):
    """
    Deep research mode — structured, evidence-driven, comprehensive analysis.

    Use when you need thorough investigation of a topic: the model is
    instructed to reason step by step, cite its knowledge sources, identify
    gaps, compare alternatives, and produce a well-structured report.
    """

    @property
    def name(self) -> str:
        return "research"

    @property
    def display_label(self) -> str:
        return "[RESEARCH]"

    @property
    def description(self) -> str:
        return "Deep research — structured analysis, evidence-driven, comprehensive."

    def augment_system_prompt(self, base_prompt: str) -> str:
        suffix = (
            "\n\n## Research Mode\n"
            "You are operating in deep research mode. Follow these principles:\n\n"
            "1. **Reason step by step** before drawing conclusions.\n"
            "2. **Structure your response** with clear headings and sections.\n"
            "3. **Cite knowledge sources** — note where information comes from "
            "(training data, well-known facts, inference) and flag uncertainty.\n"
            "4. **Cover multiple perspectives** — present competing viewpoints "
            "or interpretations where they exist.\n"
            "5. **Identify gaps** — explicitly state what is unknown, disputed, "
            "or outside your knowledge.\n"
            "6. **Compare alternatives** — where decisions or choices are involved, "
            "evaluate trade-offs systematically.\n"
            "7. **Summarise** — end with a concise summary of key findings.\n\n"
            "Depth, rigour, and intellectual honesty take priority over brevity."
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
    def name(self) -> str:
        return "code"

    @property
    def display_label(self) -> str:
        return "[CODE]"

    @property
    def description(self) -> str:
        return "Code-focused mode: reads/writes files, runs shell commands, uses git."

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


# ── Registry (single source of truth — DRY) ──────────────────────────────────

_REGISTRY: dict[str, ISessionMode] = {
    m.name: m for m in (ChatMode(), PlanMode(), ExploreMode(), ResearchMode(), CodeMode())
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
