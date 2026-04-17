# Benchmark Matrix Evidence

Generated at: 2026-04-14T16:53:19.718610+00:00
Benchmark label: darwin-py3.13.5
Platform: macOS-26.4-arm64-arm-64bit-Mach-O
Python: 3.13.5
Overall pass: yes

| ID | Description | Passed | Duration (ms) |
|---|---|---|---:|
| BM-01 | repo_map cache-hit path | yes | 575 |
| BM-02 | test_matrix cache-hit discovery path | yes | 556 |
| BM-03 | security_agent static-scan cache-hit path | yes | 591 |
| BM-04 | remote execution envelope dispatch path | yes | 11182 |

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

### BM-04 — remote execution envelope dispatch path

`/Users/prabhat/Library/CloudStorage/GoogleDrive-888prabhat@gmail.com/My Drive/Work/citnega/.venv/bin/python -m pytest tests/unit/runtime/test_remote_execution.py::test_http_remote_worker_pool_invokes_with_network_transport -q`

```text
.                                                                        [100%]
```
