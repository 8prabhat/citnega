"""Integration tests: MentalModelLLMCompiler and negation handling."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_fallback_used_when_no_gateway() -> None:
    from citnega.packages.strategy.mental_models_llm import MentalModelLLMCompiler

    compiler = MentalModelLLMCompiler(model_gateway=None)
    spec = await compiler.compile("## Think step-by-step\nAlways break down problems.\nNever skip validation.")
    assert spec is not None


@pytest.mark.asyncio
async def test_compiler_returns_spec_with_no_empty_source() -> None:
    from citnega.packages.strategy.mental_models_llm import MentalModelLLMCompiler

    compiler = MentalModelLLMCompiler(model_gateway=None)
    spec = await compiler.compile("")
    assert spec is not None


def test_mental_model_spec_has_negations_field() -> None:
    from citnega.packages.strategy.models import MentalModelSpec

    spec = MentalModelSpec(negations=["never do X", "avoid Y"])
    assert spec.negations == ["never do X", "avoid Y"]


def test_mental_model_spec_negations_defaults_empty() -> None:
    from citnega.packages.strategy.models import MentalModelSpec

    spec = MentalModelSpec()
    assert spec.negations == []


def test_strategy_spec_has_mental_model_clauses() -> None:
    from citnega.packages.strategy.models import StrategySpec

    spec = StrategySpec()
    assert hasattr(spec, "mental_model_clauses")
    assert spec.mental_model_clauses == []
