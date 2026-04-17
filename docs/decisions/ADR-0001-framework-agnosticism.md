# ADR-0001: Framework Agnosticism

**Status:** Accepted  
**Date:** 2026-04-08

## Context

Citnega needs to execute agentic workflows. Multiple frameworks exist (Google ADK, LangGraph, CrewAI) with different APIs, lifecycle models, and tool-calling conventions. Building against any one framework creates lock-in and makes it difficult to switch as the ecosystem evolves.

## Decision

No layer above the adapter boundary may import or reference any specific agent framework. The framework in use is a **runtime configuration value** (`settings.toml:[runtime].framework`). All three frameworks (ADK, LangGraph, CrewAI) are equal peers, each implemented as a concrete `IFrameworkAdapter` in an isolated subpackage.

The `import-linter` contract `no-framework-imports-outside-adapters` enforces this in CI.

## Consequences

- Switching frameworks is a one-line config change.
- All three adapters must pass the same shared LSP integration test suite (`tests/adapters/shared_suite.py`).
- Framework-specific packages are optional dependencies in `pyproject.toml`.
- The adapter layer is the only place that translates between Citnega's canonical event model and framework-native events.
