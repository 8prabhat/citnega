# FR-to-Test Traceability Matrix

Maps every Functional Requirement from the v6 Functional Maturity Specification to the
test files and test functions that cover it.

---

## 6.1 Bootstrap and Runtime Composition

| FR ID | Requirement | Test file(s) | Key test(s) |
|-------|-------------|--------------|-------------|
| FR-BOOT-001 | Single framework truth — `stub` migrated at runtime | `tests/unit/runtime/test_sessions.py` | `test_deprecated_framework_migrated`, `test_get_session_migrates_stub` |
| FR-BOOT-001 | `strict_framework_validation` rejects unknown frameworks | `tests/unit/workspace/test_app_service_register.py`, `tests/integration/test_section10_integration.py` | `TestStrictHandlerLoading`, `TestStrictFrameworkValidation` |
| FR-BOOT-002 | Model gateway lifecycle — skip_provider_health_check wired | `tests/integration/bootstrap/test_bootstrap.py` | `test_bootstrap_creates_service`, `test_skip_provider_health_check` |
| FR-BOOT-003 | Startup consistency checks — `StartupDiagnosticsEvent` emitted | `tests/unit/protocol/test_section10_events.py`, `tests/integration/test_section10_integration.py` | `TestStartupDiagnosticsEvent`, `TestStartupDiagnosticsEventEmitted` |

---

## 6.2 Runner Execution and Streaming

| FR ID | Requirement | Test file(s) | Key test(s) |
|-------|-------------|--------------|-------------|
| FR-RUN-001 | Correct streaming loop semantics — `RunCompleteEvent` always emitted | `tests/integration/runtime/test_core_runtime.py`, `tests/integration/test_golden_scenarios.py` | `test_run_complete_always_emitted`, `GS-01` through `GS-07` |
| FR-RUN-001 | `RunTerminalReasonEvent` precedes `RunCompleteEvent` | `tests/unit/protocol/test_section10_events.py`, `tests/integration/test_section10_integration.py` | `TestRunTerminalReasonEvent`, `test_terminal_reason_comes_before_run_complete` |
| FR-RUN-002 | Tool-round determinism — `CallableStartEvent`/`CallableEndEvent` paired | `tests/integration/test_golden_scenarios.py`, `tests/integration/test_tool_agent_integration.py` | `test_tool_events_paired`, `GS-02` |
| FR-RUN-003 | Cancellation safety — `RunTerminalReasonEvent.reason == "cancelled"` | `tests/integration/test_golden_scenarios.py` | `GS-04 (test_gs04_cancellation)` |

---

## 6.3 Context Assembly and Memory

| FR ID | Requirement | Test file(s) | Key test(s) |
|-------|-------------|--------------|-------------|
| FR-CTX-001 | Config-driven handler chain — `handlers` list in settings wired | `tests/unit/config/test_section10_config.py`, `tests/unit/runtime/test_context.py` | `test_default_handlers_list`, `test_assembler_runs_handlers` |
| FR-CTX-001 | `strict_handler_loading` rejects unknown handler names | `tests/unit/config/test_loaders.py` | `test_invalid_handler_reported` |
| FR-CTX-001 | `handler_timeout_ms` applied per handler | `tests/unit/config/test_section10_config.py`, `tests/integration/test_section10_integration.py` | `TestHandlerTimeoutMs` |
| FR-CTX-002 | Token budget enforcement — `ContextTruncatedEvent` emitted | `tests/unit/protocol/test_section10_events.py`, `tests/integration/test_golden_scenarios.py` | `TestContextTruncatedEventExport`, `GS-05` |
| FR-CTX-003 | Conversation compaction integration | `tests/integration/runtime/test_compaction.py` | `test_compaction_runs`, `test_compact_slash_command` |

---

## 6.4 Policy and Approval Enforcement

| FR ID | Requirement | Test file(s) | Key test(s) |
|-------|-------------|--------------|-------------|
| FR-POL-001 | Effective path policy — workspace_root resolves to real path | `tests/unit/runtime/test_policy.py` | `test_path_allowed_within_workspace`, `test_path_blocked_outside_workspace` |
| FR-POL-002 | Network policy — `enforce_network_policy` blocks outbound | `tests/unit/runtime/test_policy.py` | `test_network_blocked_when_enforce_true`, `test_network_allowed_when_enforce_false` |
| FR-POL-003 | Approval workflow reliability — `ApprovalRequiredEvent` + response | `tests/integration/test_golden_scenarios.py` | `GS-03 (test_gs03_approval_denied)` |

---

## 6.5 Tooling System

| FR ID | Requirement | Test file(s) | Key test(s) |
|-------|-------------|--------------|-------------|
| FR-TOOL-001 | Tool contract normalization — all tools pass contract suite | `tests/unit/tools/test_tool_contracts.py` | `test_required_attrs_present`, `test_callable_type_is_tool`, `test_input_schema_has_valid_json_schema`, `test_name_is_snake_case` |
| FR-TOOL-002 | Write/Edit file usability within policy bounds | `tests/unit/tools/test_tools.py` | `test_write_creates_file`, `test_write_requires_approval_by_default` |
| FR-TOOL-003 | KB tools completeness — add/search/export all work | `tests/unit/tools/test_tools.py`, `tests/integration/kb/test_kb_integration.py` | `TestKBAddTool`, `TestKBSearchTool`, `TestKBExportTool` |

---

## 6.6 Agent Orchestration

| FR ID | Requirement | Test file(s) | Key test(s) |
|-------|-------------|--------------|-------------|
| FR-AGENT-001 | Core agent wiring integrity — all specialists instantiate | `tests/unit/agents/test_agents.py` | `test_all_specialists_instantiate`, `test_tool_whitelist_enforced` |
| FR-AGENT-002 | Specialist execution contract — `SpecialistOutput` returned | `tests/unit/agents/test_agents.py`, `tests/adapters/shared_suite.py` | `test_specialist_execute_returns_output`, `test_callable_type_specialist` |
| FR-AGENT-003 | Routing observability — `RouterDecisionEvent` exported and emitted | `tests/unit/protocol/test_section10_events.py` | `TestRouterDecisionEventExport` |

---

## 6.7 Knowledge Base Functionality

| FR ID | Requirement | Test file(s) | Key test(s) |
|-------|-------------|--------------|-------------|
| FR-KB-001 | Ingestion — chunking, dedup, session scoping | `tests/unit/kb/test_kb.py` | `TestChunker`, `TestIngestionPipeline`, `test_content_hash_set` |
| FR-KB-002 | Retrieval quality floor — FTS5 returns relevant results | `tests/integration/kb/test_kb_integration.py`, `tests/integration/test_golden_scenarios.py` | `test_search_returns_results`, `GS-06` |
| FR-KB-003 | Session and global export — JSONL + Markdown | `tests/unit/kb/test_kb.py` | `TestJSONLExporter`, `TestMarkdownExporter`, `test_export_all_session_scoped_jsonl`, `test_export_all_global_includes_all` |

---

## 6.8 CLI and TUI Functional Parity

| FR ID | Requirement | Test file(s) | Key test(s) |
|-------|-------------|--------------|-------------|
| FR-UX-001 | Session lifecycle parity — create/list/delete/rename in both CLI and TUI | `tests/integration/cli/test_cli.py`, `tests/unit/tui/test_slash_session.py` | `test_session_create`, `test_session_list`, `test_rename_with_name`, `test_delete_with_yes` |
| FR-UX-002 | Run controls parity — cancel, approve, compact in both | `tests/integration/cli/test_cli.py`, `tests/unit/cli/test_run_commands.py` | `test_cancel_run`, `test_approve_run` |
| FR-UX-003 | Slash command integrity — all commands registered, help accurate | `tests/unit/tui/test_slash_session.py`, `tests/unit/workspace/test_wizard_intercept.py` | `test_normal_slash_when_no_wizard`, `test_wizard_consumes_next_input`, `test_slash_registry_includes_workspace_skill_command` |

---

## 6.9 Functional Observability

| FR ID | Requirement | Test file(s) | Key test(s) |
|-------|-------------|--------------|-------------|
| FR-OBS-001 | Canonical event completeness — all 4 Section 10 events exported | `tests/unit/protocol/test_section10_events.py` | `test_exported_from_protocol_init` (×4), `test_in_canonical_event_union` (×2) |
| FR-OBS-001 | Event replay CLI reads JSONL log | `tests/unit/cli/test_replay_command.py` | `test_replay_happy_path`, `test_json_output`, `test_critical_only_filter` |
| FR-OBS-002 | Diagnostic commands — doctor check passes | `tests/integration/cli/test_cli.py` | `test_doctor_check_passes`, `test_doctor_json_output` |

---

## 6.10 Configuration and Migration Behavior

| FR ID | Requirement | Test file(s) | Key test(s) |
|-------|-------------|--------------|-------------|
| FR-CONF-001 | Strict config schema — all required keys present with correct defaults | `tests/unit/config/test_section10_config.py`, `tests/unit/config/test_loaders.py` | `TestRuntimeSettings`, `TestContextSettings`, `test_defaults_loaded` |
| FR-CONF-001 | Env var overrides work for all Section 10 keys | `tests/unit/config/test_section10_config.py` | `test_strict_framework_validation_env_override`, `test_handler_timeout_ms_env_override` |
| FR-CONF-002 | Backward compat migration — `stub` sessions auto-migrated | `tests/unit/runtime/test_sessions.py`, `tests/integration/test_golden_scenarios.py` | `test_deprecated_framework_migrated`, `GS-07` |

---

## 6.11 P2/P3 Extensions

| FR ID | Requirement | Test file(s) | Key test(s) |
|-------|-------------|--------------|-------------|
| FR-P2-TOOL-001 | Artifact packaging contract — manifest/summary/bundle generation | `tests/unit/tools/test_p2_tools.py`, `tests/integration/test_p2_capabilities.py` | `test_artifact_pack_creates_manifest_summary_and_zip`, `test_p2_security_and_release_workflow` |
| FR-P2-AGENT-001 | Security scanning agent returns actionable findings | `tests/unit/agents/test_p2_agents.py`, `tests/integration/test_p2_capabilities.py` | `test_security_agent_detects_risky_patterns`, `test_p2_security_and_release_workflow` |
| FR-P2-AGENT-002 | Release readiness agent emits verdict + rollback plan | `tests/unit/agents/test_p2_agents.py`, `tests/integration/test_p2_capabilities.py` | `test_release_agent_generates_handoff_with_artifact_pack`, `test_p2_security_and_release_workflow` |
| FR-P2-POL-001 | Policy templates resolved and applied to tool policies | `tests/unit/runtime/test_policy_templates.py`, `tests/unit/config/test_section10_config.py`, `tests/unit/config/test_loaders.py` | `test_resolve_locked_down_template_enforces_network_and_workspace_bounds`, `test_policy_template_default_dev`, `test_invalid_policy_template_reported` |
| FR-P2-PERF-001 | `repo_map` supports stable cache-hit path | `tests/unit/tools/test_p1_tools.py` | `test_repo_map_uses_cache_on_second_run` |
| FR-P2-PERF-002 | `test_matrix` discovery supports cache-hit path | `tests/unit/tools/test_p1_tools.py` | `test_test_matrix_uses_cache_for_discovery` |
| FR-P2-PERF-003 | `security_agent` supports safe static-scan cache-hit path | `tests/unit/agents/test_p2_agents.py` | `test_security_agent_uses_cache_on_second_static_scan`, `test_security_agent_cache_invalidates_when_target_changes` |
| FR-P3-ONBOARD-001 | Dynamic callable onboarding enforces runtime contract verification | `tests/unit/workspace/test_contract_verifier.py`, `tests/unit/workspace/test_loader.py`, `tests/unit/workspace/test_app_service_register.py` | `test_verify_callable_contract_rejects_missing_schema`, `test_invalid_contract_callable_is_skipped`, `test_invalid_contract_callable_raises` |
| FR-P3-ONBOARD-002 | Workspace overlay onboarding enforces bundle manifest coverage and publisher provenance | `tests/unit/workspace/test_onboarding.py`, `tests/integration/workspace/test_onboarding_gate.py`, `tests/integration/bootstrap/test_bootstrap.py` | `test_enforce_file_coverage_rejects_undeclared_loadable_file`, `test_overlay_rejects_untrusted_publisher`, `test_bootstrap_fails_when_manifest_required_and_missing` |
| FR-P3-ONBOARD-003 | Third-party bundle signatures are verified with fail-closed semantics when required | `tests/unit/workspace/test_onboarding.py`, `tests/integration/workspace/test_onboarding_gate.py` | `test_signature_required_and_valid_passes`, `test_signature_mismatch_is_rejected`, `test_overlay_loads_signed_trusted_bundle` |
| FR-P3-ONBOARD-004 | CI explicitly gates workspace onboarding path | `.github/workflows/ci.yml`, `tests/integration/workspace/test_onboarding_gate.py` | `Workspace onboarding gate` workflow step |
| FR-P3-REMOTE-001 | Orchestrator supports remote worker dispatch model with per-step `execution_target` | `tests/unit/agents/test_orchestrator_agent.py`, `tests/integration/test_orchestrator_golden.py` | `test_orchestrator_remote_step_executes_with_signed_envelope`, `test_golden_multitool_success` |
| FR-P3-REMOTE-002 | Remote dispatch uses signed run envelopes and rejects invalid signature paths | `tests/unit/runtime/test_remote_execution.py`, `tests/unit/agents/test_orchestrator_agent.py`, `tests/unit/config/test_loaders.py` | `test_envelope_sign_and_verify_success`, `test_envelope_signature_mismatch_detected`, `test_orchestrator_remote_step_fails_when_signature_key_missing`, `test_remote_enabled_signed_envelope_requires_key` |
| FR-P3-REMOTE-003 | Remote dispatch supports network transport backend (`worker_mode=http`) with authenticated envelope exchange | `tests/unit/runtime/test_remote_execution.py`, `tests/unit/agents/test_orchestrator_agent.py`, `tests/unit/config/test_loaders.py` | `test_http_remote_worker_pool_invokes_with_network_transport`, `test_orchestrator_remote_step_executes_with_http_worker_mode`, `test_remote_http_mode_with_valid_endpoint_passes` |
| FR-P3-REMOTE-004 | Reference remote worker service enforces explicit callable allowlist and exposes isolation/health metadata | `tests/unit/runtime/test_remote_service.py`, `tests/unit/cli/test_remote_command.py` | `test_remote_worker_service_requires_explicit_allowlist`, `test_remote_worker_service_health_payload_includes_isolation_profile`, `test_remote_serve_prints_bound_endpoint` |
| FR-P3-REMOTE-005 | Remote orchestration path remains stable under sustained retry and timeout/cancel-style failure injection | `tests/integration/runtime/test_remote_soak.py` | `test_remote_http_soak_retries_with_failure_injection`, `test_remote_http_soak_timeout_recovery_after_cancel_style_failure` |
| FR-P3-REMOTE-006 | Remote envelope auth supports keyed rotation with verifier keyrings and key-id-aware health metadata | `packages/runtime/remote/envelopes.py`, `tests/unit/runtime/test_remote_execution.py`, `tests/unit/runtime/test_remote_service.py`, `tests/unit/config/test_loaders.py` | `test_envelope_signer_accepts_rotated_historical_key`, `test_remote_worker_service_accepts_rotated_historical_key`, `test_remote_rotated_key_config_passes` |
| FR-P3-REMOTE-007 | `service_isolation_profile=container` launches a real Docker/Podman worker process with mounted workspace/app-home state | `packages/runtime/remote/container_launcher.py`, `apps/cli/commands/remote.py`, `tests/unit/runtime/test_container_launcher.py`, `tests/unit/cli/test_remote_command.py` | `test_container_launch_builds_mounts_env_and_inner_command`, `test_remote_serve_launches_container_when_container_profile_selected` |
| FR-P3-REMOTE-008 | Remote HTTP workers support HTTPS + optional mTLS with server/client certificate configuration | `packages/runtime/remote/service.py`, `packages/runtime/remote/executor.py`, `tests/unit/runtime/test_remote_service.py`, `tests/unit/config/test_loaders.py` | `test_remote_worker_service_roundtrip_supports_mtls`, `test_remote_worker_service_mtls_rejects_missing_client_certificate`, `test_remote_https_mtls_config_passes` |
| FR-P3-OPS-001 | Operators can bootstrap remote secrets and follow a documented key-rotation playbook | `apps/cli/commands/remote.py`, `packages/runtime/remote/secret_bootstrap.py`, `docs/remote_worker_key_rotation_playbook.md`, `tests/unit/runtime/test_secret_bootstrap.py`, `tests/unit/cli/test_remote_command.py` | `test_build_remote_secret_bundle_includes_publication_key_by_default`, `test_remote_bootstrap_secrets_supports_json_output` |
| FR-EVID-001 | Three mandated horizontal workflows are reproducibly executable | `scripts/run_horizontal_demos.py`, `docs/evidence/horizontal_demos_latest.md` | WF-01/WF-02/WF-03 run report |
| FR-EVID-002 | Independent weighted 9+ scorecard is generated from command-backed checks | `scripts/generate_9plus_scorecard.py`, `docs/evidence/9plus_scorecard_latest.md` | category checks + weighted score output |
| FR-EVID-003 | CI enforces scorecard gate (threshold + all checks pass) and publishes evidence artifacts | `.github/workflows/ci.yml`, `scripts/generate_9plus_scorecard.py`, `scripts/run_horizontal_demos.py` | `scorecard_gate` workflow job |
| FR-EVID-004 | Benchmark matrix evidence generated across OS/Python CI lanes | `.github/workflows/ci.yml`, `scripts/run_benchmark_matrix.py`, `docs/evidence/benchmark_matrix_latest.md` | `benchmark_matrix` workflow job |
| FR-EVID-005 | Benchmark matrix fails on configured per-lane regression thresholds | `scripts/run_benchmark_matrix.py`, `docs/evidence/benchmark_thresholds.json`, `docs/evidence/benchmark_matrix_latest.md` | threshold policy resolution + `threshold_gate_pass` output |
| FR-EVID-006 | Benchmark history is persisted per CI lane and reports deltas against the previous lane run | `.github/workflows/ci.yml`, `scripts/run_benchmark_matrix.py`, `docs/evidence/benchmark_matrix_history.jsonl`, `docs/evidence/benchmark_matrix_latest.md` | history restore/save cache + previous-run delta columns |
| FR-EVID-007 | Benchmark publications are signed, branch-aware, and appended to a publication history for dashboard ingestion | `.github/workflows/ci.yml`, `scripts/run_benchmark_matrix.py`, `docs/evidence/benchmark_publication_latest.json`, `docs/evidence/benchmark_publication_history.jsonl`, `tests/unit/scripts/test_run_benchmark_matrix.py` | `test_build_publication_payload_includes_branch_metadata_and_digests`, `test_wrap_signed_publication_generates_stable_hmac_signature` |

---

## Section 7 Quality Gates

| Gate | Command | Status |
|------|---------|--------|
| All tests pass | `pytest` | 960 passed, 0 failed (2026-04-16) |
| No lint errors (project code) | `ruff check citnega/ apps/ tests/` | 0 errors introduced |
| No type errors | `mypy citnega apps --ignore-missing-imports` | 0 errors |
| Import contracts | `lint-imports` | 5/5 pass |

---

## Nextgen Implementation Coverage (Phases 4–13)

| Phase | Scope | New Tests |
|-------|-------|-----------|
| 4 F5 | CrewAI sync bridge — asyncio.run() | `tests/unit/adapters/test_crewai_runner.py` |
| 4 F6 | Streaming retry — ConnectError/TimeoutException | `tests/unit/model_gateway/test_provider_retry.py` |
| 5 | Private access elimination; stale exception logging | existing tests extended |
| 6 | CapabilityRegistry bootstrap; TaskClassifier; conversation_agent routing | `tests/unit/planning/test_classifier.py` |
| 7 | Parallel context assembly; direct runner parallel tool fanout | `tests/unit/runtime/test_context_parallel.py`, `tests/unit/adapters/test_direct_runner_parallel.py` |
| 8 | Mode registry (7 modes); SkillActivatedEvent; MentalModelCompiledEvent | `tests/unit/runtime/test_mode_registry.py`, `tests/unit/strategy/test_skills.py`, `tests/unit/strategy/test_mental_models.py` |
| 11.1 | import_session() | `tests/unit/runtime/test_session_import_export.py` |
| 11.4 | Circuit breaker — all state transitions | `tests/unit/model_gateway/test_circuit_breaker.py` |
| 11.5 | Symlink escape prevention | `tests/unit/runtime/test_policy.py::TestPathCheck` |
| 11.7 | stream_generate in _RunnerModelGateway | `tests/unit/adapters/test_direct_runner_parallel.py` |
| 12 | TUI: timestamps, keyboard shortcuts, token bar, user_message errors | `tests/unit/tui/test_streaming_block.py`, `test_approval_block.py`, `test_context_bar.py` |
| 13.1 | Bootstrap unit tests | `tests/unit/bootstrap/test_bootstrap_unit.py` |
| 13.4 | ContextTruncatedEvent emission | `tests/unit/runtime/test_context.py::test_token_budget_emits_context_truncated_event` |
