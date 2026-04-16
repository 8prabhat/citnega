# Benchmark Matrix Evidence

Generated at: 2026-04-15T02:34:43.083809+00:00
Benchmark label: darwin-py3.13.5
Platform: macOS-26.4-arm64-arm-64bit-Mach-O
Python: 3.13.5
Overall pass: yes
Threshold gate pass: yes
Threshold policy: /Users/prabhat/Library/CloudStorage/GoogleDrive-888prabhat@gmail.com/My Drive/Work/citnega/docs/evidence/benchmark_thresholds.json
History file: /Users/prabhat/Library/CloudStorage/GoogleDrive-888prabhat@gmail.com/My Drive/Work/citnega/docs/evidence/benchmark_matrix_history.jsonl
Previous lane run: 2026-04-15T02:19:16.707685+00:00

| ID | Description | Passed | Threshold Gate | Duration (ms) | Previous | Delta vs Prev | Trend | Baseline | Threshold | Max Regression |
|---|---|---|---|---:|---:|---:|---|---:|---:|---:|
| BM-01 | repo_map cache-hit path | yes | yes | 563 | 565 | -2 (-0.35%) | improved | 650 | 1950 | 200% |
| BM-02 | test_matrix cache-hit discovery path | yes | yes | 585 | 571 | 14 (2.45%) | regressed | 650 | 1950 | 200% |
| BM-03 | security_agent static-scan cache-hit path | yes | yes | 739 | 743 | -4 (-0.54%) | improved | 800 | 2400 | 200% |
| BM-04 | reference remote worker service dispatch path | yes | yes | 1077 | 1052 | 25 (2.38%) | regressed | 12000 | 24000 | 100% |

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
