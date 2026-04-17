from __future__ import annotations

from citnega.packages.capabilities import (
    CapabilityKind,
    CapabilityRegistry,
    WorkspaceCapabilityProvider,
)


def test_workspace_provider_loads_skills_and_workflow_templates(tmp_path):
    workspace = tmp_path / "workfolder"
    (workspace / "skills" / "release").mkdir(parents=True)
    (workspace / "workflows").mkdir(parents=True)
    (workspace / "skills" / "release" / "SKILL.md").write_text(
        "---\nname: release\ndescription: Release skill\n---\nUse it.",
        encoding="utf-8",
    )
    (workspace / "workflows" / "release.yaml").write_text(
        "name: release\ndescription: Release workflow\nsteps: []\n",
        encoding="utf-8",
    )

    records, diagnostics = WorkspaceCapabilityProvider(workspace).load()
    registry = CapabilityRegistry()
    registry.register_many(records)

    assert not diagnostics.failures
    assert sorted(item.capability_id for item in registry.list_all()) == [
        "skill:release",
        "workflow_template:release",
    ]
    assert [item.kind for item in registry.list_by_kind(CapabilityKind.SKILL)] == [CapabilityKind.SKILL]


def test_workspace_provider_reports_file_level_diagnostics(tmp_path):
    workspace = tmp_path / "workfolder"
    (workspace / "skills" / "valid").mkdir(parents=True)
    (workspace / "skills" / "invalid").mkdir(parents=True)
    (workspace / "workflows").mkdir(parents=True)
    (workspace / "skills" / "valid" / "SKILL.md").write_text(
        "---\nname: valid\ndescription: Valid skill\n---\nBody",
        encoding="utf-8",
    )
    (workspace / "skills" / "invalid" / "SKILL.md").write_text(
        "---\nname: invalid\nunexpected_field: true\n---\nBody",
        encoding="utf-8",
    )
    (workspace / "workflows" / "valid.yaml").write_text(
        "name: valid\ndescription: Valid workflow\nsteps: []\n",
        encoding="utf-8",
    )
    (workspace / "workflows" / "broken.yaml").write_text(
        "name: broken\ndescription: broken\nsteps: [this-is-not-a-dict]\n",
        encoding="utf-8",
    )

    records, diagnostics = WorkspaceCapabilityProvider(workspace).load()
    registry = CapabilityRegistry()
    registry.register_many(records)

    assert sorted(item.capability_id for item in registry.list_all()) == [
        "skill:valid",
        "workflow_template:valid",
    ]
    assert len(diagnostics.failures) == 2
    failure_paths = sorted(f.path for f in diagnostics.failures)
    assert str(workspace / "skills" / "invalid" / "SKILL.md") in failure_paths
    assert str(workspace / "workflows" / "broken.yaml") in failure_paths
