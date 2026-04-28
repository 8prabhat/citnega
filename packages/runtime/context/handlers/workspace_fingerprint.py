"""WorkspaceFingerprintHandler — injects a compact project-type fingerprint once per session."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from citnega.packages.observability.logging_setup import runtime_logger
from citnega.packages.protocol.interfaces.context import IContextHandler
from citnega.packages.protocol.models.context import ContextObject, ContextSource

if TYPE_CHECKING:
    from citnega.packages.protocol.models.sessions import Session


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class WorkspaceFingerprintHandler(IContextHandler):
    """
    Scans the workfolder once per session to detect project type, main language,
    and CI configuration. Injects a compact fingerprint (≤20 tokens) into every
    system prompt so the LLM knows the project context without a repo_map call.

    Results are cached per session_id — subsequent turns are O(1).
    """

    parallel_safe = True

    @property
    def name(self) -> str:
        return "workspace_fingerprint"

    def __init__(self, workfolder_root: str = "") -> None:
        self._workfolder_root = workfolder_root
        self._cache: dict[str, str] = {}

    async def enrich(self, context: ContextObject, session: Session) -> ContextObject:
        session_id = session.config.session_id

        if session_id in self._cache:
            fingerprint = self._cache[session_id]
        else:
            fingerprint = self._scan(session)
            self._cache[session_id] = fingerprint

        if not fingerprint:
            return context

        token_count = _estimate_tokens(fingerprint)
        source = ContextSource(
            source_type="state",
            content=fingerprint,
            token_count=token_count,
            metadata={"handler": "workspace_fingerprint"},
        )

        runtime_logger.debug(
            "workspace_fingerprint_injected",
            session_id=session_id,
            fingerprint=fingerprint[:80],
        )

        return context.model_copy(
            update={
                "sources": [*context.sources, source],
                "total_tokens": context.total_tokens + token_count,
                "budget_remaining": context.budget_remaining - token_count,
            }
        )

    def _scan(self, session: Session) -> str:
        root_candidates: list[Path] = []

        if self._workfolder_root:
            root_candidates.append(Path(self._workfolder_root))

        workfolder = getattr(session.config, "workfolder_path", None)
        if workfolder:
            root_candidates.append(Path(workfolder))

        for root in root_candidates:
            if root.is_dir():
                return self._fingerprint(root)

        return ""

    def _fingerprint(self, root: Path) -> str:
        parts: list[str] = []

        # Language / framework detection
        if (root / "pyproject.toml").exists():
            parts.append("Python/pyproject")
        elif (root / "setup.py").exists() or (root / "requirements.txt").exists():
            parts.append("Python")

        if (root / "package.json").exists():
            parts.append("Node.js")

        if (root / "go.mod").exists():
            parts.append("Go")

        if (root / "Cargo.toml").exists():
            parts.append("Rust")

        if (root / "pom.xml").exists() or (root / "build.gradle").exists():
            parts.append("Java/JVM")

        # Container/infra
        if (root / "Dockerfile").exists():
            parts.append("Docker")

        if (root / "docker-compose.yml").exists() or (root / "docker-compose.yaml").exists():
            parts.append("Compose")

        # CI
        gh_workflows = root / ".github" / "workflows"
        if gh_workflows.is_dir() and any(gh_workflows.glob("*.yml")):
            parts.append("GitHub Actions")

        if (root / ".gitlab-ci.yml").exists():
            parts.append("GitLab CI")

        if (root / "Makefile").exists():
            parts.append("Make")

        if not parts:
            return ""

        return f"Project: {', '.join(parts)}"
