# Citnega 9+ Specification (Horizontal Agent Platform)

Status: Draft for implementation  
Owner: Core Runtime + Product Architecture  
Date: 2026-04-14

## 1. Goal
Raise Citnega from current mixed maturity to a consistently high-quality horizontal agent platform with an externally defensible score above **9.0/10**, while delivering broader workflow coverage than Claude Code and Gemini CLI in local-first and enterprise-safe deployments.

Target outcome:
- Reliability and architecture consistency: production-grade.
- Feature surface: broader than code-only assistants (code + research + data + docs + ops + workflow orchestration).
- Governance: first-class approval, policy, and auditability.

## 2. Product Thesis
Citnega is not a coding shell; it is a **horizontal execution fabric** where an LLM orchestrates tools, agents, and workflows across domains with deterministic controls.

Differentiators to enforce:
- Local-first by default, remote-optional.
- Unified tool and agent plane with explicit policy/approval gates.
- Multi-mode execution (`chat`, `plan`, `explore`, `research`, `code`) with reproducible transitions.
- Run/event ledger that is replayable and auditable.

## 3. Current Critical Gaps (to close immediately)
1. Composition root drift between CLI/TUI and canonical bootstrap.
2. Context pipeline not fully config-driven in active runtime path.
3. Session metadata drift (`stub`/empty defaults) vs active runtime adapter/model.
4. Default model mismatch across settings and model registry.
5. Runtime shutdown race causing late cleanup failures.

## 4. Immediate Implementation Requirements (P0)
All P0 items are release blockers.

1. Single composition path:
- CLI/TUI bootstrap must delegate to canonical bootstrap.
- No parallel composition roots allowed.

2. Framework correctness:
- `direct` must be a first-class bootstrap framework option.
- Session manager default framework must match active adapter for strict validation correctness.

3. Context determinism:
- Handler chain must be instantiated from `settings.context.handlers` in order.
- Unknown handlers: warning or hard fail based on `strict_handler_loading`.
- `token_budget` enforced as terminal handler.

4. Session/model defaults:
- New sessions default to active adapter framework and top-priority model.
- Direct adapter must honor `SessionConfig.default_model_id` when provided.

5. Shutdown safety:
- Active-run bookkeeping must not drop cleanup tasks before `set_idle` persistence finishes.

## 5. Capability Targets to Exceed Competitors
The objective is not “more commands”; it is **more complete execution coverage**.

### 5.1 Horizontal Core Capabilities
1. Code workflows:
- Read/edit/write/search, shell execution, git ops, test loops, patch review.

2. Research workflows:
- Search + fetch + parse + synthesis with source traceability.

3. Data workflows:
- Structured transforms, tabular analysis, result packaging.

4. Documentation workflows:
- Spec generation, migration docs, release notes, traceability artifacts.

5. Operations workflows:
- Diagnostics, environment checks, recovery playbooks, policy-safe automation.

### 5.2 Mandatory New Built-in Tools (P1/P2)
1. `repo_map`:
- Fast architecture map (modules, dependency boundaries, hotspots).
- Output: machine-readable JSON + concise markdown summary.

2. `test_matrix`:
- Discover tests, bucket by speed/risk/component, execute selective suites.
- Output: failing clusters + likely owning modules.

3. `quality_gate`:
- Unified gate runner for format/lint/type/tests/contracts/security.
- Output: pass/fail with remediation checklist.

4. `artifact_pack`:
- Bundle run outputs (diffs, logs, summaries, metrics) for handoff/review.

### 5.3 Mandatory New Built-in Agents (P1/P2)
1. `orchestrator_agent`:
- DAG-based multi-step execution with bounded retries and rollback hooks.

2. `qa_agent`:
- Regression-focused validation across changed files + impacted modules.

3. `security_agent`:
- Policy and secret-safety checks on tool inputs/outputs and code changes.

4. `release_agent`:
- Release readiness: changelog, migration notes, risk matrix, rollback plan.

## 6. Architecture Requirements
1. Layering:
- Protocol -> runtime -> adapters/tools/agents -> apps.
- No app-layer logic in runtime internals.

2. Composition:
- Exactly one canonical bootstrap API.
- Entry points only parameterize; never rewire independently.

3. Runtime invariants:
- Single active run per session.
- Event queue ownership explicit (producer vs consumer cleanup).
- Cancellation must be idempotent and observable.

4. Context system:
- Config-defined chain, deterministic order, per-handler timeout, degraded-mode telemetry.

5. Tool/agent contracts:
- Every callable must declare input schema, safety metadata, and deterministic output envelope.

## 7. Safety, Policy, and Governance
1. Policy enforcement for network and path access must be default-on configurable.
2. Approval workflows for mutating/high-risk tools must be mandatory.
3. Full audit trail:
- Callable start/end, input summary, output summary, policy decisions.
4. Secrets handling:
- No raw secret echo in events/logs; mandatory scrubbing.

## 8. UX and Product Surface
1. TUI/CLI parity for session lifecycle, model/mode control, and diagnostics.
2. Rich slash-command control plane for workflows and agent orchestration.
3. Replayability:
- Run replay for investigation and onboarding.
4. Discoverability:
- `/agent` and `/tools` must reflect live registry state always.

## 9. Scoring Rubric (must average >9.0)
Weighted score:
1. Reliability and correctness (25%)
2. Architecture coherence and maintainability (20%)
3. Horizontal capability breadth (20%)
4. Safety/governance/auditability (15%)
5. UX and operator ergonomics (10%)
6. Performance and startup/turn latency (10%)

Pass criteria:
- No category below 8.5.
- Reliability >= 9.2.
- Architecture coherence >= 9.0.
- Horizontal capability breadth >= 9.0.

## 10. Delivery Plan
### Phase P0 (Now)
- Composition unification, context determinism, session/model defaults, shutdown race fix.
- Update docs and traceability for corrected architecture.

### Phase P1
- `repo_map`, `test_matrix`, `quality_gate` tools.
- `orchestrator_agent` and `qa_agent`.
- End-to-end golden tests for multi-tool plans.

### P1 Progress Snapshot (2026-04-14)
- Implemented: `repo_map` tool.
- Implemented: `quality_gate` tool.
- Implemented: `test_matrix` tool.
- Implemented: `qa_agent` specialist.
- Implemented: `orchestrator_agent`.
- Implemented: golden multi-tool orchestration scenarios.

### P2 Progress Snapshot (2026-04-14)
- Implemented: `artifact_pack` tool.
- Implemented: `security_agent` specialist.
- Implemented: `release_agent` specialist.
- Implemented: unit and integration coverage for P2 callables and registry wiring.
- Implemented: environment policy templates (`dev`, `team`, `locked_down`) with bootstrap-time enforcement.
- Implemented: cache layer for `repo_map` and non-executing `test_matrix` discovery.
- Implemented: safe static-scan cache path for `security_agent` (quality-gate path remains uncached).

### P3 Seed Progress (2026-04-14)
- Implemented: runtime contract verification for dynamically onboarded tools/agents/workflows.
- Implemented: registration-time guardrails so invalid callables are rejected before entering live registries.
- Implemented: workspace bundle onboarding verification (manifest + provenance + optional signature).
- Implemented: bootstrap and hot-reload gates that fail closed on invalid third-party bundles.
- Implemented: remote worker dispatch model (`execution_target=remote`) in orchestrator workflows.
- Implemented: signed run envelopes (HMAC) with verification gates for remote dispatch.
- Implemented: envelope key IDs plus verifier keyring support for non-disruptive key rotation.
- Implemented: network transport backend for remote execution (`worker_mode=http`) with auth/timeout/TLS controls.
- Implemented: reference remote worker HTTP service process with explicit callable allowlist and declared isolation profile (`process`/`container`).
- Implemented: built-in Docker/Podman launcher for `service_isolation_profile=container`.
- Implemented: optional HTTPS + mTLS support for remote workers with server/client certificate configuration.
- Implemented: remote secret bootstrap command and key-rotation playbook for operators.
- Implemented: reproducible horizontal demo runner and independent scorecard evidence generation.
- Implemented: CI-required scorecard gate (threshold + all checks pass) with artifact upload.
- Implemented: benchmark matrix evidence runner, lane threshold policy, and CI matrix execution across OS/Python lanes.
- Implemented: persisted benchmark history with per-lane trend/regression deltas across CI runs.
- Implemented: signed benchmark publication manifests and publication history for branch-aware dashboard ingestion.
- Implemented: remote orchestration soak coverage for repeated retries and timeout/cancel-style recovery.

### Phase P2
- `security_agent`, `release_agent`, `artifact_pack`.
- Policy templates by environment (dev/team/locked-down).
- Performance optimization and caching.

### Phase P3
- Remote worker/agent execution with signed run envelopes.
- Marketplace-grade plugin/tool onboarding with contract verification.

## 11. Test and Quality Gates (non-negotiable)
1. Unit coverage for every new tool/agent contract.
2. Integration scenarios for each session mode and plan approval transitions.
3. Replay tests for event fidelity.
4. Failure-path tests (timeouts, policy denies, adapter outages, cancellation races).
5. Static and style gates:
- `ruff`, `mypy` (strict profile for core packages), `pytest`, import contracts.

Release only if all gates pass in CI and local reproducibility is verified.

## 12. Definition of Done for “9+”
A release qualifies as 9+ only when:
1. P0 + P1 are implemented and green.
2. Score rubric thresholds are met in independent review.
3. At least three complex horizontal workflows succeed end-to-end without manual patching:
- Code refactor + tests + release notes.
- Research synthesis with citations + persisted KB.
- Ops diagnosis + remediation plan + verification run.

## 13. Governance Notes
- Backward compatibility: existing sessions/workspaces must load without manual migration.
- Any temporary compatibility shim must have explicit removal milestone.
- Architecture drift from this spec requires an ADR update before merge.
