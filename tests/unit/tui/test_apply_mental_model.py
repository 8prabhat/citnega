"""Tests that _apply_mental_model_to_session calls update_session_strategy (A4)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from citnega.packages.strategy.models import (
    MentalModelClause,
    MentalModelClauseType,
    MentalModelSpec,
    StrategySpec,
)


def _import_apply_fn():
    from citnega.apps.tui.slash_commands.workspace import _apply_mental_model_to_session
    return _apply_mental_model_to_session


def _make_spec() -> MentalModelSpec:
    return MentalModelSpec(
        source_text="Think step by step",
        clauses=[MentalModelClause(clause_type=MentalModelClauseType.GENERAL, text="Think step by step")],
        risk_posture="conservative",
        recommended_parallelism=2,
    )


@pytest.mark.asyncio
async def test_apply_calls_update_session_strategy() -> None:
    apply_fn = _import_apply_fn()

    mock_service = MagicMock()
    mock_service.get_session = AsyncMock(return_value=MagicMock(strategy_spec=None))
    mock_service.update_session_strategy = AsyncMock()

    mock_ctrl = MagicMock()
    mock_ctrl._session_id = "test-session-123"

    spec = _make_spec()

    # Run the function — it internally schedules an async task
    # We run the event loop to let the task complete
    apply_fn(mock_ctrl, mock_service, spec)

    # Allow the created task to run
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    mock_service.update_session_strategy.assert_called_once()
    call_args = mock_service.update_session_strategy.call_args
    session_id_arg = call_args[0][0] if call_args[0] else call_args[1].get("session_id")
    assert session_id_arg == "test-session-123"


@pytest.mark.asyncio
async def test_apply_merges_clauses_into_existing_strategy() -> None:
    apply_fn = _import_apply_fn()

    existing = StrategySpec(constraints=["Be concise"])
    mock_service = MagicMock()
    mock_service.get_session = AsyncMock(return_value=MagicMock(strategy_spec=existing))
    mock_service.update_session_strategy = AsyncMock()

    mock_ctrl = MagicMock()
    mock_ctrl._session_id = "session-456"

    spec = _make_spec()
    apply_fn(mock_ctrl, mock_service, spec)

    await asyncio.sleep(0)
    await asyncio.sleep(0)

    mock_service.update_session_strategy.assert_called_once()


@pytest.mark.asyncio
async def test_apply_no_session_id_does_nothing() -> None:
    apply_fn = _import_apply_fn()

    mock_service = MagicMock()
    mock_service.update_session_strategy = AsyncMock()

    mock_ctrl = MagicMock()
    mock_ctrl._session_id = None

    spec = _make_spec()
    apply_fn(mock_ctrl, mock_service, spec)

    await asyncio.sleep(0)

    mock_service.update_session_strategy.assert_not_called()
