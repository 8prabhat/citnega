"""artifact_pack — bundle execution artifacts for handoff and review."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import subprocess
from typing import TYPE_CHECKING, Any
import uuid
import zipfile

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.security.permissions import ensure_dir_permissions, ensure_file_permissions
from citnega.packages.shared.errors import CallableError
from citnega.packages.tools.builtin._tool_base import tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext
    from citnega.packages.storage.path_resolver import PathResolver


class ArtifactPackInput(BaseModel):
    working_dir: str = Field(
        default="",
        description="Repository/workspace root. Empty means current working directory.",
    )
    run_id: str = Field(
        default="",
        description="Optional run id used to attach the event log if available.",
    )
    pack_name: str = Field(
        default="",
        description="Optional logical pack name. Used as the artifact id prefix.",
    )
    include_git: bool = Field(
        default=True,
        description="Collect git status/diff/log evidence when in a git repository.",
    )
    include_event_log: bool = Field(
        default=True,
        description="Include the run event log when run_id can be resolved to a file.",
    )
    include_paths: list[str] = Field(
        default_factory=list,
        description="Optional additional files/directories to copy into the pack.",
    )
    max_files: int = Field(
        default=60,
        description="Maximum number of files copied from include_paths.",
    )
    max_file_bytes: int = Field(
        default=256 * 1024,
        description="Maximum bytes copied per included file (truncated when larger).",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Free-form metadata attached to the manifest.",
    )
    notes: str = Field(
        default="",
        description="Optional human notes saved to the manifest and summary.",
    )
    create_zip: bool = Field(
        default=True,
        description="Whether to create a zip bundle next to the artifact directory.",
    )


class ArtifactPackOutput(BaseModel):
    artifact_id: str
    artifact_dir: str
    manifest_path: str
    summary_path: str
    bundle_path: str = ""
    included_files: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary: str


class ArtifactPackTool(BaseCallable):
    name = "artifact_pack"
    description = (
        "Bundle run outputs for review and handoff: manifest, summary, optional git evidence, "
        "optional event log, selected files, and optional zip archive."
    )
    callable_type = CallableType.TOOL
    input_schema = ArtifactPackInput
    output_schema = ArtifactPackOutput
    policy = tool_policy(
        timeout_seconds=240.0,
        requires_approval=False,
        network_allowed=False,
        max_output_bytes=512 * 1024,
    )

    def __init__(self, *args: object, path_resolver: PathResolver | None = None, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._path_resolver = path_resolver

    async def _execute(self, input: ArtifactPackInput, context: CallContext) -> ArtifactPackOutput:
        root = Path(input.working_dir or os.getcwd()).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            raise CallableError(f"Invalid working directory: {root}")

        run_id = input.run_id.strip() or context.run_id or "manual"
        session_id = context.session_id or "session"
        artifact_id = self._build_artifact_id(input.pack_name)
        artifact_root = self._artifact_root(root)
        artifact_dir = artifact_root / session_id / run_id / artifact_id
        ensure_dir_permissions(artifact_dir)

        included_files: list[str] = []
        warnings: list[str] = []

        if input.include_git:
            self._collect_git_evidence(
                root=root,
                artifact_dir=artifact_dir,
                included_files=included_files,
                warnings=warnings,
            )

        if input.include_event_log:
            self._include_event_log(
                run_id=run_id,
                working_dir=root,
                artifact_dir=artifact_dir,
                max_bytes=max(1024, input.max_file_bytes * 4),
                included_files=included_files,
                warnings=warnings,
            )

        if input.include_paths:
            self._copy_requested_paths(
                root=root,
                artifact_dir=artifact_dir,
                include_paths=input.include_paths,
                max_files=max(1, input.max_files),
                max_bytes=max(1024, input.max_file_bytes),
                included_files=included_files,
                warnings=warnings,
            )

        created_at = datetime.now(tz=UTC)
        manifest = {
            "artifact_id": artifact_id,
            "created_at": created_at.isoformat(),
            "session_id": session_id,
            "run_id": run_id,
            "working_dir": str(root),
            "metadata": dict(input.metadata),
            "notes": input.notes,
            "included_files": included_files,
            "warnings": warnings,
        }

        manifest_path = artifact_dir / "manifest.json"
        summary_path = artifact_dir / "SUMMARY.md"
        self._write_text(manifest_path, json.dumps(manifest, indent=2, default=str))
        self._write_text(
            summary_path,
            self._render_summary(
                artifact_id=artifact_id,
                created_at=created_at,
                working_dir=root,
                run_id=run_id,
                included_files=included_files,
                warnings=warnings,
                notes=input.notes,
                metadata=input.metadata,
            ),
        )

        if "manifest.json" not in included_files:
            included_files.append("manifest.json")
        if "SUMMARY.md" not in included_files:
            included_files.append("SUMMARY.md")

        bundle_path = ""
        if input.create_zip:
            zip_path = artifact_dir.parent / f"{artifact_id}.zip"
            self._write_zip(artifact_dir=artifact_dir, zip_path=zip_path)
            bundle_path = str(zip_path)

        summary = (
            f"Artifact pack created at {artifact_dir} with {len(included_files)} files"
            + (f" and zip {bundle_path}" if bundle_path else "")
            + (f". Warnings={len(warnings)}." if warnings else ".")
        )

        return ArtifactPackOutput(
            artifact_id=artifact_id,
            artifact_dir=str(artifact_dir),
            manifest_path=str(manifest_path),
            summary_path=str(summary_path),
            bundle_path=bundle_path,
            included_files=included_files,
            warnings=warnings,
            summary=summary,
        )

    def _artifact_root(self, working_dir: Path) -> Path:
        if self._path_resolver is not None:
            return self._path_resolver.artifacts_dir
        return working_dir / ".citnega_artifacts"

    def _build_artifact_id(self, pack_name: str) -> str:
        base = _slug(pack_name) if pack_name.strip() else "artifact-pack"
        stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
        return f"{base}-{stamp}-{uuid.uuid4().hex[:6]}"

    def _collect_git_evidence(
        self,
        *,
        root: Path,
        artifact_dir: Path,
        included_files: list[str],
        warnings: list[str],
    ) -> None:
        probes = {
            "status.txt": ["status", "--short", "--branch"],
            "diff_stat.txt": ["diff", "--stat", "--no-color"],
            "recent_commits.txt": ["log", "--oneline", "-n", "15"],
        }

        git_dir = artifact_dir / "git"
        wrote_any = False
        for filename, args in probes.items():
            completed = self._run_git(root, args)
            if completed is None:
                warnings.append("git not available in PATH; skipping git evidence.")
                return
            if completed.returncode != 0:
                if not wrote_any:
                    warnings.append(
                        "git evidence skipped: working directory is not a git repository or command failed."
                    )
                continue

            content = (completed.stdout or "").strip()
            if not content:
                content = "(no output)"
            out_path = git_dir / filename
            self._write_text(out_path, content + "\n")
            included_files.append(f"git/{filename}")
            wrote_any = True

    def _include_event_log(
        self,
        *,
        run_id: str,
        working_dir: Path,
        artifact_dir: Path,
        max_bytes: int,
        included_files: list[str],
        warnings: list[str],
    ) -> None:
        event_path = self._resolve_event_log_path(run_id, working_dir)
        if event_path is None:
            warnings.append(f"No event log found for run_id={run_id}.")
            return

        try:
            raw = event_path.read_bytes()
        except OSError as exc:
            warnings.append(f"Failed to read event log {event_path}: {exc}")
            return

        truncated = False
        if len(raw) > max_bytes:
            raw = raw[:max_bytes]
            truncated = True

        out = artifact_dir / "events" / f"{run_id}.jsonl"
        self._write_bytes(out, raw)
        included_files.append(f"events/{run_id}.jsonl")
        if truncated:
            warnings.append(
                f"Event log was truncated to {max_bytes} bytes for packaging safety."
            )

    def _resolve_event_log_path(self, run_id: str, working_dir: Path) -> Path | None:
        candidates: list[Path] = []

        if self._path_resolver is not None:
            candidates.append(self._path_resolver.event_log_path(run_id))

        env_home = os.environ.get("CITNEGA_APP_HOME", "").strip()
        if env_home:
            app_home = Path(env_home).expanduser().resolve()
            candidates.append(app_home / "logs" / "events" / f"{run_id}.jsonl")
            candidates.append(app_home / "memory" / "logs" / "events" / f"{run_id}.jsonl")

        candidates.append(working_dir / "memory" / "logs" / "events" / f"{run_id}.jsonl")
        candidates.append(working_dir / ".citnega" / "memory" / "logs" / "events" / f"{run_id}.jsonl")

        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate
        return None

    def _copy_requested_paths(
        self,
        *,
        root: Path,
        artifact_dir: Path,
        include_paths: list[str],
        max_files: int,
        max_bytes: int,
        included_files: list[str],
        warnings: list[str],
    ) -> None:
        copied = 0
        target_root = artifact_dir / "inputs"

        for raw in include_paths:
            if copied >= max_files:
                warnings.append(f"Reached include_paths max_files={max_files}; remaining paths skipped.")
                break

            resolved = Path(raw).expanduser()
            if not resolved.is_absolute():
                resolved = (root / resolved).resolve()
            else:
                resolved = resolved.resolve()

            if not resolved.exists():
                warnings.append(f"Included path does not exist and was skipped: {raw}")
                continue

            if resolved.is_file():
                copied += self._copy_one_file(
                    source=resolved,
                    root=root,
                    target_root=target_root,
                    max_bytes=max_bytes,
                    included_files=included_files,
                    warnings=warnings,
                )
                continue

            for child in sorted(resolved.rglob("*")):
                if copied >= max_files:
                    warnings.append(
                        f"Reached include_paths max_files={max_files}; directory copy was truncated."
                    )
                    break
                if not child.is_file():
                    continue
                copied += self._copy_one_file(
                    source=child,
                    root=root,
                    target_root=target_root,
                    max_bytes=max_bytes,
                    included_files=included_files,
                    warnings=warnings,
                )

    def _copy_one_file(
        self,
        *,
        source: Path,
        root: Path,
        target_root: Path,
        max_bytes: int,
        included_files: list[str],
        warnings: list[str],
    ) -> int:
        rel = self._normalise_rel(root, source)
        destination = target_root / rel

        try:
            raw = source.read_bytes()
        except OSError as exc:
            warnings.append(f"Failed to read {source}: {exc}")
            return 0

        truncated = False
        if len(raw) > max_bytes:
            raw = raw[:max_bytes]
            truncated = True

        self._write_bytes(destination, raw)
        included_files.append(f"inputs/{rel.as_posix()}")

        if truncated:
            warnings.append(f"File truncated while packaging: {source} ({max_bytes} bytes kept).")
        return 1

    def _normalise_rel(self, root: Path, path: Path) -> Path:
        try:
            rel = path.relative_to(root)
            return rel
        except ValueError:
            return Path("external") / path.name

    def _write_text(self, path: Path, content: str) -> None:
        ensure_dir_permissions(path.parent)
        path.write_text(content, encoding="utf-8")
        ensure_file_permissions(path)

    def _write_bytes(self, path: Path, content: bytes) -> None:
        ensure_dir_permissions(path.parent)
        path.write_bytes(content)
        ensure_file_permissions(path)

    def _write_zip(self, *, artifact_dir: Path, zip_path: Path) -> None:
        ensure_dir_permissions(zip_path.parent)
        with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(artifact_dir.rglob("*")):
                if path.is_file():
                    zf.write(path, path.relative_to(artifact_dir))
        ensure_file_permissions(zip_path)

    def _run_git(self, root: Path, args: list[str]) -> subprocess.CompletedProcess[str] | None:
        try:
            return subprocess.run(
                ["git", "-C", str(root), *args],
                check=False,
                capture_output=True,
                text=True,
                timeout=25,
            )
        except FileNotFoundError:
            return None
        except Exception:
            return None

    def _render_summary(
        self,
        *,
        artifact_id: str,
        created_at: datetime,
        working_dir: Path,
        run_id: str,
        included_files: list[str],
        warnings: list[str],
        notes: str,
        metadata: dict[str, Any],
    ) -> str:
        lines = [
            f"# Artifact Pack: {artifact_id}",
            "",
            f"- Created: {created_at.isoformat()}",
            f"- Working dir: {working_dir}",
            f"- Run id: {run_id}",
            f"- Included files: {len(included_files)}",
        ]

        if notes.strip():
            lines.extend(["", "## Notes", "", notes.strip()])

        if metadata:
            lines.extend(["", "## Metadata", ""])
            for key, value in metadata.items():
                lines.append(f"- {key}: {value}")

        lines.extend(["", "## Files", ""])
        for rel in included_files:
            lines.append(f"- {rel}")

        if warnings:
            lines.extend(["", "## Warnings", ""])
            for warning in warnings:
                lines.append(f"- {warning}")

        return "\n".join(lines) + "\n"


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip().lower())
    cleaned = cleaned.strip("-._")
    return cleaned[:40] if cleaned else "artifact-pack"
