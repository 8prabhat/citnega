# Citnega

**Citnega** is a local-first terminal AI runtime with a full TUI, plan compiler, parallel tool execution, and workspace-extensible agents/tools/skills.  
It is designed for real repository work from a single `citnega` command.

```
pip install citnega
citnega
```

Current package line: `0.6.x`

---

## Features

- **Terminal UI** built on [Textual](https://textual.textualize.io/) — keyboard-driven, themeable, no browser required
- **Pluggable framework adapters** — swap between `direct` (built-in), Google ADK, LangGraph, or CrewAI without changing application code
- **Parallel tool execution** — independent tool calls fan out concurrently via `asyncio.TaskGroup`
- **Plan mode** — draft → approve → execute multi-step plans with a structured compiler and scheduler
- **Persistent knowledge base** — full-text search, tagging, and session-scoped KB retrieval
- **Workspace overlay** — drop custom agents, tools, workflows, and skills into a workfolder; they override built-ins by name
- **Conversation compaction** — automatic summarisation keeps context within token budget
- **Policy enforcement** — file path bounds, network controls, approval gates, per-tool overrides
- **Circuit breaker** per model provider with configurable thresholds and cooldown

---

## Installation

```bash
# Core (direct adapter, built-in tools)
pip install citnega

# With Google ADK support
pip install "citnega[adk]"

# With LangGraph
pip install "citnega[langgraph]"

# With CrewAI
pip install "citnega[crewai]"

# Everything
pip install "citnega[all]"
```

Requires Python 3.11+.

---

## Quick Start

```bash
# Launch the TUI
citnega

# New session directly
citnega --session my-project

# Headless CLI
citnega-cli run --session my-session --prompt "Summarise the latest changes in this repo"

# List sessions
citnega-cli session list
```

### TUI keyboard shortcuts

| Key | Action |
|-----|--------|
| `Enter` | Send message |
| `↑` / `↓` | Browse input history |
| `/` | Start a slash command |
| `Ctrl+K` | Open command palette |
| `Ctrl+Y` | Copy last response |
| `Ctrl+L` | Clear chat |
| `Ctrl+C` | Quit |

### Slash commands

| Command | Description |
|---------|-------------|
| `/model [id]` | Show or switch the active model |
| `/mode [name]` | Switch session mode (`chat`, `plan`, `explore`, …) |
| `/think [on\|off\|auto]` | Toggle extended thinking |
| `/compact` | Compact conversation history |
| `/sessions` | List all sessions |
| `/new` | Start a new session |
| `/rename <name>` | Rename current session |
| `/setworkfolder <path>` | Point to a workfolder |
| `/createtool` | Scaffold a new custom tool |
| `/createagent` | Scaffold a new custom agent |
| `/createworkflow` | Scaffold a new YAML workflow template |
| `/createskill` | Scaffold a new `SKILL.md` bundle |
| `/help` | List all commands |

---

## Configuration

Config lives in the platform app-home directory:

| Platform | Path |
|----------|------|
| macOS | `~/Library/Application Support/citnega/config/` |
| Linux | `~/.local/share/citnega/config/` |
| Windows | `%APPDATA%\citnega\config\` |

Key files:

- `settings.toml` — runtime, session, model, logging, workspace, policy settings
- `models.yaml` — model registry (providers, priorities, thinking flags)

All settings can also be set via environment variables with the `CITNEGA_` prefix:

```bash
CITNEGA_RUNTIME__DEFAULT_MODEL_ID=gpt-4o citnega
CITNEGA_NEXTGEN__PLANNING_ENABLED=true citnega
```

### Minimal `settings.toml`

```toml
[runtime]
default_model_id = "gpt-4o"
local_only       = false

[workspace]
workfolder_path = "/home/you/my-citnega-workspace"
```

---

## Workfolder

A workfolder is a directory that extends Citnega with your own agents, tools, and workflows. Workfolder callables override built-ins of the same name.

```
my-workspace/
├── agents/          # custom agent modules
├── tools/           # custom tool modules
├── workflows/       # YAML or Python workflow definitions
├── skills/          # SKILL.md bundles
└── memory/          # runtime state (sessions, KB, logs, artifacts)
    ├── db/
    ├── sessions/
    ├── kb/
    └── logs/
```

Set the path via `/setworkfolder` in the TUI, or in `settings.toml`:

```toml
[workspace]
workfolder_path = "/absolute/path/to/workspace"
```

### Custom tool example

```python
# my-workspace/tools/summarise.py
from citnega.packages.protocol.interfaces.tool import ITool, ToolResult

class SummariseTool(ITool):
    name        = "summarise"
    description = "Summarise a block of text in one paragraph."

    async def invoke(self, input, ctx):
        text = input.get("text", "")
        # ... call your model / logic here
        return ToolResult(output=summary)
```

---

## Built-in Tools

| Tool | Description |
|------|-------------|
| `read_file` | Read a file from disk |
| `write_file` | Write or create a file |
| `edit_file` | Apply targeted edits to a file |
| `list_dir` | List directory contents |
| `search_files` | Full-text search across a file tree |
| `run_shell` | Execute a shell command |
| `git_ops` | Git status, diff, log, commit, push |
| `web_search` | Search the web (requires provider) |
| `read_kb` | Retrieve from the persistent knowledge base |
| `write_kb` | Save a note or document to the KB |
| `repo_map` | Generate a structural map of a repository |
| `quality_gate` | Run linters and type-checkers |
| `test_matrix` | Discover and run test suites |

---

## Architecture

```
apps/
  tui/       — Textual TUI (ChatScreen, widgets, controllers)
  cli/       — Typer CLI (citnega-cli)
packages/
  bootstrap/ — Dependency composition and startup
  runtime/   — CoreRuntime, ApplicationService, SessionManager
  adapters/  — Framework adapters (direct, ADK, LangGraph, CrewAI)
  agents/    — Built-in agents (conversation, planner, specialist)
  tools/     — Built-in tools
  planning/  — PlanCompiler, PlanScheduler, TaskClassifier
  execution/ — ExecutionEngine (parallel batch runner)
  strategy/  — StrategySpec, SkillLoader, MentalModelCompiler
  capabilities/ — CapabilityRegistry and descriptors
  model_gateway/ — Provider abstraction, retry, circuit breaker
  context/   — Context assembly pipeline (handlers, token budget)
  kb/        — Knowledge base (SQLite FTS5)
  workspace/ — Workfolder loader and overlay
  config/    — Pydantic settings, TOML loaders
  protocol/  — Shared interfaces, events, models (no deps)
```

The `protocol` package defines all interfaces and events; every other package depends on it but not on each other, enforcing a clean dependency graph.

---

## Development

```bash
git clone https://github.com/8prabhat/citnega.git
cd citnega
uv sync --all-extras
uv run citnega
```

### Tests

```bash
uv run pytest                    # full suite
uv run pytest tests/unit/        # unit tests only
uv run pytest tests/integration/ # integration tests
uv run pytest --cov --cov-report=term-missing
```

### Linting

```bash
uv run ruff check .
uv run mypy packages apps --ignore-missing-imports
uv run lint-imports --config import-linter.ini
```

### Release

Build and publish manually:

```bash
python -m build
twine check dist/*
TWINE_USERNAME=__token__ TWINE_PASSWORD='pypi-<api-token>' twine upload dist/*
```

---

## License

MIT © 2025 Prabhat Kumar
