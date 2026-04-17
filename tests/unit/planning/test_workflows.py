from __future__ import annotations

from citnega.packages.planning import PlanCompiler, load_workflow_templates, render_template_value
from citnega.packages.strategy import StrategySpec


def test_load_workflow_templates_and_render_variables(tmp_path):
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "release.yaml").write_text(
        """
name: release_readiness
description: Release review workflow
max_parallelism: 2
steps:
  - step_id: repo_map
    capability_id: repo_map
    task: "Map {target}"
  - step_id: qa
    capability_id: qa_agent
    depends_on: [repo_map]
    args:
      goal: "Review {target}"
""",
        encoding="utf-8",
    )

    templates = load_workflow_templates(workflows)
    plan = PlanCompiler().compile_workflow(
        templates["release_readiness"],
        variables={"target": "service"},
        strategy=StrategySpec(mode="review", objective="release"),
        objective="Release readiness",
    )

    assert plan.generated_from == "workflow:release_readiness"
    assert plan.max_parallelism == 2
    assert plan.steps[0].task == "Map service"
    assert plan.steps[1].args["goal"] == "Review service"


def test_render_template_value_recurses():
    value = {
        "goal": "Review {target}",
        "items": ["{target}", {"path": "/tmp/{target}"}],
    }

    rendered = render_template_value(value, {"target": "repo"})

    assert rendered == {"goal": "Review repo", "items": ["repo", {"path": "/tmp/repo"}]}
