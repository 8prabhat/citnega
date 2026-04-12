"""Unit tests for workspace/templates.py"""

from __future__ import annotations

import ast

import pytest

from citnega.packages.workspace.templates import (
    FallbackTemplates,
    ScaffoldSpec,
    pascal_to_snake,
)


def _make_spec(kind: str, class_name: str = "", name: str = "", **kwargs) -> ScaffoldSpec:
    if not class_name:
        class_name = "Test" + kind.capitalize()
    if not name:
        name = "test_" + kind
    kwargs.setdefault("description", "A test callable.")
    return ScaffoldSpec(kind=kind, class_name=class_name, name=name, **kwargs)


class TestRenderTool:
    def test_parses_without_error(self) -> None:
        spec = _make_spec("tool", "MyTool", "my_tool")
        source = FallbackTemplates.render_tool(spec)
        ast.parse(source)  # raises SyntaxError if invalid

    def test_contains_class_name(self) -> None:
        spec = _make_spec("tool", "WebScraperTool", "web_scraper")
        source = FallbackTemplates.render_tool(spec)
        assert "class WebScraperTool" in source

    def test_name_attr_present(self) -> None:
        spec = _make_spec("tool", "MyTool", "my_tool")
        source = FallbackTemplates.render_tool(spec)
        assert "name          = 'my_tool'" in source or 'name          = "my_tool"' in source

    def test_description_attr_present(self) -> None:
        spec = _make_spec("tool", description="Does something useful")
        source = FallbackTemplates.render_tool(spec)
        assert "Does something useful" in source

    def test_parameters_rendered(self) -> None:
        spec = _make_spec(
            "tool",
            parameters=[{"name": "url", "type": "str", "description": "Target URL"}],
        )
        source = FallbackTemplates.render_tool(spec)
        assert "url:" in source or "url: str" in source

    def test_no_parameters_uses_default(self) -> None:
        spec = _make_spec("tool", parameters=[])
        source = FallbackTemplates.render_tool(spec)
        # Should still produce a valid module
        ast.parse(source)

    def test_callable_type_is_tool(self) -> None:
        spec = _make_spec("tool")
        source = FallbackTemplates.render_tool(spec)
        assert "CallableType.TOOL" in source


class TestRenderAgent:
    def test_parses_without_error(self) -> None:
        spec = _make_spec("agent", "ResearchAgent", "research_agent")
        source = FallbackTemplates.render_agent(spec)
        ast.parse(source)

    def test_contains_class_name(self) -> None:
        spec = _make_spec("agent", "CodeReviewAgent", "code_review_agent")
        source = FallbackTemplates.render_agent(spec)
        assert "class CodeReviewAgent" in source

    def test_system_prompt_included(self) -> None:
        spec = _make_spec("agent", system_prompt="You are a careful reviewer.")
        source = FallbackTemplates.render_agent(spec)
        assert "You are a careful reviewer." in source

    def test_tool_whitelist_included(self) -> None:
        spec = _make_spec("agent", tool_whitelist=["fetch_url", "search_files"])
        source = FallbackTemplates.render_agent(spec)
        assert "fetch_url" in source
        assert "search_files" in source

    def test_callable_type_is_specialist(self) -> None:
        spec = _make_spec("agent")
        source = FallbackTemplates.render_agent(spec)
        assert "CallableType.SPECIALIST" in source


class TestRenderWorkflow:
    def test_parses_without_error(self) -> None:
        spec = _make_spec("workflow", "DataPipelineWorkflow", "data_pipeline_workflow")
        source = FallbackTemplates.render_workflow(spec)
        ast.parse(source)

    def test_contains_class_name(self) -> None:
        spec = _make_spec("workflow", "DataPipelineWorkflow", "data_pipeline_workflow")
        source = FallbackTemplates.render_workflow(spec)
        assert "class DataPipelineWorkflow" in source

    def test_sub_agents_in_whitelist(self) -> None:
        spec = _make_spec("workflow", sub_agents=["research_agent"], tool_whitelist=["fetch_url"])
        source = FallbackTemplates.render_workflow(spec)
        assert "research_agent" in source
        assert "fetch_url" in source


class TestPascalToSnake:
    @pytest.mark.parametrize(
        "pascal,expected",
        [
            ("WebScraperTool", "web_scraper_tool"),
            ("MySpecialistAgent", "my_specialist_agent"),
            ("DataPipelineWorkflow", "data_pipeline_workflow"),
            ("ABC", "abc"),
            ("simple", "simple"),
        ],
    )
    def test_conversion(self, pascal: str, expected: str) -> None:
        assert pascal_to_snake(pascal) == expected
