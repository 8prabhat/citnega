"""Unit tests for workspace/scaffold.py"""

from __future__ import annotations

import asyncio

import pytest

from citnega.packages.workspace.scaffold import ScaffoldGenerator
from citnega.packages.workspace.templates import ScaffoldSpec


def _tool_spec(**kwargs) -> ScaffoldSpec:
    return ScaffoldSpec(
        kind="tool",
        class_name=kwargs.pop("class_name", "TestTool"),
        name=kwargs.pop("name", "test_tool"),
        description=kwargs.pop("description", "A test tool"),
        **kwargs,
    )


class TestScaffoldGeneratorFallback:
    def test_no_gateway_uses_fallback(self) -> None:
        gen = ScaffoldGenerator(model_gateway=None)
        source = asyncio.run(gen.generate(_tool_spec()))
        assert "TestTool" in source

    def test_fallback_tool_valid_python(self) -> None:
        import ast

        gen = ScaffoldGenerator(model_gateway=None)
        source = asyncio.run(gen.generate(_tool_spec()))
        ast.parse(source)  # no exception

    def test_fallback_agent(self) -> None:
        spec = ScaffoldSpec(kind="agent", class_name="MyAgent", name="my_agent", description="test")
        gen = ScaffoldGenerator(model_gateway=None)
        source = asyncio.run(gen.generate(spec))
        assert "MyAgent" in source

    def test_fallback_workflow(self) -> None:
        spec = ScaffoldSpec(
            kind="workflow", class_name="MyWorkflow", name="my_workflow", description="test"
        )
        gen = ScaffoldGenerator(model_gateway=None)
        source = asyncio.run(gen.generate(spec))
        assert "MyWorkflow" in source

    def test_unknown_kind_raises(self) -> None:
        spec = ScaffoldSpec(kind="unknown", class_name="X", name="x", description="x")
        gen = ScaffoldGenerator(model_gateway=None)
        with pytest.raises(ValueError, match="Unknown scaffold kind"):
            asyncio.run(gen.generate(spec))


class TestScaffoldGeneratorLLM:
    def test_fallback_on_gateway_error(self) -> None:
        """If the gateway raises, we fall back to templates silently."""

        class BrokenGateway:
            async def generate(self, req):
                raise RuntimeError("network down")

        gen = ScaffoldGenerator(model_gateway=BrokenGateway())
        source = asyncio.run(gen.generate(_tool_spec()))
        assert "TestTool" in source  # fallback was used

    def test_fence_stripping(self) -> None:
        """Verify that markdown fences are stripped from LLM output."""
        fenced = "```python\nclass Foo:\n    pass\n```"
        stripped = ScaffoldGenerator._strip_fences(fenced)
        assert stripped == "class Foo:\n    pass"

    def test_fence_stripping_no_fence(self) -> None:
        plain = "class Foo:\n    pass"
        assert ScaffoldGenerator._strip_fences(plain) == plain

    def test_llm_output_used_when_available(self) -> None:
        """If gateway succeeds, its output (stripped) is returned."""

        class FakeGateway:
            async def generate(self, req):
                class R:
                    content = "class GatewayTool:\n    pass\n"

                return R()

        gen = ScaffoldGenerator(model_gateway=FakeGateway())
        source = asyncio.run(gen.generate(_tool_spec(class_name="GatewayTool")))
        assert "GatewayTool" in source
