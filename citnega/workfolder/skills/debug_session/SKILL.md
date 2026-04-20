---
name: debug_session
description: Systematic debugging protocol — traceback-first, evidence-driven, root-cause focused.
triggers:
  - debug
  - fix bug
  - error
  - traceback
  - exception
  - not working
  - broken
  - fails
  - crash
preferred_tools:
  - read_file
  - run_shell
  - git_ops
  - search_files
preferred_agents:
  - code_agent
  - qa_agent
supported_modes:
  - code
tags:
  - debugging
  - bug fix
---

## Debug Session Protocol

When this skill is active, follow this systematic debugging process:

**Step 1 — Read the full error:**
- Read the complete traceback or error message — do not skip lines.
- Identify: the exception type, the failing line, and the call chain above it.

**Step 2 — Read the failing code:**
- Call `read_file` on the file containing the failing line.
- Read at least 20 lines before and after the failing line for context.
- Read any called functions or methods that appear in the traceback.

**Step 3 — Check recent changes:**
- Call `git_ops` with `operation=log` and `file_path` of the failing file.
- Look for changes in the last 5–10 commits that could have introduced the bug.
- Call `git_ops` with `operation=diff` to see exact changes.

**Step 4 — Reproduce the bug:**
- Call `run_shell` to execute the minimal reproduction case.
- Confirm the error appears before attempting a fix.

**Step 5 — Fix and verify:**
- Apply the minimal targeted fix.
- Run the reproduction case again to confirm the error is gone.
- Run the test suite for the affected module: `run_shell` with the appropriate test command.

**Step 6 — Document the fix:**
- Summarize: what was broken, why it broke, what the fix does.
- Note: was this a regression? If so, which change introduced it?

**Rules:**
- Fix the root cause, not the symptom.
- Do not suppress errors with broad `except Exception: pass` unless intentional.
- Do not add workarounds that mask the bug — find and fix the actual source.
