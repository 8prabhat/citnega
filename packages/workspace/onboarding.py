"""Workspace bundle onboarding: manifest, provenance, and signature checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import hmac
import json
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from citnega.packages.config.settings import WorkspaceSettings

DEFAULT_MANIFEST_RELPATH = ".citnega/bundle_manifest.json"
_LOADABLE_DIRS = ("tools", "agents", "workflows")


class BundleFileRecord(BaseModel):
    path: str
    sha256: str
    size_bytes: int = 0


class BundleProvenance(BaseModel):
    publisher: str
    source: str = ""
    version: str = ""
    revision: str = ""


class BundleSignature(BaseModel):
    algorithm: str = "hmac-sha256"
    value: str


class WorkspaceBundleManifest(BaseModel):
    schema_version: int = 1
    bundle_id: str
    created_at: str = Field(default_factory=lambda: datetime.now(tz=UTC).isoformat())
    provenance: BundleProvenance
    files: list[BundleFileRecord] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    signature: BundleSignature | None = None

    def signing_payload(self) -> dict[str, Any]:
        ordered_files = sorted(
            [
                {
                    "path": record.path,
                    "sha256": record.sha256,
                    "size_bytes": int(record.size_bytes),
                }
                for record in self.files
            ],
            key=lambda entry: entry["path"],
        )
        return {
            "schema_version": self.schema_version,
            "bundle_id": self.bundle_id,
            "created_at": self.created_at,
            "provenance": self.provenance.model_dump(),
            "files": ordered_files,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class WorkspaceOnboardingReport:
    manifest_path: Path
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    manifest: WorkspaceBundleManifest | None = None

    @property
    def ok(self) -> bool:
        return not self.errors


class WorkspaceOnboardingError(ValueError):
    """Raised when workspace bundle onboarding checks fail."""


def compute_bundle_manifest_signature(
    manifest: WorkspaceBundleManifest,
    secret_key: str,
) -> str:
    payload = json.dumps(
        manifest.signing_payload(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hmac.new(secret_key.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def generate_workspace_bundle_manifest(
    workfolder: Path,
    *,
    bundle_id: str,
    publisher: str,
    source: str = "",
    version: str = "",
    revision: str = "",
    metadata: dict[str, Any] | None = None,
    signature_key: str = "",
) -> WorkspaceBundleManifest:
    root = Path(workfolder).expanduser().resolve()
    if not bundle_id.strip():
        raise ValueError("bundle_id must be non-empty.")
    if not publisher.strip():
        raise ValueError("publisher must be non-empty.")

    records: list[BundleFileRecord] = []
    for rel in sorted(discover_loadable_workspace_modules(root)):
        target = (root / Path(rel)).resolve()
        records.append(
            BundleFileRecord(
                path=rel,
                sha256=sha256_file(target),
                size_bytes=target.stat().st_size,
            )
        )

    manifest = WorkspaceBundleManifest(
        bundle_id=bundle_id.strip(),
        provenance=BundleProvenance(
            publisher=publisher.strip(),
            source=source.strip(),
            version=version.strip(),
            revision=revision.strip(),
        ),
        files=records,
        metadata=dict(metadata or {}),
    )
    if signature_key.strip():
        manifest.signature = BundleSignature(
            algorithm="hmac-sha256",
            value=compute_bundle_manifest_signature(manifest, signature_key.strip()),
        )
    return manifest


def write_workspace_bundle_manifest(
    workfolder: Path,
    manifest: WorkspaceBundleManifest,
    manifest_relpath: str = DEFAULT_MANIFEST_RELPATH,
) -> Path:
    root = Path(workfolder).expanduser().resolve()
    target = resolve_manifest_path(root, manifest_relpath)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def verify_workspace_onboarding(
    workfolder: Path,
    workspace_settings: WorkspaceSettings,
) -> WorkspaceOnboardingReport:
    root = Path(workfolder).expanduser().resolve()
    manifest_path = resolve_manifest_path(root, workspace_settings.onboarding_manifest_path)
    warnings: list[str] = []
    errors: list[str] = []

    if not manifest_path.exists():
        if workspace_settings.onboarding_require_manifest:
            errors.append(
                f"Workspace bundle manifest is required but missing: {manifest_path}"
            )
        else:
            warnings.append(f"Workspace bundle manifest not found: {manifest_path}")
        return WorkspaceOnboardingReport(
            manifest_path=manifest_path,
            errors=tuple(errors),
            warnings=tuple(warnings),
        )

    try:
        manifest = WorkspaceBundleManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
    except Exception as exc:
        errors.append(f"Invalid workspace bundle manifest {manifest_path}: {exc}")
        return WorkspaceOnboardingReport(
            manifest_path=manifest_path,
            errors=tuple(errors),
            warnings=tuple(warnings),
        )

    _verify_provenance(manifest, workspace_settings, errors)
    declared_files = _verify_declared_files(root, manifest, errors)

    if workspace_settings.onboarding_enforce_file_coverage:
        loadable = discover_loadable_workspace_modules(root)
        undeclared = sorted(loadable - declared_files)
        if undeclared:
            errors.append(
                "Loadable workspace modules are missing from bundle manifest: "
                + ", ".join(undeclared)
            )

    _verify_signature(manifest, workspace_settings, errors, warnings)

    return WorkspaceOnboardingReport(
        manifest_path=manifest_path,
        errors=tuple(errors),
        warnings=tuple(warnings),
        manifest=manifest,
    )


def enforce_workspace_onboarding(
    workfolder: Path,
    workspace_settings: WorkspaceSettings,
) -> WorkspaceOnboardingReport:
    report = verify_workspace_onboarding(workfolder, workspace_settings)
    if report.errors:
        details = "; ".join(report.errors)
        raise WorkspaceOnboardingError(details)
    return report


def resolve_manifest_path(workfolder: Path, manifest_relpath: str) -> Path:
    root = Path(workfolder).expanduser().resolve()
    rel = manifest_relpath.strip() or DEFAULT_MANIFEST_RELPATH
    candidate = Path(rel).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return (root / candidate).resolve()


def discover_loadable_workspace_modules(workfolder: Path) -> set[str]:
    root = Path(workfolder).expanduser().resolve()
    modules: set[str] = set()
    for subdir in _LOADABLE_DIRS:
        folder = root / subdir
        if not folder.is_dir():
            continue
        for py_file in sorted(folder.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            modules.add(py_file.relative_to(root).as_posix())
    return modules


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_provenance(
    manifest: WorkspaceBundleManifest,
    workspace_settings: WorkspaceSettings,
    errors: list[str],
) -> None:
    publisher = manifest.provenance.publisher.strip()
    if not publisher:
        errors.append("Bundle provenance.publisher must be non-empty.")
        return

    trusted = {
        entry.strip()
        for entry in workspace_settings.onboarding_trusted_publishers
        if str(entry).strip()
    }
    if trusted and publisher not in trusted:
        errors.append(
            f"Bundle publisher {publisher!r} is not in trusted publisher allowlist."
        )


def _verify_declared_files(
    workfolder: Path,
    manifest: WorkspaceBundleManifest,
    errors: list[str],
) -> set[str]:
    declared: set[str] = set()
    for idx, record in enumerate(manifest.files):
        try:
            relpath = _normalise_relpath(record.path)
            target = _resolve_workspace_path(workfolder, relpath)
        except ValueError as exc:
            errors.append(f"files[{idx}] path invalid: {exc}")
            continue

        declared.add(relpath)
        if not target.exists() or not target.is_file():
            errors.append(f"files[{idx}] does not exist on disk: {relpath}")
            continue

        digest = sha256_file(target)
        if digest.lower() != record.sha256.strip().lower():
            errors.append(
                f"files[{idx}] hash mismatch for {relpath}: "
                f"expected {record.sha256}, got {digest}"
            )
    return declared


def _verify_signature(
    manifest: WorkspaceBundleManifest,
    workspace_settings: WorkspaceSettings,
    errors: list[str],
    warnings: list[str],
) -> None:
    signature = manifest.signature
    key = workspace_settings.onboarding_signature_key.strip()
    require_signature = workspace_settings.onboarding_require_signature

    if signature is None:
        if require_signature:
            errors.append("Bundle signature is required but missing.")
        return

    algorithm = signature.algorithm.strip().lower()
    if algorithm != "hmac-sha256":
        errors.append(
            "Unsupported bundle signature algorithm. Expected 'hmac-sha256', "
            f"got {signature.algorithm!r}."
        )
        return

    if not key:
        if require_signature:
            errors.append(
                "Bundle signature verification key is missing. Set "
                "workspace.onboarding_signature_key or "
                "CITNEGA_WORKSPACE_ONBOARDING_SIGNATURE_KEY."
            )
        else:
            warnings.append(
                "Bundle signature present but onboarding_signature_key is empty; "
                "signature verification skipped."
            )
        return

    expected = compute_bundle_manifest_signature(manifest, key).lower()
    actual = signature.value.strip().lower()
    if not hmac.compare_digest(actual, expected):
        errors.append("Bundle signature verification failed: signature mismatch.")


def _normalise_relpath(path_value: str) -> str:
    raw = path_value.strip().replace("\\", "/")
    if not raw:
        raise ValueError("path must be non-empty")
    candidate = PurePosixPath(raw)
    if candidate.is_absolute():
        raise ValueError("path must be relative")
    parts = [part for part in candidate.parts if part not in ("", ".")]
    if not parts:
        raise ValueError("path must contain at least one segment")
    if ".." in parts:
        raise ValueError("path traversal is not allowed")
    return PurePosixPath(*parts).as_posix()


def _resolve_workspace_path(workfolder: Path, relpath: str) -> Path:
    root = Path(workfolder).expanduser().resolve()
    resolved = (root / Path(relpath)).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"path escapes workspace root: {relpath!r}")
    return resolved
