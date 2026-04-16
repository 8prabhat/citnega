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
