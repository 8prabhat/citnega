from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import traceback
from typing import Protocol

from citnega.packages.capabilities.diagnostics import CapabilityDiagnostics
from citnega.packages.capabilities.models import (
    CapabilityDescriptor,
    CapabilityExecutionTraits,
    CapabilityKind,
    CapabilityProvenance,
    CapabilityRecord,
    SideEffectLevel,
)
from citnega.packages.planning.models import WorkflowTemplate
from citnega.packages.planning.workflows import load_workflow_template
from citnega.packages.protocol.callables.types import CallableMetadata
from citnega.packages.strategy.mental_models import compile_mental_model
from citnega.packages.strategy.models import SkillDescriptor
from citnega.packages.strategy.skills import load_skill


class _MetadataCallable(Protocol):
    def get_metadata(self) -> CallableMetadata: ...


def _side_effect_level(name: str, *, network_allowed: bool, requires_approval: bool) -> SideEffectLevel:
    lowered = name.lower()
    if network_allowed:
        return SideEffectLevel.NETWORK
    if any(token in lowered for token in ("write", "edit", "delete", "commit")):
        return SideEffectLevel.WRITE
    if any(token in lowered for token in ("shell", "git", "exec")) or requires_approval:
        return SideEffectLevel.SHELL
    if any(token in lowered for token in ("read", "search", "list", "map", "fetch")):
        return SideEffectLevel.READ
    return SideEffectLevel.NONE


def callable_to_descriptor(
    callable_obj: _MetadataCallable,
    *,
    source: str,
    path: str = "",
) -> CapabilityDescriptor:
    metadata = callable_obj.get_metadata()
    callable_type = str(metadata.callable_type)
    kind = CapabilityKind.TOOL if callable_type == "tool" else CapabilityKind.AGENT
    requires_approval = bool(metadata.policy.requires_approval)
    network_allowed = bool(metadata.policy.network_allowed)
    execution_traits = CapabilityExecutionTraits(
        parallel_safe=(not requires_approval and not network_allowed and kind == CapabilityKind.TOOL),
        side_effect_level=_side_effect_level(
            metadata.name,
            network_allowed=network_allowed,
            requires_approval=requires_approval,
        ),
        resource_scope=("workspace" if requires_approval else metadata.name),
        requires_exclusive_workspace=requires_approval,
        supports_remote_execution=(not requires_approval and kind == CapabilityKind.TOOL),
    )
    return CapabilityDescriptor(
        capability_id=metadata.name,
        kind=kind,
        display_name=metadata.name,
        description=metadata.description,
        input_schema=metadata.input_schema_json,
        output_schema=metadata.output_schema_json,
        policy=metadata.policy,
        execution_traits=execution_traits,
        supported_modes=["chat", "plan", "explore", "research", "code", "review", "operate"],
        tags=[callable_type],
        provenance=CapabilityProvenance(source=source, path=path),
    )


class BuiltinCapabilityProvider:
    def load(
        self,
        callables: Mapping[str, _MetadataCallable],
    ) -> tuple[list[CapabilityRecord], CapabilityDiagnostics]:
        diagnostics = CapabilityDiagnostics()
        records: list[CapabilityRecord] = []
        for name, callable_obj in sorted(callables.items()):
            try:
                descriptor = callable_to_descriptor(callable_obj, source="builtin")
                records.append(CapabilityRecord(descriptor=descriptor, runtime_object=callable_obj))
            except Exception as exc:
                diagnostics.add_failure(
                    name,
                    source="builtin",
                    path="<runtime>",
                    error="".join(traceback.format_exception_only(type(exc), exc)).strip(),
                    required=True,
                )
        return records, diagnostics


class WorkspaceCapabilityProvider:
    def __init__(self, workspace_root: Path | None) -> None:
        self._workspace_root = workspace_root

    def load(self) -> tuple[list[CapabilityRecord], CapabilityDiagnostics]:
        diagnostics = CapabilityDiagnostics()
        records: list[CapabilityRecord] = []
        if self._workspace_root is None or not self._workspace_root.exists():
            return records, diagnostics

        skills_root = self._workspace_root / "skills"
        workflows_root = self._workspace_root / "workflows"

        for skill_file in sorted(skills_root.glob("*/SKILL.md")):
            try:
                skill = load_skill(skill_file)
                records.append(
                    CapabilityRecord(
                        descriptor=self._skill_descriptor(skill),
                        runtime_object=skill,
                    )
                )
            except Exception as exc:
                diagnostics.add_failure(
                    skill_file.parent.name,
                    source="workspace",
                    path=str(skill_file),
                    error="".join(traceback.format_exception_only(type(exc), exc)).strip(),
                )

        workflow_files = sorted(list(workflows_root.glob("*.yaml")) + list(workflows_root.glob("*.yml")))
        for workflow_file in workflow_files:
            try:
                template = load_workflow_template(workflow_file)
                records.append(
                    CapabilityRecord(
                        descriptor=self._workflow_descriptor(template),
                        runtime_object=template,
                    )
                )
            except Exception as exc:
                diagnostics.add_failure(
                    workflow_file.stem,
                    source="workspace",
                    path=str(workflow_file),
                    error="".join(traceback.format_exception_only(type(exc), exc)).strip(),
                )

        return records, diagnostics

    @staticmethod
    def _skill_descriptor(skill: SkillDescriptor) -> CapabilityDescriptor:
        return CapabilityDescriptor(
            capability_id=f"skill:{skill.name}",
            kind=CapabilityKind.SKILL,
            display_name=skill.name,
            description=skill.description,
            supported_modes=skill.supported_modes,
            tags=skill.tags,
            provenance=CapabilityProvenance(source="workspace", path=skill.content_path),
        )

    @staticmethod
    def _workflow_descriptor(template: WorkflowTemplate) -> CapabilityDescriptor:
        return CapabilityDescriptor(
            capability_id=f"workflow_template:{template.name}",
            kind=CapabilityKind.WORKFLOW_TEMPLATE,
            display_name=template.name,
            description=template.description,
            input_schema={"variables": template.variables},
            supported_modes=template.supported_modes,
            tags=template.tags,
            provenance=CapabilityProvenance(source="workspace", path=template.source_path),
        )


class BuiltinSkillProvider:
    """Loads the 5 built-in skills shipped with citnega into the CapabilityRegistry."""

    def load(self) -> tuple[list[CapabilityRecord], CapabilityDiagnostics]:
        from citnega.packages.skills.builtins import BUILTIN_SKILLS

        diagnostics = CapabilityDiagnostics()
        records: list[CapabilityRecord] = []
        for skill_dict in BUILTIN_SKILLS:
            try:
                skill = SkillDescriptor(
                    name=skill_dict["name"],
                    description=skill_dict.get("description", ""),
                    content_path="<builtin>",
                    triggers=skill_dict.get("triggers", []),
                    preferred_tools=skill_dict.get("preferred_tools", []),
                    preferred_agents=skill_dict.get("preferred_agents", []),
                    supported_modes=skill_dict.get("supported_modes", []),
                    tags=skill_dict.get("tags", []),
                    body=skill_dict.get("body", ""),
                )
                descriptor = CapabilityDescriptor(
                    capability_id=f"skill:{skill.name}",
                    kind=CapabilityKind.SKILL,
                    display_name=skill.name,
                    description=skill.description,
                    supported_modes=skill.supported_modes,
                    tags=skill.tags,
                    provenance=CapabilityProvenance(source="builtin", path="<builtin>"),
                )
                records.append(CapabilityRecord(descriptor=descriptor, runtime_object=skill))
            except Exception as exc:
                diagnostics.add_failure(
                    skill_dict.get("name", "<unknown>"),
                    source="builtin",
                    path="<builtin>",
                    error="".join(traceback.format_exception_only(type(exc), exc)).strip(),
                )
        return records, diagnostics


class MentalModelCapabilityProvider:
    """
    Loads compiled MentalModelSpec objects from ``{workspace_root}/mental_models/*.md``.

    Each .md file is compiled via ``compile_mental_model()`` and registered as a
    CapabilityRecord so the runner can inject the clauses into the system prompt.
    """

    def __init__(self, workspace_root: Path | None) -> None:
        self._workspace_root = workspace_root

    def load(self) -> tuple[list[CapabilityRecord], CapabilityDiagnostics]:
        diagnostics = CapabilityDiagnostics()
        records: list[CapabilityRecord] = []
        if self._workspace_root is None or not self._workspace_root.exists():
            return records, diagnostics

        mm_root = self._workspace_root / "mental_models"
        if not mm_root.exists():
            return records, diagnostics

        for md_file in sorted(mm_root.glob("*.md")):
            try:
                spec = compile_mental_model(md_file.read_text(encoding="utf-8"))
                descriptor = CapabilityDescriptor(
                    capability_id=f"mental_model:{md_file.stem}",
                    kind=CapabilityKind.SKILL,  # reuse SKILL kind — no dedicated kind needed
                    display_name=md_file.stem,
                    description=f"Mental model: {md_file.stem}",
                    supported_modes=["chat", "plan", "explore", "research", "code", "review", "operate"],
                    provenance=CapabilityProvenance(source="workspace", path=str(md_file)),
                )
                records.append(CapabilityRecord(descriptor=descriptor, runtime_object=spec))
            except Exception as exc:
                diagnostics.add_failure(
                    md_file.stem,
                    source="workspace",
                    path=str(md_file),
                    error="".join(traceback.format_exception_only(type(exc), exc)).strip(),
                )

        return records, diagnostics
