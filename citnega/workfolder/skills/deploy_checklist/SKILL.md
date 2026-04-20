---
name: deploy_checklist
description: Pre/post-deployment checklist — quality gates, step-by-step execution, health verification.
triggers:
  - deploy
  - release
  - ship
  - go live
  - push to production
  - rollout
  - publish
preferred_tools:
  - run_shell
  - git_ops
  - quality_gate
  - secrets_scanner
  - read_file
preferred_agents:
  - release_agent
supported_modes:
  - operate
tags:
  - deployment
  - release
  - operations
---

## Deployment Checklist Protocol

When this skill is active, treat every deployment as a controlled procedure with mandatory checkpoints.

**PRE-FLIGHT (required before any deployment step):**

1. **Quality gate** — call `quality_gate` and confirm: no type errors, no lint failures, test coverage meets threshold.
2. **Clean workspace** — call `git_ops` with `operation=status`. There must be no uncommitted changes.
3. **Secrets scan** — call `secrets_scanner` on the changed file set. Zero secrets in code before shipping.
4. **Dependency check** — verify no known-vulnerable packages (run `dependency_auditor` if available).
5. **Review the change** — call `git_ops` with `operation=diff` for a final sanity check.

**DEPLOYMENT (execute each step with verify-after discipline):**

For each deployment step:
1. State the exact `run_shell` command before executing.
2. State the expected outcome.
3. Execute it.
4. Verify: call `run_shell` to confirm the expected state (e.g. service health check, process listing, log tail).
5. If verification fails: STOP. Do not proceed to the next step. Report the discrepancy.

**POST-DEPLOYMENT:**

1. Run smoke tests via `run_shell`.
2. Check service logs for errors (use `log_analyzer` if available).
3. Confirm the deployed version matches the expected tag/commit.
4. Call `write_kb` to record: what was deployed, when, and any anomalies observed.

**Rollback plan:**
Before starting, always note the rollback command. Never deploy without a known undo path.
