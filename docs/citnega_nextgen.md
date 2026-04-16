# Citnega Nextgen Technical Specification

## Status
Draft v1

## Date
2026-04-16

## Scope
This specification defines the next-generation architecture and implementation plan for Citnega.

Included:
- runtime architecture
- orchestration model
- planning and routing
- tools, agents, workflows, and skills
- parallel execution
- workspace extensibility
- code organization
- test organization
- diagnostics and observability
- performance and feature completeness

Explicitly excluded from this spec:
- multimodal support
- authentication and identity strategy

## 1. Executive Summary
Citnega already has a stronger architectural substrate than many terminal agents: adapter isolation, local-first runtime, event replay, policy enforcement, workspace extensibility, and a deterministic orchestrator. The main blockers to a true 9+/10 system are not missing primitives. They are fragmentation, inconsistency, and incomplete productization.

The current system has three overlapping orchestration paths (`conversation_agent`, `planner_agent`, `orchestrator_agent`), static built-in registries, permissive silent-failure behavior in core loading, stale UX exposure, and limited parallelism. Several built-in capabilities are still Python-repo specific, which conflicts with Citnega's stated goal as a horizontal tool.

The next-generation design shall converge on one execution engine, one canonical capability registry, one compiled plan intermediate representation, and one policy/event path. Modes, skills, workflows, and mental models must influence planning, not bypass execution semantics.

## 2. Current-State Review

### 2.1 Confirmed Strengths
1. Adapter boundary discipline is real.
   - `packages/protocol/interfaces/adapter.py`
   - Framework-specific logic remains inside adapter packages.
2. The runtime has a real event model and replayability.
   - `packages/runtime/core_runtime.py`
   - `packages/runtime/events/emitter.py`
   - `packages/runtime/events/tracer.py`
3. Policy enforcement is first-class.
   - `packages/runtime/policy/enforcer.py`
   - `packages/runtime/policy/checks.py`
4. Workspace extensibility is already viable.
   - `packages/workspace/loader.py`
   - `packages/workspace/onboarding.py`
   - `packages/workspace/contract_verifier.py`
5. Orchestrator failure handling is materially stronger than earlier iterations.
   - `packages/agents/core/orchestrator_agent.py`
   - retries, dependency blocking, rollback, remote execution, and failure mapping already exist.

### 2.2 Confirmed Architectural Flaws

#### Critical
1. Multiple overlapping supervisors and planners create duplicate orchestration semantics.
   - `packages/agents/core/conversation_agent.py`
   - `packages/agents/core/planner_agent.py`
   - `packages/agents/core/orchestrator_agent.py`
   - Impact: routing, planning, and execution logic are split across three agents with different contracts and error behavior.

2. Built-in registries are still static factories with silent failure.
   - `packages/agents/registry.py:86-134`
   - `packages/tools/registry.py:65-118`
   - Impact: built-in capability discovery is closed for extension, while failed agent construction can disappear silently.

3. Workspace loading still treats failure as best-effort even when the runtime may depend on the artifact.
   - `packages/workspace/loader.py:85-105`
   - `packages/workspace/loader.py:159-180`
   - Impact: a broken custom artifact is easy to miss and diagnostics are weak.

4. Parallel execution is not a first-class runtime feature.
   - `packages/agents/core/orchestrator_agent.py:211-252`
   - `packages/adapters/direct/runner.py:370-392`
   - Impact: ready DAG steps and batched tool calls execute serially, which leaves performance on the table and prevents a direct answer to competitor subagent/parallel flows.

#### High
5. The service facade still leaks private-ish adapter details and its docstring overstates encapsulation.
   - `packages/runtime/app_service.py:46-52`
   - `packages/runtime/app_service.py:390-397`
   - `packages/runtime/app_service.py:484-494`
   - `packages/runtime/app_service.py:602-621`

6. Feature exposure is stale relative to the runtime.
   - `packages/protocol/modes.py:215-217`
   - `apps/tui/slash_commands/builtin.py:126-128`
   - Impact: `research` and `code` modes exist but are not reflected in `/mode` help text.

7. The workflow concept is not a real first-class abstraction.
   - `packages/workspace/loader.py:107-137`
   - `packages/workspace/templates.py:169-201`
   - `packages/workspace/scaffold.py:370-401`
   - Impact: workflows are loaded and generated as specialist-like callables, not as plan templates or compiled orchestration assets.

8. Horizontal positioning is undermined by Python-centric built-ins.
   - `packages/tools/builtin/quality_gate.py:139-172`
   - `packages/tools/builtin/test_matrix.py:111-163`
   - `packages/tools/builtin/repo_map.py:141-188`
   - Impact: built-in QA and repo-analysis assume Python layout, `pytest`, `ruff`, `mypy`, `apps/packages/tests`, and `test_*.py` conventions.

9. Session planning state is still partially in-memory.
   - `packages/runtime/context/conversation_store.py:300-313`
   - Impact: plan phase resets on restart and breaks continuity for plan-mode workflows.

10. Context assembly is sequential even when handlers are independent.
   - `packages/runtime/context/assembler.py:87-115`
   - Impact: unnecessary latency for read-only context handlers.

#### Medium
11. Tool and specialist invocation still rely on heuristic input-field probing.
   - `packages/agents/core/conversation_agent.py:41-72`
   - `packages/agents/core/planner_agent.py:159-163`
   - Impact: brittle contracts and poor extensibility.

12. Hardcoded defaults are still spread across agents, tools, and runners.
   - `packages/agents/core/conversation_agent.py:25-34`
   - `packages/agents/core/orchestrator_agent.py:58-64`
   - `packages/adapters/direct/runner.py:265-320`
   - `packages/runtime/app_service.py:182-193`
   - Impact: policy and product behavior drift from configuration over time.

13. Knowledge-base tag filtering is still post-query and O(n) over candidate rows.
   - `packages/kb/retrieval.py:97-113`
   - `packages/kb/store.py:105-108`

14. There are stale or low-value organizational artifacts.
   - empty prompts folder: `packages/agents/core/prompts`
   - compatibility shim: `packages/runtime/session_modes.py`
   - stray unrelated script: `python/generate_travel_guide.py`

15. The TUI and controller layer still swallows too many exceptions.
   - examples: `apps/tui/app.py`, `apps/tui/controllers/chat_controller.py`, `apps/tui/slash_commands/builtin.py`
   - Impact: product polish and diagnosability lag behind architecture quality.

### 2.3 Incomplete Features
1. No canonical compiled-plan intermediate representation shared across routing, planning, and execution.
2. No first-class skills system.
3. No first-class mental-model compiler.
4. No parallel scheduler for tools and agents.
5. No plan template/workflow registry distinct from executable callables.
6. No required-vs-optional artifact loading policy.
7. No generic language-agnostic project quality model.
8. No capability provenance and trust ranking across built-in and workspace artifacts.
9. No explicit activation events for planning influences such as skills, workflows, or mental models.
10. No unified execution transcript that maps intent -> plan -> step -> artifact -> output.

## 3. Competitive Positioning (Excluding Multimodal and Auth)

### 3.1 Claude Code
Relevant official capabilities documented by Anthropic:
- memory via `CLAUDE.md` plus auto memory
- skills and MCP prompts
- routines and scheduling
- sandboxing
- hooks, including agent hooks
- command-driven parallel review flows such as `/simplify`, which spawns three review agents in parallel

References:
- https://code.claude.com/docs/en/memory
- https://code.claude.com/docs/en/commands
- https://code.claude.com/docs/en/hooks

### 3.2 Gemini CLI
Relevant official capabilities documented by Google:
- GEMINI.md context files and memory
- plan mode and todos
- agent skills
- checkpointing / rewind / resume
- subagents and remote subagents
- MCP servers
- hooks
- git worktrees and IDE integration

References:
- https://geminicli.com/docs/reference/commands/
- https://geminicli.com/docs/cli/gemini-md/
- https://geminicli.com/docs/tools/memory/
- https://geminicli.com/docs/cli/git-worktrees/

### 3.3 Where Citnega Wins Today
1. Adapter and provider freedom.
2. Local-first architecture and storage ownership.
3. Fine-grained policy enforcement on callables.
4. Replayable runtime events.
5. Workfolder-based extensibility for custom tools, agents, and workflows.

### 3.4 Where Citnega Still Trails
1. Parallel operator ergonomics.
2. Product polish and error UX.
3. Unified skill/memory/workflow model.
4. Consistency between runtime capability and surface UX.
5. Horizontal built-ins that work equally well across Python, JS/TS, Go, Rust, Java, mixed monorepos, and docs-heavy repositories.

### 3.5 Current External Rating
With multimodal and auth excluded, the current repo is approximately:
- architecture: 8.6/10
- runtime robustness: 8.1/10
- product completeness: 7.8/10
- overall: 8.2/10

Target for this spec:
- architecture: >= 9.5/10
- overall external rating: >= 9.1/10
- better than Gemini CLI and Claude Code on extensibility, governance, and horizontal runtime design

## 4. Nextgen Design Principles
1. Single responsibility per runtime component.
2. Open for extension, closed for modification.
3. Explicit contracts over heuristics.
4. One canonical execution path.
5. One canonical capability registry.
6. Deterministic and replayable behavior by default.
7. Strict diagnostics for core runtime assets; configurable tolerance only for optional workspace assets.
8. Horizontal-first tooling; language-specific logic must live behind detectors or profiles.
9. No random folders, no orphan scripts, no compatibility layers without a removal milestone.
10. Test structure must mirror code structure.

## 5. Target Runtime Architecture

### 5.1 Core Rule
One executor, many compilers.

Only one component executes plans:
- `ExecutionEngine`

All other components compile or influence execution:
- mode strategy
- skills
- mental model
- workflow templates
- task classifier
- plan compiler

### 5.2 Logical Pipeline
1. `SessionStateLoader`
   - loads session, mode, memory, active skills, active mental model, workspace overlays
2. `CapabilityRegistry`
   - returns normalized built-in and custom tools, agents, workflows, and skills
3. `StrategyAssembler`
   - combines mode, user intent, skills, mental model, repo signals, and policy constraints
4. `TaskClassifier`
   - chooses direct answer, specialist answer, or compiled execution plan
5. `PlanCompiler`
   - produces a typed `CompiledPlan`
6. `PlanValidator`
   - validates schema, dependencies, approvals, policy, capability availability, and execution targets
7. `ExecutionEngine`
   - executes the plan locally or remotely with concurrency controls
8. `ResultSynthesizer`
   - generates the final answer and summary artifacts
9. `TraceRecorder`
   - persists a full intent -> plan -> execution trace

### 5.3 Canonical Runtime Types

#### `CapabilityDescriptor`
Fields:
- `capability_id`
- `kind` (`tool`, `agent`, `workflow_template`, `skill`)
- `source` (`builtin`, `workspace`, `plugin`, `remote_catalog`)
- `display_name`
- `description`
- `input_schema`
- `output_schema`
- `policy`
- `execution_traits`
- `supported_modes`
- `tags`
- `language_profiles`
- `provenance`
- `stability_level`

#### `StrategySpec`
Fields:
- `mode`
- `objective`
- `success_criteria`
- `risk_posture`
- `planning_depth`
- `parallelism_budget`
- `preferred_capabilities`
- `forbidden_capabilities`
- `approval_policy`
- `evidence_requirements`
- `user_style_constraints`
- `active_skills`
- `mental_model_clauses`

#### `CompiledPlan`
Fields:
- `plan_id`
- `objective`
- `steps`
- `artifacts`
- `generated_from`
- `requires_approval`
- `max_parallelism`
- `execution_policy`
- `rollback_policy`
- `stop_conditions`
- `synthesis_requirements`

#### `PlanStep`
Fields:
- `step_id`
- `type` (`tool`, `agent`, `workflow_template_ref`, `synthesis`, `approval_gate`)
- `capability_id`
- `args`
- `depends_on`
- `can_run_in_parallel`
- `retry_policy`
- `timeout_policy`
- `rollback_step_id`
- `expected_outputs`
- `execution_target`

## 6. Modes, Skills, Workflows, and Mental Models

### 6.1 Modes
Modes are planning profiles, not execution engines.

Required built-in modes:
- `chat`
- `plan`
- `explore`
- `research`
- `code`
- `review`
- `operate`

Rules:
- all modes must be discoverable from one registry
- all surfaces must render the same mode list
- mode help, picker labels, and runtime behavior must come from shared metadata

### 6.2 Skills
Skills are reusable, non-executable instruction packs.

Storage:
- `workfolder/skills/<skill_name>/SKILL.md`
- optional front matter schema

Skills may influence:
- planning bias
- preferred tools/agents
- checklists
- evidence requirements
- style rules

Skills may not:
- grant permissions
- bypass policy
- execute code directly

Required events:
- `SkillActivatedEvent`
- `SkillRejectedEvent`

### 6.3 Mental Models
Mental models are user- or task-specific execution preferences.

Mental models must compile into structured strategy clauses before planning.
They must never remain a hidden prompt blob during execution.

Required component:
- `MentalModelCompiler`

Required output:
- normalized clauses such as ordering preference, risk tolerance, validation posture, interruption rules, and stop conditions.

Required event:
- `MentalModelCompiledEvent`

### 6.4 Workflows
Workflows must become plan templates, not specialist-like prompt wrappers.

Current anti-pattern:
- workflow generation produces a `SpecialistBase` subclass.

Required nextgen model:
- workflow files compile into `CompiledPlanTemplate`
- execution goes through the common `ExecutionEngine`
- workflows may contain placeholders, branching rules, and approval checkpoints

Storage:
- `workfolder/workflows/<workflow_name>.yaml`
- optional `workfolder/workflows/<workflow_name>.md` documentation companion

## 7. Parallel Execution Model

### 7.1 Requirements
Citnega Nextgen shall support parallel tools and agents as a native feature.

Required capabilities:
1. DAG-level parallel step scheduling.
2. Parallel tool-call fanout within one execution stage.
3. Concurrency budgets by mode and by execution target.
4. Per-capability concurrency safety metadata.
5. Deterministic result collation order.
6. Partial-failure semantics with retry, continue, or fail-fast policies.

### 7.2 Scheduler
Introduce `PlanScheduler` between validated plan and execution.

Responsibilities:
- topological ordering
- stage formation
- parallel eligibility checks
- concurrency limiting
- target-aware batching
- rollback dependency ordering

Scheduler output:
- `ExecutionBatch[]`

Each batch contains steps that can execute in parallel without violating dependencies or safety constraints.

### 7.3 Execution Safety Metadata
Every capability descriptor must declare:
- `side_effect_level`
- `parallel_safe`
- `resource_scope`
- `requires_exclusive_workspace`
- `supports_remote_execution`

Examples:
- `read_file`: parallel safe
- `search_files`: parallel safe
- `repo_map`: parallel safe with cache lock
- `write_file`: not parallel safe on overlapping paths
- `run_shell`: exclusive unless explicitly marked safe

### 7.4 Direct Runner Improvements
The direct runner shall be able to execute independent tool calls concurrently when the model emits multiple tool invocations that are declared parallel-safe.

Current limitation:
- `packages/adapters/direct/runner.py:370-392`

Nextgen behavior:
- parse the set of pending tool calls
- partition by parallel-safety and resource overlap
- execute safe groups via `asyncio.TaskGroup`
- collate results in original tool-call order

## 8. Capability Registry

### 8.1 Goals
Replace fragmented static registries with a canonical capability catalog.

The catalog must unify:
- built-in tools
- built-in agents
- workflow templates
- skills
- workspace callables
- future plugin-provided capabilities

### 8.2 Required Components
1. `BuiltinCapabilityProvider`
2. `WorkspaceCapabilityProvider`
3. `CapabilityRegistry`
4. `CapabilityResolver`
5. `CapabilityDiagnostics`

### 8.3 Failure Policy
Core runtime assets:
- fail closed
- startup error if required built-ins cannot load

Optional workspace assets:
- configurable
- `strict_workspace_loading = true|false`
- diagnostics must always record exact import/validation/instantiation failure

Remove silent skip patterns from:
- `packages/agents/registry.py`
- `packages/workspace/loader.py`

### 8.4 Discovery
Built-ins should be declared in manifest form, not hardcoded imports inside registry methods.

Preferred patterns:
- module manifests
- package-level registration decorators
- static typed manifests loaded by provider classes

## 9. Built-in Capability Enhancements

### 9.1 Tools
#### `repo_map`
Current issue:
- Python-focused architecture mapping.

Nextgen requirement:
- generic repository graph with language detectors
- support Python, JS/TS, Go, Rust, Java, mixed repos, docs-only repos
- separate scanners per language profile
- configurable summarization and graph extraction

#### `quality_gate`
Current issue:
- hardcoded Python commands and repository layout assumptions.

Nextgen requirement:
- profile engine by detected stack
- built-in profiles: `python`, `node`, `go`, `rust`, `java`, `mixed`, `docs`
- repo-local override file for commands
- dry-run explain mode
- parallel execution of independent checks

#### `test_matrix`
Current issue:
- `pytest` and `tests/test_*.py` assumptions.

Nextgen requirement:
- generic test discovery adapters
- language-aware suite bucketing
- reusable command templates
- parallel bucket execution
- flaky-test and changed-files subsets

#### `search_files`
Current issue:
- pure Python implementation, no ripgrep acceleration, no binary filtering policy, no structured result model.

Nextgen requirement:
- prefer `rg` where available
- structured matches with path, line, preview
- ignore rules and binary-file handling
- stable sorting and paging

#### `run_shell`
Nextgen requirement:
- better execution envelopes
- structured environment controls
- richer cancellation diagnostics
- optional background execution handle for long-running safe commands

### 9.2 Agents
#### `conversation_agent`
Current issue:
- heuristic supervisor loop.

Nextgen requirement:
- demote to front-door conversational coordinator
- no bespoke specialist supervision logic
- hand complex work to `PlanCompiler`

#### `planner_agent`
Current issue:
- duplicates orchestration with regex mini-DSL.

Nextgen requirement:
- remove as standalone executor
- replace with compiler service producing `CompiledPlan`

#### `router_agent`
Current issue:
- purely LLM-routed and loosely validated.

Nextgen requirement:
- hybrid routing: rules + capability metadata + model arbitration
- confidence thresholds
- deterministic fast path for obvious requests

#### `tool_executor_agent`
Current issue:
- low-value wrapper over tools.

Nextgen requirement:
- either delete it or replace with a true `CapabilitySelectionAgent` used only by the compiler layer

## 10. Code Organization Requirements

### 10.1 Package Layout
The nextgen codebase shall use explicit bounded contexts.

Required top-level source layout:
- `apps/`
- `packages/bootstrap/`
- `packages/capabilities/`
- `packages/execution/`
- `packages/planning/`
- `packages/strategy/`
- `packages/runtime/`
- `packages/workspace/`
- `packages/protocol/`
- `packages/storage/`
- `packages/observability/`
- `packages/config/`

Move or consolidate:
- registry logic into `packages/capabilities/`
- plan compiler and task classifier into `packages/planning/`
- mode, skill, and mental-model strategy logic into `packages/strategy/`
- execution scheduler and worker pools into `packages/execution/`

### 10.2 Naming Rules
1. No vague folders such as `python/`.
2. No stale shims without removal ADR and milestone.
3. No compatibility files with no users.
4. Class and module names must reflect domain responsibility.
5. Avoid legacy dual concepts such as `workflow` implemented as `SpecialistBase`.

### 10.3 Dead and Stale Artifact Policy
Candidates to remove or rationalize:
- `python/generate_travel_guide.py`
- empty `packages/agents/core/prompts/`
- `packages/runtime/session_modes.py` after migration is complete

## 11. Test Architecture

### 11.1 Principles
1. Tests must mirror runtime structure.
2. Every public runtime type needs contract tests.
3. Every planner and scheduler rule needs deterministic golden tests.
4. Every failure policy needs explicit tests.
5. Parallel execution needs race, cancellation, and determinism tests.

### 11.2 Required Suites
1. `tests/unit/planning/`
   - compiler
   - validator
   - classifier
   - workflow template expansion
   - skill selection
   - mental-model compilation
2. `tests/unit/execution/`
   - scheduler
   - batching
   - rollback ordering
   - concurrency limits
   - resource locking
3. `tests/unit/capabilities/`
   - registry
   - discovery
   - provenance
   - diagnostics
4. `tests/integration/runtime/`
   - end-to-end plan compilation and execution
   - parallel step execution
   - mixed local and remote batches
5. `tests/golden/`
   - planner and synthesis traces
6. `tests/performance/`
   - scheduler overhead
   - repo_map latency
   - search_files latency
   - quality_gate throughput

### 11.3 Tooling Gates
CI must block on:
- `ruff`
- `mypy`
- `import-linter`
- unit tests
- integration tests
- performance regression checks
- deterministic golden-plan checks

## 12. Observability and Diagnostics

### 12.1 Required New Events
- `PlanCompiledEvent`
- `PlanValidatedEvent`
- `ExecutionBatchStartedEvent`
- `ExecutionBatchCompletedEvent`
- `SkillActivatedEvent`
- `MentalModelCompiledEvent`
- `WorkflowTemplateExpandedEvent`
- `CapabilityLoadFailedEvent`
- `ParallelExecutionConflictEvent`

### 12.2 Runtime Diagnostics
Citnega Nextgen must provide:
1. why a route was chosen
2. why a skill was activated
3. why a mental-model clause affected planning
4. why a plan step was parallelized or serialized
5. why a capability failed to load
6. why a step was blocked, skipped, retried, or rolled back

## 13. Migration Plan

### Phase 1: Runtime Convergence
1. Introduce `CapabilityRegistry`.
2. Introduce `CompiledPlan` types.
3. Replace `planner_agent` execution with compiler service.
4. Demote `conversation_agent` to front-door coordinator.
5. Keep `orchestrator_agent` as transitional executor behind the new engine.

### Phase 2: Parallel Scheduler
1. Add `PlanScheduler` and `ExecutionBatch`.
2. Add capability safety metadata.
3. Add `asyncio.TaskGroup`-based parallel step execution.
4. Add direct-runner parallel tool fanout.

### Phase 3: Strategy Layer
1. Add `SkillRegistry`.
2. Add `MentalModelCompiler`.
3. Extend modes with `review` and `operate`.
4. Introduce strategy tracing events.

### Phase 4: Workflow Rework
1. Replace workflow-as-specialist scaffolds with workflow templates.
2. Add YAML workflow templates and validators.
3. Add migration for existing custom workflow Python files.

### Phase 5: Horizontal Built-ins
1. Refactor `repo_map` to multi-language scanners.
2. Refactor `quality_gate` into detector-driven profiles.
3. Refactor `test_matrix` into framework adapters.
4. Replace Python-only assumptions across built-in QA tools.

### Phase 6: Cleanup
1. Remove stale shims.
2. delete orphan scripts and empty folders
3. align docs, commands, and runtime metadata
4. close remaining duplicate code paths

## 14. Acceptance Criteria
Citnega Nextgen is complete when:
1. there is exactly one canonical execution engine
2. there is exactly one canonical capability registry
3. complex tasks compile into typed plans before execution
4. parallel tools and agents work under deterministic, policy-safe scheduling
5. workflows are plan templates, not disguised specialist prompts
6. skills and mental models are non-executable strategy inputs
7. built-in QA and repo tools are horizontal across major ecosystems
8. silent-failure patterns are removed from required runtime paths
9. mode metadata is consistent across protocol, CLI, and TUI
10. code organization has no random or stale top-level folders
11. CI blocks on type checks, import contracts, correctness, and performance regressions
12. external evaluation excluding multimodal/auth rates Citnega above 9/10

## 15. Immediate Work Backlog

### P0
1. Replace multi-agent orchestration overlap with `CompiledPlan` + `ExecutionEngine` architecture.
2. Implement DAG batch scheduler with real parallel step execution.
3. Replace static built-in registry instantiation with manifest-driven capability providers.
4. Remove silent-failure behavior from required runtime loading.

### P1
5. Rework workflows into plan templates.
6. Add first-class skills.
7. Add mental-model compilation.
8. Refactor `quality_gate`, `test_matrix`, and `repo_map` to be language-aware and horizontal.
9. Remove heuristic schema probing in planner/conversation paths.

### P2
10. Persist plan phase and compiled plan state.
11. Eliminate stale help/documentation mismatches.
12. Remove low-value wrappers and stale folders/files.
13. Tighten TUI diagnostics and structured error presentation.

## 16. Non-Negotiable Engineering Rules
1. No `except Exception: pass` in core runtime paths.
2. No private-attribute reach-through across architectural boundaries.
3. No duplicate planning or execution semantics across agents.
4. No feature exposure drift between runtime and UI.
5. No hardcoded product behavior when configuration or capability metadata should own it.
6. No language-specific assumptions in horizontal built-ins without a detector/profile boundary.
7. No new folder without a bounded-context justification.
8. No test placement that does not mirror the production bounded context.
