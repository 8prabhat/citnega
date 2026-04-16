# Citnega v6 Release Checklist

Use this checklist before tagging a release candidate. All items must be checked
by the responsible area owner.

---

## A. Quality Gates  _(Runtime owner)_

- [ ] `pytest` — 0 failures, 0 errors (skips allowed for optional dependencies)
- [ ] `ruff check citnega/ apps/ tests/` — 0 errors introduced since last release
- [ ] `mypy citnega apps --ignore-missing-imports` — 0 errors
- [ ] `lint-imports` — 5/5 import contract checks pass
- [ ] `citnega doctor` — 10/10 checks pass on a clean install

---

## B. Functional Requirements  _(Runtime owner)_

- [ ] FR-BOOT-001: `stub` framework auto-migrated; `strict_framework_validation` enforced
- [ ] FR-BOOT-002: Model gateway lifecycle integration — `skip_provider_health_check` flag tested
- [ ] FR-BOOT-003: `StartupDiagnosticsEvent` emitted at bootstrap (check event log)
- [ ] FR-RUN-001: `RunTerminalReasonEvent` always precedes `RunCompleteEvent`
- [ ] FR-RUN-002: Tool-round events (`CallableStartEvent`/`CallableEndEvent`) correctly paired
- [ ] FR-RUN-003: Cancellation produces `reason = "cancelled"` in `RunTerminalReasonEvent`
- [ ] FR-CTX-001: Handler chain configurable; `strict_handler_loading` and `handler_timeout_ms` tested
- [ ] FR-CTX-002: `ContextTruncatedEvent` emitted when token budget trimming occurs
- [ ] FR-CTX-003: `/compact` compaction flow works end-to-end
- [ ] FR-POL-001: `workspace_root` restricts file tool paths
- [ ] FR-POL-002: `enforce_network_policy = true` blocks outbound tool calls
- [ ] FR-POL-003: Approval denied flow produces correct state transitions

---

## C. Tooling and KB  _(Tools owner)_

- [ ] FR-TOOL-001: All 13 built-in tools pass `test_tool_contracts.py` suite
- [ ] FR-TOOL-002: `write_file` / `edit_file` respect policy bounds
- [ ] FR-TOOL-003: `kb_add`, `kb_search`, `kb_export` all functional
- [ ] FR-KB-001: KB ingestion handles chunking, dedup, and session scoping
- [ ] FR-KB-002: FTS5 retrieval returns relevant results (manual spot check)
- [ ] FR-KB-003: JSONL and Markdown export options both produce valid files

---

## D. CLI and TUI Parity  _(UX owner)_

- [ ] FR-UX-001: Session create / list / rename / delete works in both CLI and TUI
- [ ] FR-UX-002: Run cancel and tool approval work in both CLI and TUI
- [ ] FR-UX-003: All 19 slash commands registered; `/help` lists them all
- [ ] Workspace commands: `/setworkfolder`, `/createtool`, `/createagent`, `/createworkflow`, `/refresh` all functional in TUI
- [ ] `citnega replay --run-id <id>` produces readable timeline output
- [ ] `citnega replay --run-id <id> --json` produces valid JSONL

---

## E. Golden Scenarios  _(Runtime owner)_

Run `pytest tests/integration/test_golden_scenarios.py -v` and verify:

- [ ] GS-01: Simple conversation — `RunCompleteEvent` with `final_state = "completed"`
- [ ] GS-02: Tool-assisted conversation — tool call events present
- [ ] GS-03: Approval denied — run ends with `final_state = "cancelled"`
- [ ] GS-04: Cancellation mid-stream — `RunTerminalReasonEvent.reason = "cancelled"`
- [ ] GS-05: Context budget pressure — `ContextTruncatedEvent` emitted
- [ ] GS-06: KB ingestion and retrieval — retrieved content present in context
- [ ] GS-07: Framework migration — session with deprecated framework auto-migrated

---

## F. Event and Config Contracts  _(Runtime owner)_

- [ ] Section 10 events all exported from `citnega.packages.protocol.events`:
  - [ ] `RunTerminalReasonEvent`
  - [ ] `ContextTruncatedEvent`
  - [ ] `RouterDecisionEvent`
  - [ ] `StartupDiagnosticsEvent`
- [ ] All Section 10.2 config keys present in `settings.toml` defaults with correct types
- [ ] `CanonicalEvent` union includes all 4 new event types

---

## G. Documentation  _(All owners)_

- [ ] `docs/architecture.md` — runtime composition and event flow diagrams current
- [ ] `docs/traceability_matrix.md` — all FR IDs mapped to passing tests
- [ ] `docs/doctor_schema.md` — doctor output schema matches current implementation
- [ ] `docs/migration_notes.md` — deprecated values and new config keys documented
- [ ] `docs/remote_worker_service.md` — remote worker operator guide current
- [ ] `docs/decisions/future.md` — post-v1 items listed and up to date
- [ ] `README.md` — installation and quickstart accurate for v6

---

## H. Final Sign-off

| Area | Owner | Status | Date |
|------|-------|--------|------|
| Runtime | — | ☐ | |
| Tools | — | ☐ | |
| UX (CLI/TUI) | — | ☐ | |

Release is **approved** when all three rows are checked and all gate items above are green.

---

## I. 9+ Progress Gates  _(Architecture owner)_

- [ ] FR-P2-TOOL-001: `artifact_pack` bundles manifest + summary + optional zip
- [ ] FR-P2-AGENT-001: `security_agent` reports prioritized security findings
- [ ] FR-P2-AGENT-002: `release_agent` emits release verdict + rollback plan
- [ ] FR-P2-POL-001: policy templates (`dev`/`team`/`locked_down`) applied at bootstrap
- [ ] FR-P2-PERF-001: cache hit path validated for `repo_map`
- [ ] FR-P2-PERF-002: cache hit path validated for non-executing `test_matrix`
- [ ] FR-P2-PERF-003: cache hit path validated for static `security_agent` scans
- [ ] FR-P3-ONBOARD-001: dynamic onboarding contract verification rejects invalid callables
- [ ] FR-P3-ONBOARD-002: workspace onboarding requires valid manifest + provenance checks
- [ ] FR-P3-ONBOARD-003: signed third-party bundles verified (fail-closed when required)
- [ ] FR-P3-ONBOARD-004: CI workspace-onboarding gate step is green
- [ ] FR-P3-REMOTE-001: orchestrator remote worker execution path (`execution_target=remote`) is green
- [ ] FR-P3-REMOTE-002: signed run envelope verification is enforced for remote dispatch
- [ ] FR-P3-REMOTE-003: HTTP remote transport mode (`worker_mode=http`) is validated end-to-end
- [ ] FR-P3-REMOTE-004: reference remote worker service enforces explicit allowlist and health/isolation metadata
- [ ] FR-P3-REMOTE-005: remote soak suite is green for retries and timeout/cancel-style recovery
- [ ] FR-P3-REMOTE-006: remote envelope auth supports keyed rotation with verifier keyrings
- [ ] FR-P3-REMOTE-007: container isolation profile launches a real Docker/Podman worker
- [ ] FR-P3-REMOTE-008: remote HTTP workers support HTTPS + optional mTLS
- [ ] FR-P3-OPS-001: remote secret bootstrap command and rotation playbook are available
- [ ] FR-EVID-001: horizontal workflow evidence generated (`docs/evidence/horizontal_demos_latest.md`)
- [ ] FR-EVID-002: independent scorecard generated (`docs/evidence/9plus_scorecard_latest.md`) with score >= 9.0
- [ ] FR-EVID-003: CI scorecard gate job is green and publishes latest evidence artifacts
- [ ] FR-EVID-004: benchmark matrix CI job is green across OS/Python lanes
- [ ] FR-EVID-005: benchmark threshold gate is green against `docs/evidence/benchmark_thresholds.json`
- [ ] FR-EVID-006: benchmark history/trend evidence generated (`docs/evidence/benchmark_matrix_history.jsonl`)
- [ ] FR-EVID-007: signed benchmark publication evidence generated (`docs/evidence/benchmark_publication_latest.json`)
- [ ] `docs/spec_9plus_tracker.md` updated with current phase status
