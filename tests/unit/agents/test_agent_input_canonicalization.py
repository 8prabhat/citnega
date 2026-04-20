"""Tests for AgentInput canonical task field and alias resolution (E3)."""

from __future__ import annotations

from citnega.packages.protocol.models.agent_input import AgentInput


def test_task_field_populated_directly() -> None:
    inp = AgentInput(task="do the thing")
    assert inp.task == "do the thing"


def test_query_alias_maps_to_task() -> None:
    inp = AgentInput(query="search for X")
    assert inp.task == "search for X"


def test_text_alias_maps_to_task() -> None:
    inp = AgentInput(text="summarize this")
    assert inp.task == "summarize this"


def test_goal_alias_maps_to_task() -> None:
    inp = AgentInput(goal="build a feature")
    assert inp.task == "build a feature"


def test_task_takes_precedence_over_aliases() -> None:
    inp = AgentInput(task="primary", query="secondary", goal="tertiary")
    assert inp.task == "primary"


def test_query_takes_precedence_over_text_and_goal() -> None:
    inp = AgentInput(query="from query", text="from text")
    assert inp.task == "from query"


def test_empty_input_produces_empty_task() -> None:
    inp = AgentInput()
    assert inp.task == ""


def test_model_validate_dict() -> None:
    inp = AgentInput.model_validate({"query": "hello"})
    assert inp.task == "hello"


def test_extra_fields_preserved() -> None:
    inp = AgentInput.model_validate({"task": "x", "context": "y"})
    assert inp.task == "x"
    assert inp.model_extra.get("context") == "y"
