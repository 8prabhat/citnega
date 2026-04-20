---
name: code_review
description: Structured code review protocol — diff-first, evidence-driven, severity-graded.
triggers:
  - code review
  - PR review
  - review changes
  - review this
  - review the diff
  - review pull request
preferred_tools:
  - git_ops
  - read_file
  - quality_gate
  - repo_map
preferred_agents:
  - code_agent
  - qa_agent
supported_modes:
  - review
tags:
  - review
  - code quality
---

## Code Review Protocol

When this skill is active, perform a structured review using the following steps:

**Step 1 — Read the diff (mandatory first action):**
- Call `git_ops` with `operation=diff` to see all changed lines.
- If specific files are named, call `read_file` on each one.
- Never comment on code you have not read.

**Step 2 — Read surrounding context (parallel):**
- Read the test files for changed modules.
- Read any interfaces or base classes referenced by changed code.
- Call `repo_map` for architectural context.

**Step 3 — Run automated checks:**
- Call `quality_gate` to get lint warnings, type errors, and complexity metrics.

**Step 4 — Produce findings table:**

| Severity | File:Line | Finding | Recommendation |
|----------|-----------|---------|----------------|
| HIGH | auth.py:47 | ... | ... |

Look specifically for:
- **Bugs**: incorrect logic, off-by-one errors, race conditions
- **Regressions**: behavior that worked before may break after this change
- **Missing tests**: changed code paths with no test coverage
- **Security**: see security_review skill for detailed security checks
- **Performance**: O(n²) loops, missing indexes, unbounded memory growth
- **API contracts**: breaking changes to public interfaces or serialization formats

End with a **verdict**: Approved / Needs minor changes / Needs major revision.
