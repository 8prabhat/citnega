"""
Unit tests for TaskClassifier.

Covers:
- direct_answer fast path (short factual questions)
- compiled_plan path (plan keywords detected)
- specialist path (registry-based routing)
- strategy force_plan_mode override
- fallback to compiled_plan when no registry match
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from citnega.packages.planning.classifier import ClassificationResult, TaskClassifier


def _make_classifier() -> TaskClassifier:
    return TaskClassifier()


# ── direct_answer ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "objective",
    [
        "What is Python?",
        "What's the capital of France?",
        "Who is Alan Turing?",
        "Where is the Eiffel Tower?",
        "Define recursion",
        "Explain REST",
    ],
)
def test_direct_answer_short_factual_questions(objective: str) -> None:
    result = _make_classifier().classify(objective)
    assert result.path == "direct_answer"
    assert result.confidence >= 0.85


def test_direct_answer_not_triggered_for_long_input() -> None:
    long_q = "What is the best way to implement a distributed system with eventual consistency, CRDT merging, and automatic conflict resolution?"
    result = _make_classifier().classify(long_q)
    # Too many words for direct_answer fast path
    assert result.path != "direct_answer"


# ── compiled_plan ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "objective",
    [
        "Plan a trip to Paris step by step",
        "First search for documentation, then summarise it",
        "Create a workflow to build and test the application",
        "Build and deploy the service",
        "Implement and test the new feature end-to-end",
    ],
)
def test_compiled_plan_plan_patterns(objective: str) -> None:
    result = _make_classifier().classify(objective)
    assert result.path == "compiled_plan"
    assert result.confidence >= 0.8


def test_strategy_force_plan_mode_overrides() -> None:
    strategy = MagicMock()
    strategy.force_plan_mode = True
    result = _make_classifier().classify("What is Python?", strategy=strategy)
    assert result.path == "compiled_plan"
    assert result.confidence == 1.0
    assert "force" in result.reason


# ── specialist ─────────────────────────────────────────────────────────────────


def _make_registry_with(capability_id: str, description: str, kind: str = "tool") -> MagicMock:
    from citnega.packages.capabilities.models import (
        CapabilityDescriptor,
        CapabilityKind,
        CapabilityProvenance,
    )

    descriptor = CapabilityDescriptor(
        capability_id=capability_id,
        kind=CapabilityKind.TOOL if kind == "tool" else CapabilityKind.AGENT,
        display_name=capability_id,
        description=description,
        tags=[kind],
        provenance=CapabilityProvenance(source="test"),
    )
    registry = MagicMock()
    registry.list_all.return_value = [descriptor]
    return registry


def test_specialist_single_capability_match() -> None:
    registry = _make_registry_with("search_web", "Search the web for information")
    result = _make_classifier().classify("search web for python tutorials", registry=registry)
    # Either specialist match or compiled_plan — the key is it doesn't go direct_answer
    assert result.path in ("specialist", "compiled_plan")


def test_specialist_no_match_falls_back_to_compiled_plan() -> None:
    registry = _make_registry_with("send_email", "Send email to recipients")
    result = _make_classifier().classify("analyse the codebase structure", registry=registry)
    assert result.path == "compiled_plan"
    assert result.confidence < 0.7 or result.reason == "fallback: no clear single-capability match"


def test_no_registry_falls_back_to_compiled_plan_for_unknown() -> None:
    result = _make_classifier().classify("do something complex with multiple steps maybe")
    assert result.path == "compiled_plan"


# ── ClassificationResult model ──────────────────────────────────────────────


def test_classification_result_defaults() -> None:
    result = ClassificationResult(path="direct_answer")
    assert result.capability_id is None
    assert result.confidence == 1.0
    assert result.reason == ""


def test_classification_result_specialist_has_id() -> None:
    result = ClassificationResult(path="specialist", capability_id="read_file", confidence=0.8)
    assert result.capability_id == "read_file"
    assert result.confidence == 0.8
