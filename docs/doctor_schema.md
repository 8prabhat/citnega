# CLI Doctor: Output Schema and Sample Outputs

`citnega-cli doctor check` runs 10 self-checks and reports pass/fail so operators can quickly
diagnose misconfiguration or missing dependencies.

---

## Invocation

```bash
citnega-cli doctor check --human  # human-readable
citnega-cli doctor check --json   # one JSON object per line (JSONL)
```

Exit code is `0` if all checks pass, `1` if any check fails.

---

## Checks

| Check name | What it verifies |
|------------|-----------------|
| `config` | `settings.toml` + env vars load without errors |
| `framework_adapter` | Configured framework is a known, importable adapter |
| `models_yaml` | `models.yaml` exists and has at least one model entry |
| `database_path` | DB path parent directory is writable |
| `kb_store` | `KnowledgeStore` module imports without error |
| `tool_registry` | All built-in tools build without error |
| `agent_registry` | All built-in agents build without error |
| `context_handlers` | All 5 context handler classes import cleanly |
| `policy_enforcer` | `PolicyEnforcer` instantiates without error |
| `tui_app` | `citnega.apps.tui.app` imports without error |

---

## Human-readable output schema

```
  [STATUS] <check_name padded to 25 chars>  <detail>
  ...

Results: N/10 checks passed
```

`STATUS` is `PASS` or `FAIL`.

### Sample — all passing

```
  [PASS] config                    framework=adk, model=gemma4-26b-local
  [PASS] framework_adapter         adapter=ADKFrameworkAdapter
  [PASS] models_yaml               14 model(s) defined, default=gemma4-26b-local
  [PASS] database_path             db_path=/Users/alice/Library/Application Support/citnega/db/citnega.db
  [PASS] kb_store                  importable
  [PASS] tool_registry             13 tool(s) registered
  [PASS] agent_registry            23 agent(s) registered
  [PASS] context_handlers          all 5 handlers importable
  [PASS] policy_enforcer           instantiated
  [PASS] tui_app                   importable

Results: 10/10 checks passed
```

### Sample — partial failure

```
  [PASS] config                    framework=adk, model=gemma4-26b-local
  [FAIL] framework_adapter         No module named 'google.adk'
  [PASS] models_yaml               14 model(s) defined, default=gemma4-26b-local
  [PASS] database_path             db_path=/Users/alice/Library/Application Support/citnega/db/citnega.db
  [PASS] kb_store                  importable
  [FAIL] tool_registry             Cannot import web_fetch: missing aiohttp
  [PASS] agent_registry            23 agent(s) registered
  [PASS] context_handlers          all 5 handlers importable
  [PASS] policy_enforcer           instantiated
  [PASS] tui_app                   importable

Results: 8/10 checks passed
```

---

## JSON output schema

Each check emits one JSON object. A final `summary` object follows.

### Per-check object

```json
{
  "ok":     true | false,
  "check":  "<check_name>",
  "detail": "<human-readable detail or error message>"
}
```

### Summary object

```json
{
  "summary": {
    "passed": <int>,
    "failed": <int>
  }
}
```

### Sample — all passing (JSONL)

```jsonl
{"ok": true, "check": "config", "detail": "framework=adk, model=gemma4-26b-local"}
{"ok": true, "check": "framework_adapter", "detail": "adapter=ADKFrameworkAdapter"}
{"ok": true, "check": "models_yaml", "detail": "14 model(s) defined, default=gemma4-26b-local"}
{"ok": true, "check": "database_path", "detail": "db_path=/Users/alice/Library/Application Support/citnega/db/citnega.db"}
{"ok": true, "check": "kb_store", "detail": "importable"}
{"ok": true, "check": "tool_registry", "detail": "13 tool(s) registered"}
{"ok": true, "check": "agent_registry", "detail": "23 agent(s) registered"}
{"ok": true, "check": "context_handlers", "detail": "all 5 handlers importable"}
{"ok": true, "check": "policy_enforcer", "detail": "instantiated"}
{"ok": true, "check": "tui_app", "detail": "importable"}
{"summary": {"passed": 10, "failed": 0}}
```

---

## Integration notes

- The JSON output is designed for piping to `jq` or CI tooling:
  ```bash
  citnega-cli doctor check --json | jq 'select(.ok == false)'
  ```
- A non-zero exit code can be used as a pre-flight gate in deployment scripts.
- The `StartupDiagnosticsEvent` emitted at bootstrap mirrors these checks in the
  event log (`<app_home>/logs/events/*.jsonl`) so failures are observable after the fact.
