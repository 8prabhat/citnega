"""SecurityAgent — secret-safety and policy-focused repository scanner."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.agents.specialists._specialist_base import SpecialistBase, SpecialistOutput
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType
from citnega.packages.shared.errors import CallableError
from citnega.packages.tools.builtin._cache_utils import (
    cache_file,
    load_json_cache,
    stable_hash,
    write_json_cache,
)

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class SecurityAgentInput(BaseModel):
    task: str = Field(
        default="Assess security risks, secrets exposure, and policy gaps.",
        description="Security objective for the assessment.",
    )
    working_dir: str = Field(
        default="",
        description="Repository root. Empty means current working directory.",
    )
    changed_files: list[str] = Field(
        default_factory=list,
        description="Optional explicit file list to scan. When empty, agent auto-detects changed files.",
    )
    scan_untracked: bool = Field(
        default=True,
        description="Include untracked files when auto-detecting changed files.",
    )
    max_files: int = Field(
        default=250,
        description="Maximum number of files to inspect.",
    )
    max_findings: int = Field(
        default=20,
        description="Maximum findings to include in output.",
    )
    include_repo_map: bool = Field(
        default=True,
        description="Gather architecture context using repo_map.",
    )
    include_quality_gate: bool = Field(
        default=False,
        description="Run quality_gate to attach broader quality signals.",
    )
    quality_profile: str = Field(
        default="quick",
        description="quality_gate profile when include_quality_gate=true.",
    )
    run_id: str = Field(
        default="",
        description="Optional run id for event-log scrub checks.",
    )
    include_event_log_scan: bool = Field(
        default=True,
        description="Scan event logs for unsanitized secret fields when run_id is available.",
    )
    use_cache: bool = Field(
        default=True,
        description="Use filesystem cache for heavy static scans when safe.",
    )
    cache_ttl_seconds: int = Field(
        default=300,
        description="TTL for security scan cache entries.",
    )


class SecurityFinding(BaseModel):
    severity: str
    category: str
    file_path: str
    line: int = 0
    message: str
    recommendation: str


_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
_EXCLUDED_DIRS = {
    ".git",
    ".citnega_cache",
    ".venv",
    "venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "node_modules",
    "dist",
    "build",
}

_SECRET_KEY_RE = re.compile(
    r"(?i)\b(api[_-]?key|secret|password|token|access[_-]?key|authorization|credential)\b"
)
_AWS_KEY_RE = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
_GH_TOKEN_RE = re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")
_PRIVATE_KEY_RE = re.compile(r"-----BEGIN(?: [A-Z]+)? PRIVATE KEY-----")
_INLINE_SECRET_RE = re.compile(
    r"(?i)\b(api[_-]?key|secret|password|token|access[_-]?key)\b\s*[:=]\s*['\"][^'\"]{8,}['\"]"
)
_CURL_PIPE_RE = re.compile(r"\bcurl\b[^\n|]*\|\s*(?:sh|bash)\b")
_WGET_PIPE_RE = re.compile(r"\bwget\b[^\n|]*\|\s*(?:sh|bash)\b")
_RM_ROOT_RE = re.compile(r"\brm\s+-rf\s+/\b")
_SUBPROCESS_SHELL_RE = re.compile(r"subprocess\.(?:run|Popen|call)\([^\n]*shell\s*=\s*True")
_REQUESTS_VERIFY_FALSE_RE = re.compile(r"requests\.(?:get|post|put|patch|delete)\([^\n]*verify\s*=\s*False")


class SecurityAgent(SpecialistBase):
    name = "security_agent"
    description = (
        "Security specialist: scans changed code and event traces for secrets exposure, "
        "unsafe execution patterns, and policy drift; returns prioritized remediation."
    )
    callable_type = CallableType.SPECIALIST
    input_schema = SecurityAgentInput
    output_schema = SpecialistOutput
    policy = CallablePolicy(
        timeout_seconds=360.0,
        requires_approval=False,
        network_allowed=False,
        max_output_bytes=512 * 1024,
        max_depth_allowed=4,
    )

    SYSTEM_PROMPT = (
        "You are a security reviewer focused on practical risk reduction. "
        "Prioritize exploitable issues and data-leak vectors over style concerns."
    )
    TOOL_WHITELIST = [
        # Architecture context
        "repo_map",
        "quality_gate",
        # Static analysis (passive/local)
        "vuln_scanner",
        "secrets_scanner",
        "hash_integrity",
        # System inspection (passive/local)
        "os_fingerprint",
        "hypervisor_detect",
        "kernel_audit",
        "process_inspector",
        "user_audit",
        "firewall_inspect",
        # Network tools (requires_approval=True in policy — PolicyEnforcer gates these)
        "port_scanner",
        "network_recon",
        "network_vuln_scan",
        "ssl_tls_audit",
        "dns_recon",
    ]

    async def _execute(self, input: SecurityAgentInput, context: CallContext) -> SpecialistOutput:
        root = Path(input.working_dir or os.getcwd()).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            raise CallableError(f"Invalid working directory: {root}")

        tool_calls_made: list[str] = []
        sections: list[str] = []
        sources: list[str] = []
        child_ctx = context.child(self.name, self.callable_type)

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
                    sections.append(
                        "Repository topology:\n"
                        f"- {out.summary}\n"
                        f"- Hotspots: {', '.join(out.hotspots[:5]) or 'none'}"
                    )
                    sources.append("repo_map")
                elif repo_result.error:
                    sections.append(f"Repository mapping failed: {repo_result.error.message}")

        if input.include_quality_gate:
            gate_tool = self._get_tool("quality_gate")
            if gate_tool is not None:
                from citnega.packages.tools.builtin.quality_gate import QualityGateInput

                gate_result = await gate_tool.invoke(
                    QualityGateInput(working_dir=str(root), profile=input.quality_profile),
                    child_ctx,
                )
                tool_calls_made.append("quality_gate")
                if gate_result.success and gate_result.output:
                    out = gate_result.output
                    failing = [c.name for c in out.checks if not c.passed]
                    sections.append(
                        "Quality gate:\n"
                        f"- {out.summary}\n"
                        f"- Failing checks: {', '.join(failing) if failing else 'none'}"
                    )
                    sources.append("quality_gate")
                elif gate_result.error:
                    sections.append(f"Quality gate failed: {gate_result.error.message}")

        targets = self._resolve_targets(root, input)
        run_id = input.run_id.strip() or context.run_id
        cache_path = self._cache_path(
            root=root,
            input=input,
            targets=targets,
            run_id=run_id,
        )
        if cache_path is not None:
            cached = load_json_cache(cache_path, ttl_seconds=max(0, input.cache_ttl_seconds))
            if cached:
                cached_sources = [str(s) for s in cached.get("sources", []) if str(s).strip()]
                if "security_cache" not in cached_sources:
                    cached_sources.append("security_cache")
                return SpecialistOutput(
                    response=str(cached.get("response", "")),
                    tool_calls_made=[
                        str(s) for s in cached.get("tool_calls_made", []) if str(s).strip()
                    ],
                    sources=cached_sources,
                )

        findings = self._scan_files(root, targets)

        if input.include_event_log_scan and run_id:
            findings.extend(self._scan_event_log(run_id=run_id, working_dir=root))

        # Augment with dedicated vuln_scanner + secrets_scanner tools
        vuln_tool = self._get_tool("vuln_scanner")
        if vuln_tool is not None:
            from citnega.packages.tools.security.vuln_scanner import VulnScannerInput
            vr = await vuln_tool.invoke(VulnScannerInput(path=str(root)), child_ctx)
            if vr.success and vr.output:
                tool_calls_made.append("vuln_scanner")
                sections.append(
                    f"Static vuln scan: {vr.output.total_findings} findings "
                    f"({vr.output.critical} critical, {vr.output.high} high)"
                )
                sources.append("vuln_scanner")

        secrets_tool = self._get_tool("secrets_scanner")
        if secrets_tool is not None:
            from citnega.packages.tools.security.secrets_scanner import SecretsScannerInput
            sr = await secrets_tool.invoke(SecretsScannerInput(path=str(root)), child_ctx)
            if sr.success and sr.output:
                tool_calls_made.append("secrets_scanner")
                sections.append(
                    f"Secrets scan: {sr.output.critical + sr.output.high} high/critical findings "
                    f"across {sr.output.scanned_files} files"
                )
                sources.append("secrets_scanner")

        findings = sorted(
            findings,
            key=lambda f: (_SEVERITY_RANK.get(f.severity, 99), f.file_path, f.line),
        )[: max(1, input.max_findings)]

        response = self._build_report(
            task=input.task,
            root=root,
            scanned_files=len(targets),
            findings=findings,
            evidence_sections=sections,
        )

        output = SpecialistOutput(
            response=response,
            tool_calls_made=tool_calls_made,
            sources=sources,
        )
        if cache_path is not None:
            write_json_cache(
                cache_path,
                {
                    "response": output.response,
                    "tool_calls_made": output.tool_calls_made,
                    "sources": output.sources,
                },
            )
        return output

    def _resolve_targets(self, root: Path, input: SecurityAgentInput) -> list[Path]:
        max_files = max(1, input.max_files)

        if input.changed_files:
            resolved: list[Path] = []
            for raw in input.changed_files:
                path = Path(raw).expanduser()
                if not path.is_absolute():
                    path = (root / path).resolve()
                else:
                    path = path.resolve()
                if path.exists() and path.is_file():
                    resolved.append(path)
            return resolved[:max_files]

        changed = self._git_changed_files(root, include_untracked=input.scan_untracked)
        if changed:
            return changed[:max_files]

        return self._fallback_scan_files(root, max_files=max_files)

    def _git_changed_files(self, root: Path, *, include_untracked: bool) -> list[Path]:
        commands = [
            ["diff", "--name-only"],
            ["diff", "--name-only", "--cached"],
        ]
        if include_untracked:
            commands.append(["ls-files", "--others", "--exclude-standard"])

        paths: list[Path] = []
        seen: set[Path] = set()
        for args in commands:
            try:
                completed = subprocess.run(
                    ["git", "-C", str(root), *args],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
            except Exception:
                continue

            if completed.returncode != 0:
                continue

            for line in completed.stdout.splitlines():
                candidate = (root / line.strip()).resolve()
                if not line.strip() or not candidate.exists() or not candidate.is_file():
                    continue
                if candidate in seen:
                    continue
                seen.add(candidate)
                paths.append(candidate)

        return paths

    def _fallback_scan_files(self, root: Path, *, max_files: int) -> list[Path]:
        targets: list[Path] = []
        allowed_ext = {".py", ".js", ".ts", ".tsx", ".sh", ".yml", ".yaml", ".toml", ".json", ".env"}

        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _EXCLUDED_DIRS]
            current = Path(dirpath)

            for filename in filenames:
                if len(targets) >= max_files:
                    return targets
                candidate = current / filename
                if filename.startswith(".") and filename not in {".env", ".env.local", ".env.production"}:
                    continue
                suffix = candidate.suffix.lower()
                if suffix not in allowed_ext and filename not in {"Dockerfile", "Makefile"}:
                    continue
                if candidate.is_file():
                    targets.append(candidate)

        return targets

    def _scan_files(self, root: Path, targets: list[Path]) -> list[SecurityFinding]:
        findings: list[SecurityFinding] = []

        for path in targets:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            rel = self._display_path(path, root)
            file_hits = 0

            for line_no, line in enumerate(text.splitlines(), start=1):
                stripped = line.strip()
                if not stripped:
                    continue

                finding = self._scan_line(rel, line_no, stripped)
                if finding is None:
                    continue

                findings.append(finding)
                file_hits += 1
                if file_hits >= 12:
                    findings.append(
                        SecurityFinding(
                            severity="low",
                            category="scan_limit",
                            file_path=rel,
                            line=line_no,
                            message="Additional findings in this file were suppressed to keep output concise.",
                            recommendation="Run a focused scan on this file for full details.",
                        )
                    )
                    break

            if path.name in {".env", ".env.local", ".env.production"}:
                findings.append(
                    SecurityFinding(
                        severity="medium",
                        category="env_file",
                        file_path=rel,
                        line=0,
                        message="Environment file present in scanned target set.",
                        recommendation="Ensure env files are gitignored and secrets are loaded from secure stores.",
                    )
                )

        findings.extend(self._scan_policy_defaults(root))
        return findings

    def _scan_line(self, rel_path: str, line_no: int, line: str) -> SecurityFinding | None:
        if _PRIVATE_KEY_RE.search(line):
            return SecurityFinding(
                severity="critical",
                category="private_key_material",
                file_path=rel_path,
                line=line_no,
                message="Private key material detected in source.",
                recommendation="Remove the key, rotate affected credentials, and use a secure key store.",
            )

        if _AWS_KEY_RE.search(line) or _GH_TOKEN_RE.search(line):
            return SecurityFinding(
                severity="high",
                category="hardcoded_token",
                file_path=rel_path,
                line=line_no,
                message="High-confidence access token pattern detected.",
                recommendation="Revoke/rotate token and replace with runtime secret injection.",
            )

        if _INLINE_SECRET_RE.search(line):
            return SecurityFinding(
                severity="high",
                category="inline_secret_assignment",
                file_path=rel_path,
                line=line_no,
                message="Potential hardcoded secret assignment detected.",
                recommendation="Move secret values to environment/key-store and commit redacted placeholders only.",
            )

        if _CURL_PIPE_RE.search(line) or _WGET_PIPE_RE.search(line):
            return SecurityFinding(
                severity="high",
                category="remote_script_execution",
                file_path=rel_path,
                line=line_no,
                message="Remote script piping to shell detected.",
                recommendation="Pin downloads by checksum/signature and execute verified local files only.",
            )

        if _RM_ROOT_RE.search(line):
            return SecurityFinding(
                severity="critical",
                category="destructive_shell",
                file_path=rel_path,
                line=line_no,
                message="Potentially destructive shell command detected.",
                recommendation="Remove or guard this command behind explicit safety checks.",
            )

        if _SUBPROCESS_SHELL_RE.search(line):
            return SecurityFinding(
                severity="medium",
                category="subprocess_shell_true",
                file_path=rel_path,
                line=line_no,
                message="subprocess call with shell=True can enable command injection.",
                recommendation="Use argument arrays with shell=False and strict input validation.",
            )

        if _REQUESTS_VERIFY_FALSE_RE.search(line):
            return SecurityFinding(
                severity="medium",
                category="tls_verification_disabled",
                file_path=rel_path,
                line=line_no,
                message="TLS verification disabled in HTTP request.",
                recommendation="Keep TLS verification enabled and install proper CA roots for internal endpoints.",
            )

        return None

    def _scan_policy_defaults(self, root: Path) -> list[SecurityFinding]:
        findings: list[SecurityFinding] = []
        candidates = [
            root / "config" / "settings.toml",
            root / "packages" / "config" / "defaults" / "settings.toml",
        ]

        for path in candidates:
            if not path.exists() or not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            if "enforce_network_policy = false" in text:
                findings.append(
                    SecurityFinding(
                        severity="medium",
                        category="policy_network_permissive",
                        file_path=self._display_path(path, root),
                        line=0,
                        message="Network policy enforcement is disabled by default.",
                        recommendation="Set enforce_network_policy=true in restricted environments.",
                    )
                )

            if "strict_handler_loading = false" in text:
                findings.append(
                    SecurityFinding(
                        severity="low",
                        category="policy_strict_loading_disabled",
                        file_path=self._display_path(path, root),
                        line=0,
                        message="Strict handler loading is disabled.",
                        recommendation="Enable strict_handler_loading to fail fast on unknown context handlers.",
                    )
                )

        return findings

    def _scan_event_log(self, *, run_id: str, working_dir: Path) -> list[SecurityFinding]:
        path = self._resolve_event_log_path(run_id, working_dir)
        if path is None:
            return []

        findings: list[SecurityFinding] = []
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            return findings

        for idx, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue

            for key_path, value in self._iter_key_values(payload):
                if not _SECRET_KEY_RE.search(key_path):
                    continue
                if not isinstance(value, str) or not value.strip():
                    continue
                if value.strip() == "***REDACTED***":
                    continue
                findings.append(
                    SecurityFinding(
                        severity="high",
                        category="unscrubbed_event_secret",
                        file_path=str(path),
                        line=idx,
                        message=f"Event log contains non-redacted sensitive field '{key_path}'.",
                        recommendation="Route event fields through scrub_dict and rotate exposed credentials.",
                    )
                )
                break

        return findings

    def _cache_path(
        self,
        *,
        root: Path,
        input: SecurityAgentInput,
        targets: list[Path],
        run_id: str,
    ) -> Path | None:
        if not input.use_cache:
            return None

        # Cache only static scans. If dynamic evidence tools are enabled we
        # intentionally bypass cache so quality/repo context stays fresh.
        if input.include_quality_gate or input.include_repo_map:
            return None

        event_sig = "none"
        if input.include_event_log_scan and run_id:
            event_sig = self._event_log_signature(run_id=run_id, working_dir=root)

        key = stable_hash(
            {
                "root": str(root),
                "task": input.task,
                "scan_untracked": input.scan_untracked,
                "max_files": input.max_files,
                "max_findings": input.max_findings,
                "include_event_log_scan": input.include_event_log_scan,
                "run_id": run_id if input.include_event_log_scan else "",
                "event_sig": event_sig,
                "targets_sig": self._targets_signature(root=root, targets=targets),
            }
        )
        return cache_file(root, self.name, key)

    def _targets_signature(self, *, root: Path, targets: list[Path]) -> str:
        records: list[dict[str, object]] = []
        for path in targets:
            try:
                stat = path.stat()
            except OSError:
                continue
            records.append(
                {
                    "path": self._display_path(path, root),
                    "size": int(stat.st_size),
                    "mtime_ns": int(stat.st_mtime_ns),
                }
            )
        return stable_hash({"targets": sorted(records, key=lambda r: str(r["path"]))})

    def _event_log_signature(self, *, run_id: str, working_dir: Path) -> str:
        path = self._resolve_event_log_path(run_id, working_dir)
        if path is None:
            return "missing"
        try:
            stat = path.stat()
        except OSError:
            return "unreadable"
        return f"{path}:{int(stat.st_size)}:{int(stat.st_mtime_ns)}"

    def _resolve_event_log_path(self, run_id: str, working_dir: Path) -> Path | None:
        candidates: list[Path] = []

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

    def _iter_key_values(self, obj: object, prefix: str = "") -> list[tuple[str, object]]:
        out: list[tuple[str, object]] = []
        if isinstance(obj, dict):
            for key, value in obj.items():
                name = f"{prefix}.{key}" if prefix else str(key)
                out.extend(self._iter_key_values(value, name))
            return out
        if isinstance(obj, list):
            for idx, value in enumerate(obj):
                name = f"{prefix}[{idx}]"
                out.extend(self._iter_key_values(value, name))
            return out
        out.append((prefix, obj))
        return out

    def _display_path(self, path: Path, root: Path) -> str:
        try:
            return str(path.relative_to(root))
        except ValueError:
            return str(path)

    def _build_report(
        self,
        *,
        task: str,
        root: Path,
        scanned_files: int,
        findings: list[SecurityFinding],
        evidence_sections: list[str],
    ) -> str:
        severity_counts = dict.fromkeys(("critical", "high", "medium", "low"), 0)
        for finding in findings:
            if finding.severity in severity_counts:
                severity_counts[finding.severity] += 1

        lines = [
            f"Security task: {task}",
            f"Working directory: {root}",
            f"Files scanned: {scanned_files}",
            (
                "Severity counts: "
                f"critical={severity_counts['critical']}, high={severity_counts['high']}, "
                f"medium={severity_counts['medium']}, low={severity_counts['low']}"
            ),
        ]

        if evidence_sections:
            lines.extend(["", "Evidence:"])
            for section in evidence_sections:
                lines.append(section)

        lines.extend(["", "Findings:"])
        if not findings:
            lines.append("- No high-confidence security findings detected in the scanned scope.")
        else:
            for finding in findings:
                loc = f"{finding.file_path}:{finding.line}" if finding.line > 0 else finding.file_path
                lines.append(
                    f"- [{finding.severity.upper()}] {loc} ({finding.category}) — {finding.message} "
                    f"Remediation: {finding.recommendation}"
                )

        lines.extend(
            [
                "",
                "Remediation checklist:",
                "- Rotate and revoke any exposed credentials immediately.",
                "- Replace inline secrets with key-store/environment injection.",
                "- Remove remote script piping and destructive shell shortcuts.",
                "- Re-run security_agent after fixes and before release tagging.",
            ]
        )

        return "\n".join(lines)
