# Benchmark Matrix Evidence

Generated at: 2026-04-14T20:43:09.848695+00:00
Benchmark label: darwin-py3.13.5
Platform: macOS-26.4-arm64-arm-64bit-Mach-O
Python: 3.13.5
Overall pass: yes
Threshold gate pass: yes
Threshold policy: /Users/prabhat/Library/CloudStorage/GoogleDrive-888prabhat@gmail.com/My Drive/Work/citnega/docs/evidence/benchmark_thresholds.json

| ID | Description | Passed | Threshold | Duration (ms) | Baseline | Max Regression |
|---|---|---|---|---:|---:|---:|
| BM-01 | repo_map cache-hit path | yes / yes | 560 | 650 | 200% |
| BM-02 | test_matrix cache-hit discovery path | yes / yes | 566 | 650 | 200% |
| BM-03 | security_agent static-scan cache-hit path | yes / yes | 614 | 800 | 200% |
| BM-04 | reference remote worker service dispatch path | yes / yes | 1039 | 12000 | 100% |

## Command Output Tails

### BM-01 — repo_map cache-hit path

`/Users/prabhat/Library/CloudStorage/GoogleDrive-888prabhat@gmail.com/My Drive/Work/citnega/.venv/bin/python -m pytest tests/unit/tools/test_p1_tools.py::test_repo_map_uses_cache_on_second_run -q`

```text
.                                                                        [100%]
```

### BM-02 — test_matrix cache-hit discovery path

`/Users/prabhat/Library/CloudStorage/GoogleDrive-888prabhat@gmail.com/My Drive/Work/citnega/.venv/bin/python -m pytest tests/unit/tools/test_p1_tools.py::test_test_matrix_uses_cache_for_discovery -q`

```text
.                                                                        [100%]
```

### BM-03 — security_agent static-scan cache-hit path

`/Users/prabhat/Library/CloudStorage/GoogleDrive-888prabhat@gmail.com/My Drive/Work/citnega/.venv/bin/python -m pytest tests/unit/agents/test_p2_agents.py::test_security_agent_uses_cache_on_second_static_scan -q`

```text
.                                                                        [100%]
```

### BM-04 — reference remote worker service dispatch path

`/Users/prabhat/Library/CloudStorage/GoogleDrive-888prabhat@gmail.com/My Drive/Work/citnega/.venv/bin/python -m pytest tests/unit/runtime/test_remote_service.py::test_remote_worker_service_roundtrip_invokes_callable -q`

```text
.                                                                        [100%]
```
