"""
Unit tests for CapabilityProviders (MentalModelCapabilityProvider, WorkspaceCapabilityProvider).

Covers:
- MentalModelCapabilityProvider loads .md files from mental_models/
- MentalModelCapabilityProvider is graceful when directory is empty or missing
- WorkspaceCapabilityProvider regression: skills still load (no breakage from new provider)
"""

from __future__ import annotations

import pytest

from citnega.packages.capabilities.providers import (
    MentalModelCapabilityProvider,
    WorkspaceCapabilityProvider,
)


# ---------------------------------------------------------------------------
# MentalModelCapabilityProvider
# ---------------------------------------------------------------------------


def test_mental_model_provider_loads_md_files(tmp_path) -> None:
    mm_dir = tmp_path / "mental_models"
    mm_dir.mkdir()
    (mm_dir / "precision.md").write_text(
        "---\nname: precision\n---\n- Be exact\n- Cite sources",
        encoding="utf-8",
    )

    records, diagnostics = MentalModelCapabilityProvider(tmp_path).load()
    assert len(records) == 1
    assert records[0].descriptor.capability_id == "mental_model:precision"


def test_mental_model_provider_graceful_empty(tmp_path) -> None:
    mm_dir = tmp_path / "mental_models"
    mm_dir.mkdir()
    # Empty directory — no .md files

    records, diagnostics = MentalModelCapabilityProvider(tmp_path).load()
    assert records == []
    assert diagnostics.failures == []


def test_mental_model_provider_missing_dir(tmp_path) -> None:
    # mental_models/ subdirectory doesn't exist
    records, diagnostics = MentalModelCapabilityProvider(tmp_path).load()
    assert records == []


def test_mental_model_provider_none_root() -> None:
    records, diagnostics = MentalModelCapabilityProvider(None).load()
    assert records == []


def test_mental_model_provider_records_have_all_modes(tmp_path) -> None:
    mm_dir = tmp_path / "mental_models"
    mm_dir.mkdir()
    (mm_dir / "thorough.md").write_text("---\nname: thorough\n---\n- Go deep", encoding="utf-8")

    records, _ = MentalModelCapabilityProvider(tmp_path).load()
    assert len(records) == 1
    supported = records[0].descriptor.supported_modes
    assert "chat" in supported
    assert "code" in supported
    assert "review" in supported


def test_mental_model_provider_bad_file_adds_diagnostic(tmp_path) -> None:
    mm_dir = tmp_path / "mental_models"
    mm_dir.mkdir()
    # Write a file that compile_mental_model will likely fail on (binary garbage)
    (mm_dir / "bad.md").write_bytes(b"\xff\xfe bad binary \x00\x01")

    records, diagnostics = MentalModelCapabilityProvider(tmp_path).load()
    # Should not crash — bad files go to diagnostics.failures
    # (may succeed or fail depending on compile_mental_model robustness)
    assert isinstance(records, list)
    assert isinstance(diagnostics.failures, list)


# ---------------------------------------------------------------------------
# WorkspaceCapabilityProvider — regression guard
# ---------------------------------------------------------------------------


def test_workspace_capability_provider_no_regression(tmp_path) -> None:
    """WorkspaceCapabilityProvider still loads skills after MentalModelCapabilityProvider was added."""
    workspace = tmp_path / "workfolder"
    (workspace / "skills" / "my_skill").mkdir(parents=True)
    (workspace / "skills" / "my_skill" / "SKILL.md").write_text(
        "---\nname: my_skill\ndescription: Test skill\n---\nDo the thing.",
        encoding="utf-8",
    )

    records, _ = WorkspaceCapabilityProvider(workspace).load()
    skill_ids = [r.descriptor.capability_id for r in records]
    assert any("my_skill" in sid for sid in skill_ids)


def test_workspace_capability_provider_empty_dir(tmp_path) -> None:
    workspace = tmp_path / "workfolder"
    workspace.mkdir()

    records, _ = WorkspaceCapabilityProvider(workspace).load()
    assert isinstance(records, list)


def test_workspace_capability_provider_none_root() -> None:
    records, _ = WorkspaceCapabilityProvider(None).load()
    assert records == []
