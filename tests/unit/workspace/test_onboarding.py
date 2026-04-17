"""Unit tests for workspace bundle onboarding verification."""

from __future__ import annotations

from pathlib import Path

from citnega.packages.config.settings import WorkspaceSettings
from citnega.packages.workspace.onboarding import (
    generate_workspace_bundle_manifest,
    verify_workspace_onboarding,
    write_workspace_bundle_manifest,
)


def _write_loadable_tool(workfolder: Path, name: str = "sample_tool") -> Path:
    tools_dir = workfolder / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)
    target = tools_dir / f"{name}.py"
    target.write_text("value = 1\n", encoding="utf-8")
    return target


def test_manifest_required_missing_returns_error(tmp_path: Path) -> None:
    _write_loadable_tool(tmp_path)
    settings = WorkspaceSettings(onboarding_require_manifest=True)
    report = verify_workspace_onboarding(tmp_path, settings)
    assert not report.ok
    assert any("required but missing" in err for err in report.errors)


def test_valid_manifest_with_trusted_publisher_passes(tmp_path: Path) -> None:
    _write_loadable_tool(tmp_path)
    manifest = generate_workspace_bundle_manifest(
        tmp_path,
        bundle_id="bundle-one",
        publisher="trusted-inc",
    )
    write_workspace_bundle_manifest(tmp_path, manifest)

    settings = WorkspaceSettings(
        onboarding_require_manifest=True,
        onboarding_trusted_publishers=["trusted-inc"],
    )
    report = verify_workspace_onboarding(tmp_path, settings)
    assert report.ok
    assert report.manifest is not None


def test_hash_mismatch_is_detected(tmp_path: Path) -> None:
    tool = _write_loadable_tool(tmp_path)
    manifest = generate_workspace_bundle_manifest(
        tmp_path,
        bundle_id="bundle-two",
        publisher="trusted-inc",
    )
    write_workspace_bundle_manifest(tmp_path, manifest)

    tool.write_text("value = 2\n", encoding="utf-8")
    settings = WorkspaceSettings(onboarding_require_manifest=True)
    report = verify_workspace_onboarding(tmp_path, settings)

    assert not report.ok
    assert any("hash mismatch" in err for err in report.errors)


def test_signature_required_and_valid_passes(tmp_path: Path) -> None:
    _write_loadable_tool(tmp_path)
    manifest = generate_workspace_bundle_manifest(
        tmp_path,
        bundle_id="bundle-three",
        publisher="trusted-inc",
        signature_key="shared-secret",
    )
    write_workspace_bundle_manifest(tmp_path, manifest)

    settings = WorkspaceSettings(
        onboarding_require_manifest=True,
        onboarding_require_signature=True,
        onboarding_signature_key="shared-secret",
    )
    report = verify_workspace_onboarding(tmp_path, settings)

    assert report.ok


def test_signature_mismatch_is_rejected(tmp_path: Path) -> None:
    _write_loadable_tool(tmp_path)
    manifest = generate_workspace_bundle_manifest(
        tmp_path,
        bundle_id="bundle-four",
        publisher="trusted-inc",
        signature_key="right-secret",
    )
    write_workspace_bundle_manifest(tmp_path, manifest)

    settings = WorkspaceSettings(
        onboarding_require_manifest=True,
        onboarding_require_signature=True,
        onboarding_signature_key="wrong-secret",
    )
    report = verify_workspace_onboarding(tmp_path, settings)

    assert not report.ok
    assert any("signature mismatch" in err for err in report.errors)


def test_enforce_file_coverage_rejects_undeclared_loadable_file(tmp_path: Path) -> None:
    _write_loadable_tool(tmp_path, name="declared_tool")
    manifest = generate_workspace_bundle_manifest(
        tmp_path,
        bundle_id="bundle-five",
        publisher="trusted-inc",
    )
    write_workspace_bundle_manifest(tmp_path, manifest)

    _write_loadable_tool(tmp_path, name="undeclared_tool")
    settings = WorkspaceSettings(
        onboarding_require_manifest=True,
        onboarding_enforce_file_coverage=True,
    )
    report = verify_workspace_onboarding(tmp_path, settings)

    assert not report.ok
    assert any("missing from bundle manifest" in err for err in report.errors)
