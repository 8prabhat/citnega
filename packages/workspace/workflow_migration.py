"""Utilities for migrating legacy Python workflows into YAML templates."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from citnega.packages.workspace.templates import pascal_to_snake


@dataclass(slots=True)
class WorkflowMigrationResult:
    converted: list[str] = field(default_factory=list)
    skipped_existing_template: list[str] = field(default_factory=list)
    skipped_no_workflow_class: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, list[str]]:
        return {
            "converted": self.converted,
            "skipped_existing_template": self.skipped_existing_template,
            "skipped_no_workflow_class": self.skipped_no_workflow_class,
            "errors": self.errors,
        }


@dataclass(slots=True)
class _WorkflowMetadata:
    workflow_name: str
    description: str
    capabilities: list[str]


def migrate_python_workflows_to_templates(workflows_dir: Path) -> WorkflowMigrationResult:
    """
    Convert legacy ``workflows/*.py`` modules into ``*.yaml`` templates.

    Existing YAML templates are never overwritten.
    """
    result = WorkflowMigrationResult()
    if not workflows_dir.exists():
        return result

    for py_file in sorted(workflows_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        target = py_file.with_suffix(".yaml")
        if target.exists():
            result.skipped_existing_template.append(str(py_file))
            continue
        try:
            metadata = _extract_workflow_metadata(py_file)
            if metadata is None:
                result.skipped_no_workflow_class.append(str(py_file))
                continue
            template = _render_template(metadata)
            target.write_text(
                yaml.safe_dump(template, sort_keys=False, allow_unicode=False),
                encoding="utf-8",
            )
            result.converted.append(str(py_file))
        except Exception as exc:
            result.errors.append(f"{py_file}: {exc}")
    return result


def _extract_workflow_metadata(path: Path) -> _WorkflowMetadata | None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        name_value = ""
        description_value = ""
        whitelist: list[str] = []
        for statement in node.body:
            if not isinstance(statement, ast.Assign):
                continue
            for target in statement.targets:
                if not isinstance(target, ast.Name):
                    continue
                if target.id == "name":
                    parsed = _literal_string(statement.value)
                    if parsed:
                        name_value = parsed
                elif target.id == "description":
                    parsed = _literal_string(statement.value)
                    if parsed:
                        description_value = parsed
                elif target.id == "TOOL_WHITELIST":
                    whitelist = _literal_str_list(statement.value)
        workflow_name = name_value or pascal_to_snake(node.name)
        if not workflow_name.endswith("_workflow"):
            continue
        capabilities = [item for item in whitelist if item]
        if not capabilities:
            capabilities = ["conversation_agent"]
        description = description_value or f"Migrated workflow from {path.name}"
        return _WorkflowMetadata(
            workflow_name=workflow_name,
            description=description,
            capabilities=list(dict.fromkeys(capabilities)),
        )
    return None


def _literal_string(node: ast.AST) -> str:
    value = ast.literal_eval(node)
    if isinstance(value, str):
        return value.strip()
    return ""


def _literal_str_list(node: ast.AST) -> list[str]:
    value = ast.literal_eval(node)
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
    return out


def _render_template(metadata: _WorkflowMetadata) -> dict[str, object]:
    steps: list[dict[str, object]] = []
    previous_step = ""
    for idx, capability in enumerate(metadata.capabilities, start=1):
        step_id = f"step{idx}_{capability.replace('-', '_')}"
        step = {
            "step_id": step_id,
            "capability_id": capability,
            "task": "Execute {objective}",
            "depends_on": [previous_step] if previous_step else [],
            "can_run_in_parallel": False,
            "execution_target": "local",
        }
        steps.append(step)
        previous_step = step_id
    return {
        "name": metadata.workflow_name,
        "description": metadata.description,
        "variables": {"objective": "High-level objective provided at compile time."},
        "supported_modes": ["plan", "code", "explore", "research", "review", "operate"],
        "max_parallelism": 1,
        "steps": steps,
    }

