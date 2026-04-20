from __future__ import annotations

from typing import TYPE_CHECKING, Any

from citnega.packages.strategy.models import (
    MentalModelClause,
    MentalModelClauseType,
    MentalModelSpec,
)

if TYPE_CHECKING:
    from citnega.packages.runtime.events.emitter import EventEmitter


def compile_mental_model(
    text: str,
    *,
    session_id: str = "",
    run_id: str = "",
    emitter: Any | None = None,
) -> MentalModelSpec:
    clauses: list[MentalModelClause] = []
    risk_posture = "balanced"
    recommended_parallelism = 1

    for raw_line in text.splitlines():
        line = raw_line.strip(" -\t")
        if not line:
            continue
        lowered = line.lower()
        clause_type = MentalModelClauseType.GENERAL
        if any(token in lowered for token in ("ask before", "confirm before", "approval")):
            clause_type = MentalModelClauseType.APPROVAL
        elif any(token in lowered for token in ("first", "then", "finally", "before", "after")):
            clause_type = MentalModelClauseType.ORDERING
        elif any(token in lowered for token in ("verify", "validate", "test", "check")):
            clause_type = MentalModelClauseType.VALIDATION
        elif "parallel" in lowered:
            clause_type = MentalModelClauseType.PARALLELISM
            if any(token in lowered for token in ("prefer", "use", "allow", "aggressive")):
                recommended_parallelism = 4
        elif any(token in lowered for token in ("conservative", "careful", "minimal risk")):
            clause_type = MentalModelClauseType.RISK
            risk_posture = "conservative"
        elif any(token in lowered for token in ("aggressive", "fast", "move quickly")):
            clause_type = MentalModelClauseType.RISK
            risk_posture = "aggressive"
        clauses.append(MentalModelClause(clause_type=clause_type, text=line))

    spec = MentalModelSpec(
        source_text=text,
        clauses=clauses,
        recommended_parallelism=recommended_parallelism,
        risk_posture=risk_posture,
    )
    if emitter is not None:
        try:
            from citnega.packages.protocol.events.planning import MentalModelCompiledEvent

            emitter.emit(
                MentalModelCompiledEvent(
                    session_id=session_id,
                    run_id=run_id,
                    clause_count=len(clauses),
                    risk_posture=risk_posture,
                    recommended_parallelism=recommended_parallelism,
                )
            )
        except Exception:
            pass
    return spec
