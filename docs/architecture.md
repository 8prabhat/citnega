# Citnega v6 Architecture

Runtime composition and event flow diagrams.

---

## 1. Runtime Composition

```
┌─────────────────────────────────────────────────────────────────────┐
│  Entry points                                                        │
│  ┌──────────────────┐          ┌──────────────────┐                 │
│  │  apps/cli/main   │          │  apps/tui/app     │                 │
│  │  (Typer CLI)     │          │  (Textual TUI)    │                 │
│  └────────┬─────────┘          └────────┬──────────┘                │
└───────────┼─────────────────────────────┼───────────────────────────┘
            │                             │
            ▼                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Bootstrap  (packages/bootstrap/bootstrap.py)                        │
│                                                                      │
│   1. PathResolver          10. PolicyEnforcer                        │
│   2. Settings (TOML+env)   11. ActivityTracer                        │
│   3. Logging (structlog)   12. EventEmitter (JSONL log)              │
│   4. DB (SQLite WAL)       13. ContextHandlers chain                 │
│   5. Migrations (Alembic)  14. ContextAssembler                      │
│   6. ModelGateway          15a. ToolRegistry.build_all()             │
│   7. FrameworkAdapter      15b. AgentRegistry.build_all()            │
│   8. SessionRepo           15c. KnowledgeStore                       │
│   9. RunRepo               16. CoreRuntime                           │
│                            17. ApplicationService                    │
│                            28. StartupDiagnosticsEvent emitted       │
└───────────────────────────────────┬─────────────────────────────────┘
                                    │  IApplicationService
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  ApplicationService  (packages/runtime/app_service.py)               │
│                                                                      │
│  run_turn()  ──►  CoreRuntime.execute_turn()                         │
│  list_tools()      SessionManager.create/get/list()                  │
│  list_agents()     KnowledgeStore.ingest/search/export()             │
│  register_callable()  hot_reload_workfolder()                        │
└───────────────────────────────────┬─────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  CoreRuntime  (packages/runtime/core_runtime.py)                     │
│                                                                      │
│   ContextAssembler ──► [Handler chain]                               │
│     RecentTurnsHandler                                               │
│     SessionSummaryHandler                                            │
│     KBRetrievalHandler                                               │
│     RuntimeStateHandler                                              │
│     TokenBudgetHandler  ◄── enforces max_context_tokens              │
│                                                                      │
│   FrameworkAdapter.run_turn() ──► streaming event loop               │
│     └► PolicyEnforcer.check() per tool call                          │
│     └► ToolCallBlock events emitted per invocation                   │
│     └► ApprovalRequired if policy = "require_approval"               │
│                                                                      │
│   finally:  RunTerminalReasonEvent  ──► RunCompleteEvent             │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Event Flow

```
CoreRuntime.execute_turn()
│
├─ emit RunStateEvent(state="context_assembling")
│
├─ ContextAssembler.assemble()
│   └─ emit ContextTruncatedEvent  (if truncation occurred)
│
├─ emit RunStateEvent(state="executing")
│
├─ FrameworkAdapter.run_turn()  [streaming loop]
│   ├─ emit TokenEvent             (per streaming token)
│   ├─ emit ThinkingEvent          (extended thinking tokens)
│   ├─ emit CallableStartEvent     (tool/agent invocation begins)
│   │   └─ emit RouterDecisionEvent  (if routing agent)
│   └─ emit CallableEndEvent       (tool/agent invocation ends)
│
├─ [on approval required]
│   └─ emit ApprovalRequiredEvent
│       └─ emit ApprovalRespondedEvent  (when user responds)
│
└─ finally  (all paths)
    ├─ emit RunTerminalReasonEvent  (reason: completed|cancelled|failed|depth_limit|timeout|approval_denied)
    └─ emit RunCompleteEvent        (final_state, total_tokens, duration_ms)

Bootstrap path (once at startup):
    └─ emit StartupDiagnosticsEvent  (checks, status, failures)
```

---

## 3. Dependency Layers

```
┌─────────────────────────────────────────────────────┐
│  apps/            Entry points (CLI, TUI)            │
├─────────────────────────────────────────────────────┤
│  packages/bootstrap/   Composition root              │
├─────────────────────────────────────────────────────┤
│  packages/runtime/     CoreRuntime, Sessions,        │
│                        Context, Policy               │
├─────────────────────────────────────────────────────┤
│  packages/agents/      Specialists, ConversationAgent│
│  packages/tools/       10 built-in tools             │
│  packages/kb/          KnowledgeStore (FTS5)         │
│  packages/model_gateway/  Provider routing           │
│  packages/workspace/   Dynamic loader + scaffold     │
├─────────────────────────────────────────────────────┤
│  packages/protocol/    Interfaces + event models     │
│  packages/config/      Settings, TOML loader         │
│  packages/storage/     PathResolver, DB, migrations  │
│  packages/shared/      Errors, registry, types       │
│  packages/observability/  structlog, ActivityTracer  │
│  packages/security/    Scrubber, KeyStore            │
└─────────────────────────────────────────────────────┘
```

---

## 4. Self-Creating Workspace

```
TUI /createtool → WizardState
         │  (collects name, description, parameters)
         ▼
ScaffoldGenerator
  ├─ ModelGateway available? → LLM generates Python module
  └─ No gateway?             → FallbackTemplates.render_tool()
         │
         ▼
CodeValidator.validate()  (ast.parse + class + attr checks)
         │
         ▼
WorkspaceWriter.write_tool()  → <workfolder>/tools/<name>.py
         │
         ▼
Workspace onboarding gate
  ├─ verify .citnega/bundle_manifest.json (optional/required by policy)
  ├─ verify publisher allowlist + file hashes
  └─ verify HMAC signature when enabled
         │
         ▼
DynamicLoader.load_directory()  (importlib, scans BaseCallable subclasses)
         │
         ▼
ApplicationService.register_callable()  → BaseRegistry.register(overwrite=True)
         │
         ▼
Live in runtime — appears in /agent tools immediately
```

---

## 5. Remote Worker Dispatch (P3)

```
OrchestratorAgent step (execution_target="remote")
         │
         ▼
Remote executor backend selected by [remote].worker_mode
  ├─ inprocess
  │   └─ InProcessRemoteWorkerPool
  │       ├─ round-robin worker slots
  │       └─ bounded local concurrency
  │
  └─ http
      └─ HttpRemoteWorkerPool
          ├─ POST signed envelope + payload to remote endpoint
          ├─ optional bearer token auth header
          └─ request timeout + TLS/mTLS verification controls
         │
         ▼
Signed envelope controls (both modes)
  ├─ Build RemoteRunEnvelope (session/run/turn/callable/payload hash)
  ├─ Sign envelope (HMAC SHA-256 + active key id)
  └─ Verify signature against active key + rotated verifier keyring
         │
         ▼
In-process: target.invoke(...) directly
HTTP:
  ├─ RemoteWorkerHTTPService verifies payload hash + signature
  ├─ explicit callable allowlist enforced server-side
  ├─ /health exposes worker id + isolation profile + accepted key ids
  ├─ optional HTTPS with server certificate
  ├─ optional mTLS with client certificate enforcement
  ├─ process profile serves in local process
  ├─ container profile launches the same worker inside Docker/Podman
  └─ remote worker returns InvokeResult payload over network
         │
         ▼
OrchestrationStepResult
  - execution_target=remote
  - worker_id
  - envelope_id
  - envelope_verified
```

---

## 6. Benchmark Publication

```
scripts/run_benchmark_matrix.py
    │
    ├─ run lane benchmark sample
    ├─ apply regression thresholds
    ├─ append benchmark_matrix_history.jsonl
    ├─ compute report + history SHA-256 digests
    ├─ attach branch / CI metadata
    ├─ sign publication payload (HMAC) when configured
    └─ append benchmark_publication_history.jsonl
```
