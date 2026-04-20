"""Tests for Session.strategy_spec field (A1)."""

from __future__ import annotations

from datetime import UTC, datetime

from citnega.packages.protocol.models.sessions import Session, SessionConfig
from citnega.packages.strategy.models import MentalModelClause, MentalModelClauseType, StrategySpec


def _make_config() -> SessionConfig:
    return SessionConfig(
        session_id="s1",
        name="test",
        framework="adk",
        default_model_id="test-model",
    )


def test_strategy_spec_defaults_to_none() -> None:
    session = Session(
        config=_make_config(),
        created_at=datetime.now(UTC),
        last_active_at=datetime.now(UTC),
    )
    assert session.strategy_spec is None


def test_strategy_spec_accepts_valid_spec() -> None:
    spec = StrategySpec(mode="plan", risk_posture="conservative")
    session = Session(
        config=_make_config(),
        created_at=datetime.now(UTC),
        last_active_at=datetime.now(UTC),
        strategy_spec=spec,
    )
    assert session.strategy_spec is not None
    assert session.strategy_spec.mode == "plan"
    assert session.strategy_spec.risk_posture == "conservative"


def test_strategy_spec_model_copy_round_trip() -> None:
    session = Session(
        config=_make_config(),
        created_at=datetime.now(UTC),
        last_active_at=datetime.now(UTC),
    )
    spec = StrategySpec(
        mental_model_clauses=[
            MentalModelClause(
                clause_type=MentalModelClauseType.RISK,
                text="Always approve high-risk actions",
            )
        ]
    )
    updated = session.model_copy(update={"strategy_spec": spec})
    assert updated.strategy_spec is not None
    assert len(updated.strategy_spec.mental_model_clauses) == 1
    assert session.strategy_spec is None  # original unchanged


def test_session_serializes_with_strategy_spec() -> None:
    spec = StrategySpec(mode="code", parallelism_budget=3)
    session = Session(
        config=_make_config(),
        created_at=datetime.now(UTC),
        last_active_at=datetime.now(UTC),
        strategy_spec=spec,
    )
    data = session.model_dump()
    assert data["strategy_spec"]["mode"] == "code"
    assert data["strategy_spec"]["parallelism_budget"] == 3


def test_session_round_trips_via_model_validate() -> None:
    spec = StrategySpec(mode="research")
    session = Session(
        config=_make_config(),
        created_at=datetime.now(UTC),
        last_active_at=datetime.now(UTC),
        strategy_spec=spec,
    )
    restored = Session.model_validate(session.model_dump())
    assert restored.strategy_spec is not None
    assert restored.strategy_spec.mode == "research"
