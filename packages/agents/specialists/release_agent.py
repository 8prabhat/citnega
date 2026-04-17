"""ReleaseAgent — release-readiness synthesis across git, quality, and artifacts."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.agents.specialists._specialist_base import SpecialistBase, SpecialistOutput
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType
from citnega.packages.shared.errors import CallableError

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class ReleaseAgentInput(BaseModel):
    task: str = Field(
        default="Assess release readiness and produce a deployment/rollback brief.",
        description="Release objective.",
    )
    working_dir: str = Field(
        default="",
        description="Repository root. Empty means current working directory.",
    )
    version: str = Field(
        default="",
        description="Optional target version tag (e.g. v0.9.0).",
    )
    base_ref: str = Field(
        default="HEAD~1",
        description="Base git ref for changelog/diff scope.",
    )
    head_ref: str = Field(
        default="HEAD",
        description="Head git ref for changelog/diff scope.",
    )
    max_commits: int = Field(
        default=20,
        description="Maximum commits included in changelog section.",
    )
    include_quality_gate: bool = Field(
        default=True,
        description="Run quality_gate and include its status.",
    )
    quality_profile: str = Field(
        default="quick",
        description="quality_gate profile when include_quality_gate=true.",
    )
    include_test_matrix: bool = Field(
        default=True,
        description="Run test_matrix discovery and include coverage footprint.",
    )
    include_repo_map: bool = Field(
        default=False,
        description="Include architecture hotspots in release context.",
    )
    include_artifact_pack: bool = Field(
        default=True,
        description="Create artifact_pack bundle with release handoff assets.",
    )
    artifact_name: str = Field(
        default="",
        description="Optional artifact pack name override.",
    )


class _GitReleaseContext(BaseModel):
    commits: list[str] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    diff_stat: str = ""
    warnings: list[str] = Field(default_factory=list)


class ReleaseAgent(SpecialistBase):
    name = "release_agent"
    description = (
        "Release specialist: composes changelog, migration notes, risk matrix, "
        "quality status, artifact handoff, and rollback plan."
    )
    callable_type = CallableType.SPECIALIST
    input_schema = ReleaseAgentInput
    output_schema = SpecialistOutput
    policy = CallablePolicy(
        timeout_seconds=420.0,
        requires_approval=False,
        network_allowed=False,
        max_output_bytes=512 * 1024,
        max_depth_allowed=4,
    )

    SYSTEM_PROMPT = (
        "You are a release engineering lead. Prioritize objective readiness signals and "
        "explicit rollback safety over optimistic messaging."
    )
    TOOL_WHITELIST = ["quality_gate", "test_matrix", "repo_map", "artifact_pack"]

    async def _execute(self, input: ReleaseAgentInput, context: CallContext) -> SpecialistOutput:
        root = Path(input.working_dir or os.getcwd()).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            raise CallableError(f"Invalid working directory: {root}")

        tool_calls_made: list[str] = []
        sources: list[str] = []
        evidence_sections: list[str] = []
        child_ctx = context.child(self.name, self.callable_type)

        gate_passed: bool | None = None
        if input.include_quality_gate:
            gate_tool = self._get_tool("quality_gate")
            if gate_tool is not None:
                from citnega.packages.tools.builtin.quality_gate import QualityGateInput

                gate_result = await gate_tool.invoke(
                    QualityGateInput(
                        working_dir=str(root),
                        profile=input.quality_profile,
                    ),
                    child_ctx,
                )
                tool_calls_made.append("quality_gate")
                if gate_result.success and gate_result.output:
                    out = gate_result.output
                    gate_passed = bool(out.passed)
                    failing = [c.name for c in out.checks if not c.passed]
                    evidence_sections.append(
                        "Quality gate:\n"
                        f"- {out.summary}\n"
                        f"- Failing checks: {', '.join(failing) if failing else 'none'}"
                    )
                    sources.append("quality_gate")
                elif gate_result.error:
                    gate_passed = False
                    evidence_sections.append(f"Quality gate execution failed: {gate_result.error.message}")

        if input.include_test_matrix:
            matrix_tool = self._get_tool("test_matrix")
            if matrix_tool is not None:
                from citnega.packages.tools.builtin.test_matrix import MatrixInput

                matrix_result = await matrix_tool.invoke(
                    MatrixInput(root_path=str(root), execute=False),
                    child_ctx,
                )
                tool_calls_made.append("test_matrix")
                if matrix_result.success and matrix_result.output:
                    out = matrix_result.output
                    buckets = ", ".join(f"{k}:{v}" for k, v in sorted(out.buckets.items())) or "none"
                    evidence_sections.append(
                        "Test matrix:\n"
                        f"- {out.summary}\n"
                        f"- Buckets: {buckets}"
                    )
                    sources.append("test_matrix")
                elif matrix_result.error:
                    evidence_sections.append(f"Test matrix execution failed: {matrix_result.error.message}")

        if input.include_repo_map:
            repo_tool = self._get_tool("repo_map")
            if repo_tool is not None:
                from citnega.packages.tools.builtin.repo_map import RepoMapInput

                repo_result = await repo_tool.invoke(
                    RepoMapInput(root_path=str(root), include_tests=True, max_hotspots=8, max_edges=12),
                    child_ctx,
                )
                tool_calls_made.append("repo_map")
                if repo_result.success and repo_result.output:
                    out = repo_result.output
                    evidence_sections.append(
                        "Repository map:\n"
                        f"- {out.summary}\n"
                        f"- Hotspots: {', '.join(out.hotspots[:5]) or 'none'}"
                    )
                    sources.append("repo_map")
                elif repo_result.error:
                    evidence_sections.append(f"Repo map execution failed: {repo_result.error.message}")

        git_ctx = self._collect_git_context(
            root=root,
            base_ref=input.base_ref,
            head_ref=input.head_ref,
            max_commits=max(1, input.max_commits),
        )

        risk_rows = self._build_risk_rows(git_ctx.changed_files)
        migration_notes = self._derive_migration_notes(git_ctx.changed_files)

        artifact_section = ""
        if input.include_artifact_pack:
            artifact_tool = self._get_tool("artifact_pack")
            if artifact_tool is not None:
                from citnega.packages.tools.builtin.artifact_pack import ArtifactPackInput

                pack_name = input.artifact_name.strip() or self._default_artifact_name(input.version)
                include_paths = self._artifact_include_paths(root, git_ctx.changed_files)
                artifact_result = await artifact_tool.invoke(
                    ArtifactPackInput(
                        working_dir=str(root),
                        run_id=context.run_id,
                        pack_name=pack_name,
                        include_git=True,
                        include_event_log=False,
                        include_paths=include_paths,
                        metadata={
                            "version": input.version or "unversioned",
                            "base_ref": input.base_ref,
                            "head_ref": input.head_ref,
                        },
                        notes="Release readiness artifact bundle.",
                        create_zip=True,
                    ),
                    child_ctx,
                )
                tool_calls_made.append("artifact_pack")
                if artifact_result.success and artifact_result.output:
                    out = artifact_result.output
                    artifact_section = (
                        "Artifact pack:\n"
                        f"- {out.summary}\n"
                        f"- Bundle: {out.bundle_path or 'not generated'}"
                    )
                    sources.append("artifact_pack")
                elif artifact_result.error:
                    artifact_section = f"Artifact pack failed: {artifact_result.error.message}"

        verdict, blockers = self._release_verdict(gate_passed, risk_rows)
        response = self._build_report(
            task=input.task,
            root=root,
            version=input.version,
            base_ref=input.base_ref,
            head_ref=input.head_ref,
            verdict=verdict,
            blockers=blockers,
            git_ctx=git_ctx,
            risk_rows=risk_rows,
            migration_notes=migration_notes,
            evidence_sections=evidence_sections,
            artifact_section=artifact_section,
        )

        return SpecialistOutput(
            response=response,
            tool_calls_made=tool_calls_made,
            sources=sources,
        )

    def _collect_git_context(
        self,
        *,
        root: Path,
        base_ref: str,
        head_ref: str,
        max_commits: int,
    ) -> _GitReleaseContext:
        ctx = _GitReleaseContext()
        ref_range = f"{base_ref}..{head_ref}" if base_ref and head_ref else ""

        commits_args = ["log", "--oneline", "-n", str(max_commits)]
        if ref_range:
            commits_args = ["log", "--oneline", ref_range, "-n", str(max_commits)]

        commits = self._run_git(root, commits_args)
        if commits is None:
            ctx.warnings.append("git not available; changelog and diff details are limited.")
            return ctx

        if commits.returncode == 0:
            ctx.commits = [line.strip() for line in commits.stdout.splitlines() if line.strip()]
        else:
            fallback = self._run_git(root, ["log", "--oneline", "-n", str(max_commits)])
            if fallback is not None and fallback.returncode == 0:
                ctx.commits = [line.strip() for line in fallback.stdout.splitlines() if line.strip()]
            else:
                ctx.warnings.append("Unable to collect git commit history for release scope.")

        diff_files = self._run_git(root, ["diff", "--name-only", ref_range] if ref_range else ["diff", "--name-only"])
        if diff_files is not None and diff_files.returncode == 0:
            ctx.changed_files = [line.strip() for line in diff_files.stdout.splitlines() if line.strip()]
        elif ref_range:
            show_files = self._run_git(root, ["show", "--pretty=", "--name-only", head_ref])
            if show_files is not None and show_files.returncode == 0:
                ctx.changed_files = [line.strip() for line in show_files.stdout.splitlines() if line.strip()]

        diff_stat = self._run_git(root, ["diff", "--stat", ref_range] if ref_range else ["diff", "--stat"])
        if diff_stat is not None and diff_stat.returncode == 0:
            ctx.diff_stat = diff_stat.stdout.strip()

        if not ctx.changed_files:
            ctx.warnings.append("No changed files detected for the selected ref range.")

        return ctx

    def _build_risk_rows(self, changed_files: list[str]) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for rel in changed_files:
            lowered = rel.lower()
            risk = "medium"
            reason = "Product/code surface changed."

            if any(k in lowered for k in ("runtime", "policy", "security", "bootstrap", "core_runtime")):
                risk = "high"
                reason = "Core runtime or security control path changed."
            elif any(k in lowered for k in ("migrations", "alembic", "settings", "config/")):
                risk = "high"
                reason = "Configuration or schema path changed; rollout compatibility risk."
            elif any(k in lowered for k in ("docs/", "readme", "changelog", "traceability")):
                risk = "low"
                reason = "Documentation-only surface change."
            elif lowered.startswith("tests/"):
                risk = "low"
                reason = "Test-only change."

            rows.append({"file": rel, "risk": risk, "reason": reason})

        return rows

    def _derive_migration_notes(self, changed_files: list[str]) -> list[str]:
        notes: list[str] = []

        if any("migrations" in f.lower() or "alembic" in f.lower() for f in changed_files):
            notes.append("Database/schema migration files changed; verify upgrade and rollback paths.")

        if any("settings" in f.lower() or "config" in f.lower() for f in changed_files):
            notes.append("Configuration surface changed; document defaults, env overrides, and compatibility expectations.")

        if any(f.lower().startswith("docs/") or "readme" in f.lower() for f in changed_files):
            notes.append("Documentation changed; ensure release notes reference updated behavior accurately.")

        if not notes:
            notes.append("No explicit migration-impacting paths detected from current change scope.")

        return notes

    def _release_verdict(
        self,
        gate_passed: bool | None,
        risk_rows: list[dict[str, str]],
    ) -> tuple[str, list[str]]:
        blockers: list[str] = []

        if gate_passed is False:
            blockers.append("Quality gate reported failures.")

        high_risk_count = sum(1 for row in risk_rows if row.get("risk") == "high")
        if high_risk_count > 0:
            blockers.append(
                f"{high_risk_count} high-risk changed files require explicit rollout and rollback validation."
            )

        if blockers:
            return "needs_attention", blockers
        return "ready", blockers

    def _artifact_include_paths(self, root: Path, changed_files: list[str]) -> list[str]:
        selected: list[str] = []
        for rel in changed_files:
            candidate = (root / rel).resolve()
            if candidate.exists() and candidate.is_file():
                selected.append(rel)
            if len(selected) >= 12:
                break
        return selected

    def _default_artifact_name(self, version: str) -> str:
        base = version.strip() or "candidate"
        safe = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in base)
        return f"release-{safe}"

    def _run_git(self, root: Path, args: list[str]) -> subprocess.CompletedProcess[str] | None:
        try:
            return subprocess.run(
                ["git", "-C", str(root), *args],
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
            )
        except FileNotFoundError:
            return None
        except Exception:
            return None

    def _build_report(
        self,
        *,
        task: str,
        root: Path,
        version: str,
        base_ref: str,
        head_ref: str,
        verdict: str,
        blockers: list[str],
        git_ctx: _GitReleaseContext,
        risk_rows: list[dict[str, str]],
        migration_notes: list[str],
        evidence_sections: list[str],
        artifact_section: str,
    ) -> str:
        lines = [
            f"Release task: {task}",
            f"Working directory: {root}",
            f"Version: {version or 'unspecified'}",
            f"Range: {base_ref}..{head_ref}",
            f"Verdict: {verdict.upper()}",
        ]

        if blockers:
            lines.append("Blockers:")
            for blocker in blockers:
                lines.append(f"- {blocker}")

        if git_ctx.warnings:
            lines.append("Git warnings:")
            for warning in git_ctx.warnings:
                lines.append(f"- {warning}")

        lines.extend(["", "Changelog (scoped commits):"])
        if git_ctx.commits:
            for commit in git_ctx.commits:
                lines.append(f"- {commit}")
        else:
            lines.append("- No commits resolved for the selected scope.")

        lines.extend(["", "Changed files:"])
        if git_ctx.changed_files:
            lines.extend(f"- {path}" for path in git_ctx.changed_files[:30])
            if len(git_ctx.changed_files) > 30:
                lines.append(f"- ... ({len(git_ctx.changed_files) - 30} more)")
        else:
            lines.append("- No changed files resolved.")

        if git_ctx.diff_stat:
            lines.extend(["", "Diff stat:", git_ctx.diff_stat])

        lines.extend(["", "Risk matrix:"])
        if risk_rows:
            for row in risk_rows[:25]:
                lines.append(f"- [{row['risk'].upper()}] {row['file']} — {row['reason']}")
            if len(risk_rows) > 25:
                lines.append(f"- ... ({len(risk_rows) - 25} more rows)")
        else:
            lines.append("- No risk rows available.")

        lines.extend(["", "Migration notes:"])
        for note in migration_notes:
            lines.append(f"- {note}")

        if evidence_sections:
            lines.extend(["", "Execution evidence:"])
            lines.extend(evidence_sections)

        if artifact_section:
            lines.extend(["", artifact_section])

        lines.extend(
            [
                "",
                "Rollback plan:",
                "1. Tag current head before deployment (e.g., git tag -a pre-release-<ts> HEAD).",
                "2. If rollback needed, revert release range (git revert --no-commit <base>..<head>) and commit.",
                "3. Redeploy previous known-good artifact and re-run quality gate + smoke tests.",
                "4. Publish incident note with root cause and permanent remediation.",
            ]
        )

        return "\n".join(lines)
