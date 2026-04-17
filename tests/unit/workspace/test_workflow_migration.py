from __future__ import annotations

from pathlib import Path

import yaml  # type: ignore[import-untyped]

from citnega.packages.workspace.workflow_migration import (
    migrate_python_workflows_to_templates,
)


def _legacy_workflow_source() -> str:
    return """
from pydantic import BaseModel, Field
from citnega.packages.agents.specialists._specialist_base import SpecialistBase, SpecialistOutput
from citnega.packages.protocol.callables.types import CallableType, CallablePolicy
from citnega.packages.protocol.callables.context import CallContext

class ReleaseWorkflowInput(BaseModel):
    objective: str = Field(description="objective")

class ReleaseWorkflow(SpecialistBase):
    name = "release_workflow"
    description = "Legacy release workflow."
    callable_type = CallableType.SPECIALIST
    input_schema = ReleaseWorkflowInput
    output_schema = SpecialistOutput
    policy = CallablePolicy(timeout_seconds=60.0)
    TOOL_WHITELIST = ["repo_map", "quality_gate", "qa_agent"]

    async def _execute(self, input: ReleaseWorkflowInput, context: CallContext) -> SpecialistOutput:
        return SpecialistOutput(response="ok")
"""


def test_migrates_python_workflow_to_yaml_template(tmp_path: Path) -> None:
    workflows_dir = tmp_path / "workflows"
    workflows_dir.mkdir(parents=True)
    (workflows_dir / "release_workflow.py").write_text(
        _legacy_workflow_source(),
        encoding="utf-8",
    )

    result = migrate_python_workflows_to_templates(workflows_dir)

    assert result.converted == [str(workflows_dir / "release_workflow.py")]
    target = workflows_dir / "release_workflow.yaml"
    assert target.exists()
    template = yaml.safe_load(target.read_text(encoding="utf-8"))
    assert template["name"] == "release_workflow"
    assert [step["capability_id"] for step in template["steps"]] == [
        "repo_map",
        "quality_gate",
        "qa_agent",
    ]


def test_skips_when_yaml_template_already_exists(tmp_path: Path) -> None:
    workflows_dir = tmp_path / "workflows"
    workflows_dir.mkdir(parents=True)
    py_file = workflows_dir / "release_workflow.py"
    py_file.write_text(_legacy_workflow_source(), encoding="utf-8")
    (workflows_dir / "release_workflow.yaml").write_text(
        "name: release_workflow\ndescription: existing\nsteps: []\n",
        encoding="utf-8",
    )

    result = migrate_python_workflows_to_templates(workflows_dir)

    assert result.converted == []
    assert result.skipped_existing_template == [str(py_file)]


def test_reports_parse_errors(tmp_path: Path) -> None:
    workflows_dir = tmp_path / "workflows"
    workflows_dir.mkdir(parents=True)
    py_file = workflows_dir / "broken_workflow.py"
    py_file.write_text("class BrokenWorkflow(\n", encoding="utf-8")

    result = migrate_python_workflows_to_templates(workflows_dir)

    assert result.converted == []
    assert len(result.errors) == 1
    assert str(py_file) in result.errors[0]
