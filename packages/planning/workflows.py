from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from citnega.packages.planning.models import WorkflowTemplate


def load_workflow_template(path: Path) -> WorkflowTemplate:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    data.setdefault("name", path.stem)
    data.setdefault("source_path", str(path))
    return WorkflowTemplate.model_validate(data)


def load_workflow_templates(workflows_root: Path) -> dict[str, WorkflowTemplate]:
    if not workflows_root.exists():
        return {}
    templates: dict[str, WorkflowTemplate] = {}
    for path in sorted(list(workflows_root.glob("*.yaml")) + list(workflows_root.glob("*.yml"))):
        template = load_workflow_template(path)
        templates[template.name] = template
    return templates


def render_template_value(value: Any, variables: dict[str, Any]) -> Any:
    if isinstance(value, str):
        return value.format_map(dict(variables))
    if isinstance(value, list):
        return [render_template_value(item, variables) for item in value]
    if isinstance(value, dict):
        return {key: render_template_value(item, variables) for key, item in value.items()}
    return value
