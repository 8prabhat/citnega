# Citnega

A local-first, platform-agnostic TUI + agentic framework for general-purpose tasks.

Citnega runs on **Linux**, **macOS**, and **Windows**. The terminal UI is modeled after Gemini CLI and Claude Code: a single scrollable conversation pane with streaming output, inline tool-call cards, approval prompts, and slash commands.

## Features

- **Conversational TUI** — single-pane interface with streaming LLM output
- **Framework-agnostic** — ADK, LangGraph, and CrewAI are equal, config-selected peers
- **Core + Specialist agents** — `ConversationAgent` orchestrates `ResearchAgent`, `FileAgent`, `DataAgent`, `WritingAgent`, `SummaryAgent`
- **10 built-in tools** — web_search, read_file, write_file, kb_search, list_dir, fetch_url, parse_csv, parse_json, run_calculation, search_files
- **Local KB** — SQLite FTS5 full-text search, no embeddings required
- **Secure secrets** — OS-native keyring (macOS Keychain / Windows Credential Manager / Linux Secret Service)
- **Approval gates** — dangerous operations (file writes, network) require user approval inline
- **Checkpointing** — runs can be paused, resumed, and recovered after process kill

## Installation

```bash
pip install citnega
# or
pipx install citnega
```

With a specific framework:
```bash
pip install "citnega[adk]"      # Google ADK
pip install "citnega[langgraph]" # LangGraph
pip install "citnega[crewai]"   # CrewAI
```

## Quick Start

```bash
# Launch TUI
citnega

# Run a task headlessly
citnega-cli run --session my-session --task "Summarize the latest IPCC report"

# List sessions
citnega-cli sessions list

# Search KB
citnega-cli kb search "climate risk"
```

## Configuration

Config files live in the platform-appropriate app home:
- **Linux:** `~/.local/share/citnega/config/`
- **macOS:** `~/Library/Application Support/citnega/config/`
- **Windows:** `%APPDATA%\citnega\config\`

Key config files:
- `settings.toml` — runtime framework, model, logging, TUI preferences
- `model_registry.toml` — model provider definitions
- `agent_registry.toml` — agent registrations
- `tool_registry.toml` — tool registrations with policies

## Development

```bash
git clone https://github.com/your-org/citnega
cd citnega
bash scripts/dev_setup.sh
```

### Running tests

```bash
uv run pytest                          # all tests
uv run pytest tests/unit/              # unit tests only
uv run pytest --cov=packages           # with coverage
```

### Linting and type checking

```bash
uv run ruff check .
uv run mypy packages/
uv run lint-imports                    # architecture contracts
```

## Architecture

See `citnega_technical_specification.txt` for the complete build-ready specification.

Key principles:
- **SOLID + DRY** throughout
- **Framework agnosticism** — only `packages/adapters/` imports framework SDKs
- **Composition root** — only `packages/bootstrap/bootstrap.py` wires concrete dependencies
- **Import contracts** enforced by `import-linter` in CI

## License

MIT
