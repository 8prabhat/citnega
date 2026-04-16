# Migration Notes: Deprecated Framework Values and Config Keys

Applies to: Citnega v5 → v6 upgrade.

---

## 1. Deprecated Framework Value: `stub`

### What changed

The `stub` framework adapter was a development placeholder. In v6, `adk` (Google ADK) is the
production default. `stub` remains importable for tests but is removed from the supported
runtime set.

### Automatic migration

Session records that have `framework = "stub"` are **automatically migrated** to the
configured `default_framework` on first access via `get_session()`. No manual action is
required. A deprecation warning is logged:

```
[WARNING] session_framework_migrated session_id=<id> old=stub new=adk
```

### Deprecation flag

`_DEPRECATED_FRAMEWORKS = frozenset({"stub"})` in `citnega/packages/runtime/sessions.py`.
To add future deprecated values, extend this frozenset and the migration test in
`tests/unit/runtime/test_sessions.py`.

### Config file impact

If your `~/.config/citnega/config.toml` (or `settings.toml`) contains:
```toml
[runtime]
framework = "stub"
```

Replace with:
```toml
[runtime]
framework = "adk"
```

`strict_framework_validation = true` will raise `InvalidConfigError` at session creation
if a non-supported framework name is used.

---

## 2. New Required Config Keys (v6)

All new keys have safe defaults and are backward-compatible. Existing installations do not
need to set them explicitly unless they want non-default behavior.

### `[runtime]` section

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `default_framework` | string | `"adk"` | Framework used when none specified per-session |
| `strict_framework_validation` | bool | `false` | Raise `InvalidConfigError` on unknown framework names |

Env var overrides: `CITNEGA_RUNTIME_DEFAULT_FRAMEWORK`, `CITNEGA_RUNTIME_STRICT_FRAMEWORK_VALIDATION`

### `[policy]` section

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `workspace_root` | string | `""` | Absolute path that file tools are restricted to; `""` = no restriction |
| `enforce_network_policy` | bool | `false` | Block outbound network calls from tools when `true` |

Env var overrides: `CITNEGA_POLICY_WORKSPACE_ROOT`, `CITNEGA_POLICY_ENFORCE_NETWORK_POLICY`

### `[context]` section

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `strict_handler_loading` | bool | `false` | Raise `InvalidConfigError` on unknown handler names in `handlers` list |
| `handler_timeout_ms` | int | `0` | Per-handler timeout in milliseconds; `0` = no timeout |

Env var overrides: `CITNEGA_CONTEXT_STRICT_HANDLER_LOADING`, `CITNEGA_CONTEXT_HANDLER_TIMEOUT_MS`

### `[workspace]` section (new in v6)

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `workfolder_path` | string | `""` | Path where `/createtool` etc. write generated files; `""` = CWD |
| `auto_refresh` | bool | `false` | Auto-reload workfolder on startup |

Env var overrides: `CITNEGA_WORKSPACE_WORKFOLDER_PATH`, `CITNEGA_WORKSPACE_AUTO_REFRESH`

---

## 3. Minimal v6 `settings.toml` (with all new keys)

```toml
[runtime]
framework                    = "adk"
default_model_id             = ""
strict_framework_validation  = false

[policy]
workspace_root               = ""
enforce_network_policy       = false
default_policy               = "allow"
require_approval_tools       = []

[context]
handlers                     = ["recent_turns", "session_summary", "kb_retrieval", "runtime_state", "token_budget"]
strict_handler_loading       = false
handler_timeout_ms           = 0

[workspace]
workfolder_path              = ""
auto_refresh                 = false
```

---

## 4. One-time Migration for Existing Installations

If you have persisted sessions with `framework = "stub"`:

1. The migration is automatic on first `get_session()` call — no script needed.
2. To force-migrate all sessions at once:
   ```bash
   citnega sessions list      # triggers migration for each session loaded
   ```
3. To audit: check the structlog output for `session_framework_migrated` entries.

---

## 5. Removal Timeline

- `stub` compatibility code will be **removed after two minor releases** from v6.0.
- The `_DEPRECATED_FRAMEWORKS` frozenset guards the migration code; removal is a
  one-line delete plus cleaning up associated tests.
- Deprecation warnings appear in logs immediately; no user-visible TUI warning is shown
  unless `strict_framework_validation = true`.
