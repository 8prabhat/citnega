"""citnega doctor — runtime self-diagnostics command.

Runs a series of checks and reports pass/fail per check so the operator
can quickly diagnose misconfiguration or missing dependencies.

Output is human-readable by default; use --json for machine-readable JSONL.
"""

from __future__ import annotations

import json

import typer

app = typer.Typer(help="Runtime self-diagnostics.")


def _check(label: str, fn) -> dict:
    """Run fn(); return a dict with ok, label, detail."""
    try:
        detail = fn()
        return {"ok": True, "check": label, "detail": detail or "ok"}
    except Exception as exc:
        return {"ok": False, "check": label, "detail": str(exc)}


@app.command("check")
def doctor_check(
    as_json: bool = typer.Option(False, "--json", help="Emit one JSON object per line."),
) -> None:
    """Run all startup self-checks and report pass/fail."""
    results: list[dict] = []

    # ── 1. Config loads without errors ───────────────────────────────────────
    def _check_config():
        from citnega.packages.config.loaders import load_settings
        s = load_settings()
        return f"framework={s.runtime.framework}, model={s.runtime.default_model_id}"

    results.append(_check("config", _check_config))

    # ── 2. Framework adapter is known ────────────────────────────────────────
    def _check_framework():
        from citnega.packages.bootstrap.bootstrap import _select_adapter
        from citnega.packages.config.loaders import load_settings
        from citnega.packages.storage.path_resolver import PathResolver
        s = load_settings()
        pr = PathResolver()
        adapter = _select_adapter(s.runtime.framework, pr)
        return f"adapter={adapter.__class__.__name__}"

    results.append(_check("framework_adapter", _check_framework))

    # ── 3. Models YAML is present and has at least one entry ─────────────────
    def _check_models():
        from citnega.packages.model_gateway.yaml_config import load_yaml_config
        cfg = load_yaml_config(None)
        count = len(cfg.models)
        if count == 0:
            raise ValueError("No models defined in models.yaml")
        return f"{count} model(s) defined, default={cfg.default_model}"

    results.append(_check("models_yaml", _check_models))

    # ── 4. Database is reachable (SQLite file exists or can be created) ───────
    def _check_db():
        from citnega.packages.storage.path_resolver import PathResolver
        pr = PathResolver()
        db_path = pr.db_path
        # Just verify the parent dir is writable
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return f"db_path={db_path}"

    results.append(_check("database_path", _check_db))

    # ── 5. KB store module importable ────────────────────────────────────────
    def _check_kb():
        from citnega.packages.kb.store import KnowledgeStore  # noqa: F401
        return "importable"

    results.append(_check("kb_store", _check_kb))

    # ── 6. Tool registry builds without errors ────────────────────────────────
    def _check_tools():
        from unittest.mock import MagicMock

        from citnega.packages.storage.path_resolver import PathResolver
        from citnega.packages.tools.registry import ToolRegistry
        pr = PathResolver()
        reg = ToolRegistry(
            enforcer=MagicMock(),
            emitter=MagicMock(),
            tracer=MagicMock(),
            path_resolver=pr,
            kb_store=None,
        )
        tools = reg.build_all()
        return f"{len(tools)} tool(s) registered"

    results.append(_check("tool_registry", _check_tools))

    # ── 7. Agent registry builds without errors ───────────────────────────────
    def _check_agents():
        from unittest.mock import MagicMock

        from citnega.packages.agents.registry import AgentRegistry
        reg = AgentRegistry(
            enforcer=MagicMock(),
            emitter=MagicMock(),
            tracer=MagicMock(),
            tools={},
        )
        agents = reg.build_all()
        return f"{len(agents)} agent(s) registered"

    results.append(_check("agent_registry", _check_agents))

    # ── 8. Context handler imports all resolve ────────────────────────────────
    def _check_handlers():
        from citnega.packages.runtime.context.handlers.kb_retrieval import (
            KBRetrievalHandler,  # noqa: F401
        )
        from citnega.packages.runtime.context.handlers.recent_turns import (
            RecentTurnsHandler,  # noqa: F401
        )
        from citnega.packages.runtime.context.handlers.runtime_state import (
            RuntimeStateHandler,  # noqa: F401
        )
        from citnega.packages.runtime.context.handlers.session_summary import (
            SessionSummaryHandler,  # noqa: F401
        )
        from citnega.packages.runtime.context.handlers.token_budget import (
            TokenBudgetHandler,  # noqa: F401
        )
        return "all 5 handlers importable"

    results.append(_check("context_handlers", _check_handlers))

    # ── 9. Policy enforcer instantiates ──────────────────────────────────────
    def _check_policy():
        from unittest.mock import MagicMock

        from citnega.packages.runtime.policy.enforcer import PolicyEnforcer
        PolicyEnforcer(MagicMock(), MagicMock())
        return "instantiated"

    results.append(_check("policy_enforcer", _check_policy))

    # ── 10. TUI app imports without error ─────────────────────────────────────
    def _check_tui():
        import importlib
        importlib.import_module("citnega.apps.tui.app")
        return "importable"

    results.append(_check("tui_app", _check_tui))

    # ── Render ────────────────────────────────────────────────────────────────
    passed = sum(1 for r in results if r["ok"])
    failed = len(results) - passed

    if as_json:
        for r in results:
            typer.echo(json.dumps(r))
        typer.echo(json.dumps({"summary": {"passed": passed, "failed": failed}}))
    else:
        for r in results:
            status = "PASS" if r["ok"] else "FAIL"
            typer.echo(f"  [{status}] {r['check']:<25} {r['detail']}")
        typer.echo()
        typer.echo(f"Results: {passed}/{len(results)} checks passed")

    if failed:
        raise typer.Exit(code=1)
