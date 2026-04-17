# Citnega 9+ Delivery Tracker

Last updated: 2026-04-15
Source of truth: `docs/spec_9plus.md`

## P0 (Release Blockers)
- [x] Single composition path (CLI/TUI delegate to canonical bootstrap)
- [x] Framework correctness (`direct` first-class, session default alignment)
- [x] Context determinism from config handlers + token budget terminal
- [x] Session/model default alignment with active adapter/model
- [x] Shutdown cleanup race protection

## P1
### Tools
- [x] `repo_map`
- [x] `test_matrix`
- [x] `quality_gate`

### Agents
- [x] `qa_agent`
- [x] `orchestrator_agent`

### Validation
- [x] Golden multi-tool orchestration scenarios

## P2
### Tools and Agents
- [x] `artifact_pack`
- [x] `security_agent`
- [x] `release_agent`

### Policy
- [x] Policy templates by environment (`dev`, `team`, `locked_down`)

### Performance
- [x] Caching for `repo_map`
- [x] Caching for `test_matrix` discovery (`execute=false`)
- [x] Caching for other heavy workflows where safe (`quality_gate` intentionally uncached)

## P3
### Remote Execution
- [x] Remote worker/agent execution model
- [x] Signed run envelopes
- [x] Network transport backend (`worker_mode=http`) with auth/timeout/TLS controls
- [x] Reference remote worker service process with explicit allowlist + isolation profile
- [x] Remote orchestration soak coverage (retries + timeout/cancel-style recovery)
- [x] Envelope key rotation support with key IDs + verifier keyring
- [x] Built-in Docker/Podman launcher for `service_isolation_profile=container`
- [x] Optional HTTPS + mTLS support for remote HTTP workers
- [x] Remote secret bootstrap command + operator rotation playbook

### Onboarding and Contracts
- [x] Runtime contract verification for dynamically onboarded callables
- [x] Marketplace-grade plugin/tool onboarding flow end-to-end
- [x] Signature/provenance verification for third-party plugin bundles

## Cross-Cutting Remaining Work
- [x] Full independent scoring pass against 9+ rubric with evidence per category
- [x] Three mandated horizontal workflow demos with reproducible scripts
- [x] Expand release checklist and traceability matrix to include P2/P3 FR IDs
- [x] CI gate to enforce workspace onboarding contract verification path
- [x] CI-required scorecard gate (threshold + all checks pass)
- [x] Benchmark matrix evidence generation across OS/Python CI lanes
- [x] Benchmark threshold policy by lane (regression percentage gate)
- [x] Benchmark history persistence with per-lane trend/regression deltas across CI runs
- [x] Signed benchmark publication manifests and branch-aware publication history

## Current Ratings Trajectory (Internal)
- Reliability and correctness: 9.8
- Architecture coherence: 9.8
- Capability breadth: 9.8
- Safety/governance/auditability: 9.8
- UX/operator ergonomics: 9.8
- Performance/latency: 9.8
- Independent weighted score (2026-04-15 UTC / 2026-04-15 IST): 9.8/10 (`docs/evidence/9plus_scorecard_latest.md`)

## Execution Order Completion (2026-04-15)
- [x] Harden remote backend beyond in-process workers (network transport backend via `worker_mode=http`)
- [x] Turn scorecard checks into CI required gates
- [x] Expand benchmark matrix across OS/Python combinations
- [x] Add a reference remote worker service process (explicit callable allowlist + process/container isolation profile)
- [x] Add benchmark threshold policy by lane (fail when latency regression exceeds configured percentage)
- [x] Add long-run soak tests for remote orchestrations (retry/cancel/failure injection over sustained runs)
- [x] Add envelope key rotation support for remote worker authentication
- [x] Add true containerized worker launcher for the `container` isolation profile
- [x] Persist benchmark history and render trend/regression deltas across CI runs
- [x] Add optional mTLS for remote HTTP workers where PKI is available
- [x] Add signed benchmark/history publication across CI branches for longitudinal dashboards
- [x] Add remote worker secret bootstrap and key-rotation operational playbook

## Next Recommended Execution Order
1. Add KMS or secret-manager-backed remote credential loading so shared secrets do not rely on env distribution alone
2. Add certificate expiry diagnostics and proactive mTLS renewal warnings in `citnega doctor`
3. Add a dashboard consumer that validates benchmark publication signatures before ingest
