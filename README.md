# Citnega

Citnega is a local-first agent runtime and terminal UI with pluggable framework adapters, built-in agents and tools, and a user workfolder for custom behavior.

## What Lives Where

Built-in code stays in the package:
- `packages/agents/` contains built-in agents
- `packages/tools/` contains built-in tools
- `packages/bootstrap/` and `apps/` contain composition roots and user interfaces

User-defined runtime data stays in the workfolder:
- `memory/` holds runtime state such as DB, logs, sessions, artifacts, KB data, checkpoints, and exports
- `agents/` holds custom agents
- `tools/` holds custom tools
- `workflows/` holds custom workflows

If a custom tool, agent, or workflow has the same name as a built-in callable, the workfolder version wins.

## Workfolder Layout

```text
<workfolder>/
├── memory/
│   ├── db/
│   ├── logs/
│   ├── sessions/
│   ├── artifacts/
│   ├── kb/
│   ├── checkpoints/
│   └── exports/
├── agents/
├── tools/
└── workflows/
```

Citnega will create the missing subdirectories when the workfolder is configured.

## Installation

```bash
pip install citnega
```

Optional framework extras:

```bash
pip install "citnega[adk]"
pip install "citnega[langgraph]"
pip install "citnega[crewai]"
```

## Quick Start

```bash
# Launch the TUI
citnega

# Run a task headlessly
citnega-cli run --session my-session --prompt "Summarize the latest IPCC report"

# List sessions
citnega-cli session list
```

## Configuration

Config files live in the platform app home:
- Linux: `~/.local/share/citnega/config/`
- macOS: `~/Library/Application Support/citnega/config/`
- Windows: `%APPDATA%\\citnega\\config\\`

Key config files:
- `settings.toml` for runtime, model, logging, and workspace defaults
- `workspace.toml` for the active workfolder path
- `model_registry.toml` for model definitions

To point Citnega at a workfolder, set:

```toml
[workspace]
workfolder_path = "/absolute/path/to/workfolder"
```

When a workfolder is configured, runtime state is stored under `<workfolder>/memory` instead of the app-home data directory.

## Development

```bash
git clone https://github.com/your-org/citnega
cd citnega
bash scripts/dev_setup.sh
```

### Tests

```bash
uv run pytest
uv run pytest tests/unit/
uv run pytest tests/integration/
```

### Linting

```bash
uv run ruff check .
uv run mypy packages apps
uv run lint-imports --config import-linter.ini
```

## Architecture Notes

- Framework adapters stay isolated under `packages/adapters/`
- Bootstrap code composes concrete dependencies and loads the workspace overlay
- Built-in callables are loaded first, then workfolder callables override them by name
- Core agents are rewired after overrides so they see the final tool and agent registry

## License

MIT
