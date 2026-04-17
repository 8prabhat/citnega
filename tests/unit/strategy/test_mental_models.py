from __future__ import annotations

from citnega.packages.strategy import MentalModelClauseType, compile_mental_model


def test_compile_mental_model_extracts_strategy_clauses():
    spec = compile_mental_model(
        """
        First map the repo.
        Then verify assumptions with tests.
        Ask before risky edits.
        Use parallel work where safe.
        Be conservative with changes.
        """
    )

    assert [clause.clause_type for clause in spec.clauses] == [
        MentalModelClauseType.ORDERING,
        MentalModelClauseType.ORDERING,
        MentalModelClauseType.APPROVAL,
        MentalModelClauseType.PARALLELISM,
        MentalModelClauseType.RISK,
    ]
    assert spec.recommended_parallelism == 4
    assert spec.risk_posture == "conservative"


# ── MentalModelCompiledEvent emission ─────────────────────────────────────────


def test_compile_mental_model_via_service_emits_event():
    """compile_mental_model() on ApplicationService emits MentalModelCompiledEvent."""
    from unittest.mock import MagicMock

    from citnega.packages.protocol.events.planning import MentalModelCompiledEvent
    from citnega.packages.runtime.app_service import ApplicationService
    from citnega.packages.shared.registry import CallableRegistry

    events: list = []
    emitter = MagicMock()
    emitter.emit.side_effect = events.append

    runtime = MagicMock()
    runtime.get_runner = MagicMock(return_value=None)
    runtime.capability_registry = None

    svc = ApplicationService.__new__(ApplicationService)
    svc._runtime = runtime
    svc._emitter = emitter
    svc._callable_registry = CallableRegistry()
    svc._capability_registry_cache = None
    svc._app_home = None

    svc.compile_mental_model("sess-1", "First do A.\nThen do B.\nAsk before risky edits.")

    mm_events = [e for e in events if isinstance(e, MentalModelCompiledEvent)]
    assert len(mm_events) == 1
    evt = mm_events[0]
    assert evt.session_id == "sess-1"
    assert evt.clause_count == 3
    assert evt.risk_posture == "balanced"
