```
 ██████╗██╗████████╗███╗   ██╗███████╗ ██████╗  █████╗
██╔════╝██║╚══██╔══╝████╗  ██║██╔════╝██╔════╝ ██╔══██╗
██║     ██║   ██║   ██╔██╗ ██║█████╗  ██║  ███╗███████║
██║     ██║   ██║   ██║╚██╗██║██╔══╝  ██║   ██║██╔══██║
╚██████╗██║   ██║   ██║ ╚████║███████╗╚██████╔╝██║  ██║
 ╚═════╝╚═╝   ╚═╝   ╚═╝  ╚═══╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝
```

<div align="center">

# CITNEGA

### Your AI. Your Terminal. Your Rules.

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.6.1-orange.svg)](https://github.com/8prabhat/citnega/releases)

**A local-first AI runtime that lives in your terminal.**  
Plan, research, write, code, analyse — with 9 thinking modes, 60+ tools, and 35+ specialist agents — all without leaving your keyboard.

```bash
pip install citnega && citnega
```

</div>

---

## What Is Citnega?

Citnega is a self-contained AI assistant that runs entirely in your terminal. It is not a thin chatbot wrapper — it is a full AI runtime: session management, multi-agent orchestration, parallel tool execution, a persistent knowledge base, and a polished keyboard-driven interface, all in one command.

**You do not need to be a developer to use Citnega.** If you are comfortable with a terminal, Citnega gives you a powerful thinking and research partner that can browse the web, read and write documents, write and run code, analyse data, manage files, and remember everything across sessions.

**Who uses Citnega?**

| I want to… | Citnega does it |
|------------|----------------|
| Research a topic thoroughly with real sources | `auto_research` mode — multi-angle search, source scoring, cited report |
| Write a structured plan before doing anything | `plan` mode — draft → review → execute |
| Explore a codebase or debug a problem | `code` mode — reads files, runs commands, checks diffs |
| Do a deep dive into any subject | `explore` mode — agents fan out, gather evidence, synthesise |
| Run a professional code review | `review` mode — mandatory diff reading, evidence-based findings |
| Execute a step-by-step operational runbook | `operate` mode — state, execute, verify each step |
| Let the AI work autonomously toward a goal | `autonomous` mode — self-directed, replans on failure |
| Just have a smart conversation | `chat` mode — default, always on |

---

## Features

- **9 session modes** — `chat`, `plan`, `explore`, `research`, `code`, `review`, `operate`, `autonomous`, `auto_research` — each with its own behaviour, tool budget, and system prompt
- **Terminal UI** — built on [Textual](https://textual.textualize.io/), fully keyboard-driven, no browser needed, themeable
- **Multi-agent orchestration** — requests are automatically routed to the right specialist; complex goals are decomposed into parallel DAG steps with retries and rollback
- **60+ built-in tools** — filesystem, git, shell, web search, web scraping, data analysis, PDF/Excel/Word export, chart rendering, GitHub/Jira/Linear, email, Slack, and more
- **35+ specialist agents** — code, QA, research, security, data science, ML, writing, finance, legal, HR, marketing, sales, UX, SRE, DevOps, and more
- **Autonomous deep research** — 9-phase structured loop: KB-first check, multi-angle search, source quality scoring, cross-verification, provenance tracking, adaptive re-search, cited structured report
- **Persistent knowledge base** — everything the AI learns is saved across sessions in a full-text-searchable SQLite store
- **Workfolder overlay** — add your own agents, tools, and skills to a local directory; they override built-ins without touching the package
- **Model-agnostic** — connect Ollama (local), any OpenAI-compatible API, vLLM, or LiteLLM; the gateway has per-provider circuit breaking and priority routing
- **Framework adapters** — swap the execution backbone to Google ADK, LangGraph, or CrewAI with one config line
- **MCP support** — plug in any Model Context Protocol server as a tool source
- **Policy enforcement** — file path bounds, network controls, per-tool approval gates
- **Context efficiency** — automatic conversation compaction, tool-result compression, token budget pipeline

---

## Installation

```bash
# Standard install
pip install citnega

# With Google ADK support
pip install "citnega[adk]"

# With LangGraph
pip install "citnega[langgraph]"

# With CrewAI
pip install "citnega[crewai]"

# With MCP support
pip install "citnega[mcp]"

# Everything
pip install "citnega[all]"
```

**Requires Python 3.11 or newer.**

### Install from source

```bash
git clone https://github.com/8prabhat/citnega.git
cd citnega
python -m venv .citnega_env
source .citnega_env/bin/activate    # Windows: .citnega_env\Scripts\activate
pip install -e ".[dev]"
```

---

## Quick Start

```bash
# Launch the interactive TUI
citnega

# Open a named session directly
citnega --session my-project

# Run a one-shot prompt from the command line
citnega-cli run --session work --prompt "What changed in this repo in the last week?"

# List all sessions
citnega-cli session list
```

### First time

1. Run `citnega` — it opens in `chat` mode.
2. Type `/setup` to configure a model (Ollama, OpenAI API, etc.).
3. Type `/mode research` and ask it to research anything.
4. Type `/mode code` and ask it to look at a file or run a command.
5. Type `/help` to see everything available.

---

## The TUI

```
┌─ Citnega ────────────────────────────────────────── [CODE] claude-sonnet ─┐
│                                                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │ You: read the main.py file and explain what it does                  │ │
│  │                                                                      │ │
│  │ Citnega: I'll read the file first.                                   │ │
│  │ [read_file] main.py → 142 lines                                      │ │
│  │                                                                      │ │
│  │ This is the entry point for your web server. It sets up...           │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│                                                                            │
│  > _                                                              F1 F2 F3 │
└────────────────────────────────────────────────────────────────────────────┘
```

### Keyboard shortcuts

| Key | Action |
|-----|--------|
| `Enter` | Send message |
| `↑` / `↓` | Browse message history |
| `/` | Open slash command input |
| `Ctrl+K` | Command palette |
| `Ctrl+Y` | Copy last response |
| `Ctrl+L` | Clear chat |
| `F1` | Settings |
| `F2` | Session picker |
| `F3` | Session history |
| `Ctrl+C` | Quit |

### Slash commands

| Command | What it does |
|---------|-------------|
| `/mode [name]` | Switch to a different thinking mode |
| `/model [id]` | Show or change the active model |
| `/sessions` | List all your sessions |
| `/new` | Start a fresh session |
| `/rename <name>` | Rename this session |
| `/compact` | Compress conversation history to save context |
| `/think [on\|off\|auto]` | Toggle extended thinking (where supported) |
| `/setworkfolder <path>` | Point to a custom workspace directory |
| `/createtool` | Scaffold a new custom tool |
| `/createagent` | Scaffold a new custom agent |
| `/createskill` | Scaffold a new skill bundle |
| `/help` | Show all available commands |

---

## Session Modes

Every mode shapes how Citnega thinks and acts. Switch anytime with `/mode <name>`.

| Mode | What it does | Tool rounds | Temp |
|------|-------------|-------------|------|
| `chat` | Conversational — no constraints, direct answers | 5 | 0.7 |
| `plan` | Draft a numbered plan first, then execute after your approval | 5 | 0.4 |
| `explore` | Deep multi-angle exploration — calls agents, follows threads | 12 | 0.8 |
| `research` | Evidence-driven structured report with mandatory source citing | 15 | 0.3 |
| `code` | Reads files, runs commands, edits code, checks git | 10 | 0.2 |
| `review` | Code review — reads the diff, gathers evidence, grades findings | 8 | 0.3 |
| `operate` | Runbook discipline — state → execute → verify each step | 8 | 0.2 |
| `autonomous` | Self-directed — works toward a goal, replans on failure | 30 | 0.2 |
| `auto_research` | 9-phase structured research: multi-angle, cross-verified, cited report | 40 | 0.4 |

**Tool rounds** = how many tool-call turns the AI gets per response. Higher = deeper work.

---

## Architecture

```
citnega/
├── apps/
│   ├── tui/                  Textual TUI (ChatScreen, session picker, history)
│   └── cli/                  Typer CLI (citnega-cli)
│
└── packages/
    ├── protocol/             ← Central hub: all interfaces, events, models.
    │                           Every package depends on this; none depend
    │                           on each other. Clean, testable graph.
    │
    ├── bootstrap/            Startup: 28-step composition root, DI wiring
    ├── runtime/              CoreRuntime, sessions, events, policy, scheduling
    ├── adapters/             direct | adk | langgraph | crewai
    │
    ├── agents/
    │   ├── core/             11 routing + orchestration agents
    │   ├── specialists/      26 domain specialist agents
    │   ├── domain/           Domain agents (finance, legal, healthcare…)
    │   └── roles/            Role agents (reviewer, writer)
    │
    ├── tools/
    │   ├── builtin/          60+ tool implementations
    │   └── security/         Security toolset
    │
    ├── planning/             PlanCompiler, PlanValidator, TaskClassifier
    ├── execution/            ExecutionEngine — parallel DAG step runner
    ├── capabilities/         CapabilityRegistry — index of all agents + tools
    ├── model_gateway/        Provider abstraction, circuit breaker, rate limiter
    ├── skills/               Domain skill bundles (prompt templates + triggers)
    ├── kb/                   Knowledge base (SQLite FTS5)
    ├── mcp/                  Model Context Protocol bridge
    ├── messaging/            Telegram, Discord channels
    ├── observability/        Structured logging, retention
    ├── security/             Key store, permissions, secrets scrubber
    ├── storage/              SQLite, Alembic migrations, repositories
    ├── config/               Pydantic settings, TOML loaders
    └── workspace/            Workfolder overlay loader
```

### How a request flows

```
Your message
     │
     ▼
DirectModelRunner
     ├─ IntentClassifierAgent   zero-token keyword routing
     ├─ SessionMode             augments system prompt
     │
     ├─ Tool calls (parallel, up to N rounds per mode)
     │       │
     │       ├─ ConversationAgent ──► RouterAgent ──► Specialist(s)
     │       ├─ OrchestratorAgent ──► DAG steps ──► ExecutionEngine
     │       └─ PlannerAgent ────────────────────► OrchestratorAgent
     │
     └─ Token compression + knowledge base persistence
```

### Design principles

- **Protocol hub** — `packages/protocol` is the only package everyone can import. Nothing else cross-imports, so every module is independently testable.
- **Dependency injection** — `PolicyEnforcer`, `EventEmitter`, and `Tracer` are injected at construction; no global state.
- **Open/Closed** — adding a new mode is one class + one line. Adding a new tool is one file. Nothing else changes.
- **Workfolder overlay** — your custom callables shadow built-ins by name; you never fork the package.

---

## Built-in Agents

### Core (routing, orchestration, reasoning)

| Agent | What it does |
|-------|-------------|
| `ConversationAgent` | Primary orchestrator — routes to specialists, synthesises results |
| `OrchestratorAgent` | DAG planner — dependencies, retries, rollback, remote dispatch |
| `PlannerAgent` | Decomposes goals and delegates to OrchestratorAgent |
| `RouterAgent` | Picks the right specialist for a given request |
| `IntentClassifierAgent` | Zero-token keyword classifier — routes before any LLM call |
| `RePlanner` | Invoked on step failure to revise the remaining plan |
| `ReasoningAgent` | Chain-of-thought reasoning for complex inference |
| `ValidatorAgent` | Output quality checking and validation |
| `WriterAgent` | Structured document and report generation |
| `RetrieverAgent` | Knowledge base retrieval and context assembly |
| `ToolExecutorAgent` | Safe isolated tool invocation with policy enforcement |

### Specialists (domain experts)

| Area | Agents |
|------|--------|
| Engineering | `code_agent`, `qa_agent`, `qa_engineer_agent`, `sre_agent`, `devops_agent`, `release_agent`, `ml_engineer_agent` |
| Research & Data | `research_agent`, `auto_research_agent`, `data_agent`, `data_analyst_agent`, `data_scientist_agent` |
| Writing | `writing_agent`, `summary_agent`, `customer_support_agent` |
| Business | `business_analyst_agent`, `product_manager_agent`, `marketing_agent`, `sales_agent`, `ux_design_agent` |
| Risk & Compliance | `security_agent`, `lawyer_agent`, `risk_manager_agent`, `financial_controller_agent` |
| Operations | `hr_agent`, `file_agent` |

---

## Built-in Tools

### Files, code, and shell

| Tool | Does |
|------|------|
| `read_file` | Read any file |
| `write_file` | Create or overwrite a file |
| `edit_file` | Surgical find-and-replace edits |
| `list_dir` | List directory contents |
| `search_files` | Full-text search across a file tree |
| `repo_map` | Structural map of a codebase |
| `run_shell` | Run any shell command |
| `git_ops` | Status, diff, log, add, commit, push |
| `quality_gate` | Linting and type checking |
| `test_matrix` | Discover and run test suites |

### Web and research

| Tool | Does |
|------|------|
| `search_web` | Search the web |
| `read_webpage` | Fetch and parse a page as Markdown |
| `fetch_url` | Raw HTTP fetch |
| `web_scraper` | Structured web scraping |

### Knowledge base

| Tool | Does |
|------|------|
| `read_kb` | Full-text search in the persistent KB |
| `write_kb` | Save notes, findings, or documents |

### Data and analysis

| Tool | Does |
|------|------|
| `pandas_analyze` | Analyse CSV/DataFrames |
| `data_profiler` | Statistical profiling |
| `pivot_table` | Pivot tables from structured data |
| `sql_query` | SQL against SQLite |
| `calculate` | Safe arithmetic |

### Documents and visualisation

| Tool | Does |
|------|------|
| `render_chart` | Generate charts with Matplotlib |
| `write_pdf` | Export to PDF |
| `write_docx` | Export to Word |
| `create_excel` | Create Excel workbooks |
| `create_ppt` | Create PowerPoint presentations |
| `mermaid_render` | Render Mermaid diagrams |
| `ocr_image` | Extract text from images (`citnega[ocr]`) |

### Integrations

| Tool | Does |
|------|------|
| `github_ops` | GitHub issues, PRs, repos |
| `jira_ops` | Jira issue management |
| `linear_ops` | Linear issue tracking |
| `email_reader` | Read emails |
| `email_composer` | Send emails |
| `slack_notifier` | Slack messages |
| `calendar_event` | Create calendar events |
| `prometheus_query` | PromQL queries |
| `vault_secret` | HashiCorp Vault secrets |
| `browser_session` | Browser automation |

### Security

| Tool | Does |
|------|------|
| `port_scanner` | TCP port scanning |
| `ssl_tls_audit` | Certificate and cipher audit |
| `secrets_scanner` | Scan for leaked secrets |
| `vuln_scanner` | Dependency vulnerability scan |

---

## Model Providers

Connect any model. Configure in `model_registry.toml` or `models.yaml`.

| Provider | `provider_type` | Notes |
|----------|----------------|-------|
| **Ollama** | `ollama` | Local models — Gemma, Llama, Mistral, Qwen, any `ollama pull` model |
| **OpenAI-compatible** | `openai_compatible` | OpenAI, Anthropic (via proxy), Groq, Together, Fireworks, etc. |
| **vLLM** | `vllm` | Self-hosted vLLM inference server |
| **LiteLLM** | `litellm` | 100+ providers via LiteLLM proxy |
| **Custom** | `custom_remote` | Implement `BaseProvider` for any API |

The gateway picks by priority, fails over on error, and applies a per-provider circuit breaker with configurable thresholds.

### Minimal `model_registry.toml`

```toml
[[models]]
model_id      = "my-model"
provider_type = "ollama"
model_name    = "gemma3:12b"
priority      = 100

[models.capabilities]
supports_streaming    = true
supports_tool_calling = true
```

---

## Framework Adapters

| Adapter | Install | When to use |
|---------|---------|-------------|
| `direct` | *(included)* | Default — best performance, full Citnega feature set |
| `adk` | `citnega[adk]` | Google Agent Development Kit ecosystem |
| `langgraph` | `citnega[langgraph]` | LangGraph state machines |
| `crewai` | `citnega[crewai]` | CrewAI multi-agent framework |

Set in `settings.toml`: `framework = "direct"`

---

## Configuration

Config directory:

| Platform | Location |
|----------|----------|
| macOS | `~/Library/Application Support/citnega/config/` |
| Linux | `~/.local/share/citnega/config/` |
| Windows | `%APPDATA%\citnega\config\` |

### `settings.toml` reference

```toml
[runtime]
default_model_id      = "my-model"   # from model_registry.toml
framework             = "direct"      # direct | adk | langgraph | crewai
local_only            = true          # refuse remote API calls
max_supervisor_rounds = 6             # routing depth for ConversationAgent

[workspace]
workfolder_path = "/path/to/my-workspace"

[session]
default_mode = "chat"                 # which mode to start new sessions in

[nextgen]
planning_enabled   = true
execution_enabled  = true
skills_enabled     = true

[context]
recent_turns_count = 10               # turns kept in the active context window

[policy]
allow_network    = true
require_approval = false              # if true, tool calls need your confirmation
```

Every setting can be overridden with an environment variable using `CITNEGA_` prefix and `__` for nesting:

```bash
CITNEGA_RUNTIME__DEFAULT_MODEL_ID=my-model citnega
CITNEGA_SESSION__DEFAULT_MODE=research citnega
CITNEGA_POLICY__REQUIRE_APPROVAL=true citnega
```

---

## Workfolder — Extend Without Forking

A workfolder is a directory that layers on top of everything built in. Drop files in; Citnega finds them automatically. Your custom agent or tool overrides the built-in of the same name.

```
my-workspace/
├── agents/       custom agent .py files
├── tools/        custom tool .py files
├── workflows/    YAML workflow definitions
├── skills/       SKILL.md prompt bundles
└── memory/       managed automatically — sessions, KB, logs, artefacts
```

Set with `/setworkfolder /path/to/workspace` or in `settings.toml`.

### Custom tool in 10 lines

```python
# my-workspace/tools/currency.py
from citnega.packages.protocol.interfaces.tool import ITool, ToolResult

class CurrencyTool(ITool):
    name        = "currency_convert"
    description = "Convert an amount between currencies."

    async def invoke(self, input: dict, ctx) -> ToolResult:
        # ... your logic
        return ToolResult(output=f"{input['amount']} {input['from']} = ...")
```

### Custom agent in 20 lines

```python
# my-workspace/agents/summariser.py
from pydantic import BaseModel, Field
from citnega.packages.agents.specialists._specialist_base import SpecialistBase, SpecialistOutput
from citnega.packages.protocol.callables.types import CallablePolicy

class SummariserInput(BaseModel):
    text: str = Field(description="Text to summarise.")

class SummariserAgent(SpecialistBase):
    name         = "summariser"
    description  = "Summarises long text into a concise paragraph."
    input_schema = SummariserInput
    output_schema = SpecialistOutput
    policy = CallablePolicy(timeout_seconds=30.0)

    async def _execute(self, input: SummariserInput, context) -> SpecialistOutput:
        result = await self._call_model(f"Summarise this:\n\n{input.text}")
        return SpecialistOutput(response=result)
```

---

## MCP Integration

Citnega can connect to any [Model Context Protocol](https://modelcontextprotocol.io) server and expose its tools to all agents automatically.

```toml
# settings.toml
[mcp]
enabled = true

[[mcp.servers]]
name    = "filesystem"
command = "npx"
args    = ["-y", "@modelcontextprotocol/server-filesystem", "/home/you"]
```

Install with `pip install "citnega[mcp]"`.

---

## Skills

Skills are prompt bundles that activate automatically when your request matches their triggers. They tell agents how to approach a class of problem — no manual mode switching required.

| Domain | Covers |
|--------|--------|
| Core | General reasoning, step-by-step thinking, clarification |
| Auto-Research | Multi-angle research, source verification, cited reports |
| Business | Market analysis, competitive intelligence, SWOT |
| Data & ML | EDA, model evaluation, feature engineering |
| Operations | SRE runbooks, incident response, capacity planning |
| Risk & Legal | Compliance review, risk assessment, contract analysis |
| HR | Hiring, performance review, policy drafting |
| Product | PRD writing, user story mapping, roadmap planning |
| Marketing | Campaign design, copy, SEO, analytics |
| Sales | Outreach, pipeline, proposal writing |
| UX | User research, design critique, accessibility |
| Support | Ticket triage, escalation paths, KB articles |
| Finance | Budgeting, forecasting, financial modelling |

Add your own by putting a `SKILL.md` in `my-workspace/skills/`.

---

## Development

```bash
# Install dev extras
pip install -e ".[dev]"

# Run tests
python -m pytest                      # full suite
python -m pytest tests/unit/          # unit tests only (fast, no network)
python -m pytest tests/integration/   # integration tests
python -m pytest --cov --cov-report=term-missing

# Linting and type checking
ruff check .
mypy packages apps --ignore-missing-imports

# Check import boundaries (protocol hub rule)
lint-imports --config import-linter.ini

# Build a wheel
python -m build
```

---

## License

MIT © 2025 Prabhat Kumar

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

---

## Contributing

Issues and PRs are welcome at [github.com/8prabhat/citnega](https://github.com/8prabhat/citnega/issues).

Before opening a PR:
1. `ruff check .` and `mypy packages apps` — no new errors
2. Add tests — `pytest tests/unit/` must pass
3. Keep `packages/protocol` free of imports from other packages
