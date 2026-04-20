"""E2E integration test for the nextgen pipeline: classify → compile → execute."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from citnega.packages.capabilities.models import (
    CapabilityDescriptor,
    CapabilityKind,
    CapabilityProvenance,
)
from citnega.packages.capabilities.registry import CapabilityRecord, CapabilityRegistry
from citnega.packages.execution.engine import ExecutionEngine
from citnega.packages.planning.classifier import TaskClassifier
from citnega.packages.planning.compiler import PlanCompiler
from citnega.packages.protocol.callables.context import CallContext
from citnega.packages.protocol.models.sessions import SessionConfig


def _make_context() -> CallContext:
    config = SessionConfig(
        session_id="test-session",
        name="Test Session",
        framework="direct",
        default_model_id="claude-opus-4",
    )
    return CallContext(
        session_id="test-session",
        run_id="test-run",
        turn_id="test-turn",
        session_config=config,
    )


def _make_registry() -> CapabilityRegistry:
    """Build a CapabilityRegistry with two stub capabilities."""
    registry = CapabilityRegistry()

    for cap_id, kind, name in [
        ("search_tool", CapabilityKind.TOOL, "Search"),
        ("summarise_agent", CapabilityKind.AGENT, "Summarise"),
    ]:
        descriptor = CapabilityDescriptor(
            capability_id=cap_id,
            kind=kind,
            display_name=name,
            description=f"Stub {name} capability for testing.",
            provenance=CapabilityProvenance(source="builtin"),
        )
        stub_runtime = MagicMock()
        stub_runtime.invoke = AsyncMock(return_value=MagicMock(output=MagicMock(result=f"{name} done")))
        record = CapabilityRecord(descriptor=descriptor, runtime_object=stub_runtime)
        registry.register(record)

    return registry


def test_task_classifier_classifies_simple_query():
    classifier = TaskClassifier()
    registry = _make_registry()
    result = classifier.classify("What is 2+2?", registry=registry)
    assert result.path in {"direct_answer", "specialist", "compiled_plan"}
    assert result.confidence >= 0.0
    # capability_id may be None for direct_answer path
    if result.path != "direct_answer":
        assert result.capability_id


def test_task_classifier_returns_confidence():
    classifier = TaskClassifier()
    result = classifier.classify("Research the history of Rome and write a summary")
    assert 0.0 <= result.confidence <= 1.0


def test_plan_compiler_produces_compiled_plan():
    compiler = PlanCompiler()
    plan = compiler.compile_goal(
        "Search for recent news and summarise",
        capability_id="summarise_agent",
    )
    assert plan.plan_id
    assert plan.objective == "Search for recent news and summarise"
    assert len(plan.steps) >= 1


@pytest.mark.asyncio
async def test_execution_engine_executes_single_step_plan():
    compiler = PlanCompiler()
    registry = _make_registry()
    engine = ExecutionEngine()
    context = _make_context()

    plan = compiler.compile_goal(
        "Summarise this document",
        capability_id="summarise_agent",
    )

    result = await engine.execute(plan, registry, context)
    assert result is not None


@pytest.mark.asyncio
async def test_classify_compile_execute_pipeline():
    """End-to-end: classify → compile → execute."""
    classifier = TaskClassifier()
    compiler = PlanCompiler()
    registry = _make_registry()
    engine = ExecutionEngine()
    context = _make_context()

    objective = "Search for data and summarise the results"
    classification = classifier.classify(objective, registry=registry)

    if classification.path == "direct_answer":
        # Direct answers don't need a plan — this is a valid fast path
        assert classification.confidence > 0
        return

    plan = compiler.compile_goal(
        objective,
        capability_id=classification.capability_id or "summarise_agent",
    )
    assert plan.steps

    result = await engine.execute(plan, registry, context)
    assert result is not None
