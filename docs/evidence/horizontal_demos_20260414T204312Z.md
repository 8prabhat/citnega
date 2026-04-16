# Horizontal Workflow Demo Evidence

Generated at: 2026-04-14T20:43:14.589431+00:00
Overall pass: yes

| ID | Scenario | Requirement | Passed | Duration (ms) |
|---|---|---|---|---:|
| WF-01 | Code Refactor + Tests + Release Readiness | Code workflow with orchestration and release safety checks | yes | 634 |
| WF-02 | Research/KB Synthesis and Retrieval | Research-style ingestion and retrieval persisted through KB | yes | 781 |
| WF-03 | Ops Diagnosis + Remediation + Verification | Security and release ops workflow with remediation guidance | yes | 646 |

## Command Output Tails

### WF-01 — Code Refactor + Tests + Release Readiness

`/Users/prabhat/Library/CloudStorage/GoogleDrive-888prabhat@gmail.com/My Drive/Work/citnega/.venv/bin/python -m pytest tests/integration/test_orchestrator_golden.py::test_golden_multitool_success -q`

```text
.                                                                        [100%]
```

### WF-02 — Research/KB Synthesis and Retrieval

`/Users/prabhat/Library/CloudStorage/GoogleDrive-888prabhat@gmail.com/My Drive/Work/citnega/.venv/bin/python -m pytest tests/integration/test_golden_scenarios.py::TestGS06KBIngestionAndRetrieval::test_add_kb_item_and_retrieve -q`

```text
.                                                                        [100%]
```

### WF-03 — Ops Diagnosis + Remediation + Verification

`/Users/prabhat/Library/CloudStorage/GoogleDrive-888prabhat@gmail.com/My Drive/Work/citnega/.venv/bin/python -m pytest tests/integration/test_p2_capabilities.py::test_p2_security_and_release_workflow -q`

```text
.                                                                        [100%]
```
