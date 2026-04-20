"""repo_map — lightweight repository architecture mapper."""

from __future__ import annotations

from collections import Counter
import os
from pathlib import Path
import re
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.shared.errors import CallableError
from citnega.packages.tools.builtin._cache_utils import (
    cache_file,
    file_tree_signature,
    git_state_fingerprint,
    load_json_cache,
    stable_hash,
    write_json_cache,
)
from citnega.packages.tools.builtin._tool_base import tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class RepoMapInput(BaseModel):
    root_path: str = Field(
        default="",
        description="Repository root. Empty means current working directory.",
    )
    include_tests: bool = Field(
        default=True,
        description="When false, excludes files under test/tests directories.",
    )
    max_files: int = Field(
        default=5000,
        description="Maximum number of Python files to inspect.",
    )
    max_hotspots: int = Field(
        default=15,
        description="How many largest files by line-count to include.",
    )
    max_edges: int = Field(
        default=20,
        description="How many import edges to include in the output.",
    )
    use_cache: bool = Field(
        default=True,
        description="When true, reuses cached repo_map results if repository state is unchanged.",
    )
    cache_ttl_seconds: int = Field(
        default=300,
        description="Cache entry TTL in seconds. 0 disables expiration.",
    )


class RepoMapOutput(BaseModel):
    root_path: str
    total_files_scanned: int
    python_files_scanned: int
    top_modules: list[str]
    hotspots: list[str]
    import_edges: list[str]
    detected_stacks: list[str] = []
    cache_hit: bool = False
    summary: str


class RepoMapTool(BaseCallable):
    name = "repo_map"
    description = (
        "Generate a lightweight architecture map for a repository: module distribution, "
        "largest Python files, and top local import edges."
    )
    callable_type = CallableType.TOOL
    input_schema = RepoMapInput
    output_schema = RepoMapOutput
    policy = tool_policy(
        timeout_seconds=60.0,
        requires_approval=False,
        network_allowed=False,
        max_output_bytes=512 * 1024,
    )

    _EXCLUDE_DIRS = frozenset(
        {
            ".git",
            ".hg",
            ".svn",
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
    )

    _IMPORT_RE = re.compile(r"^\s*import\s+([a-zA-Z_]\w*(?:\.[\w]+)*)")
    _FROM_RE = re.compile(r"^\s*from\s+([a-zA-Z_]\w*(?:\.[\w]+)*)\s+import\s+")

    async def _execute(self, input: RepoMapInput, context: CallContext) -> RepoMapOutput:
        root = Path(input.root_path or os.getcwd()).expanduser().resolve()
        if not root.exists():
            raise CallableError(f"Root path does not exist: {root}")
        if not root.is_dir():
            raise CallableError(f"Root path is not a directory: {root}")

        cache_path: Path | None = None
        if input.use_cache:
            cache_path = cache_file(root, self.name, self._cache_key(root, input))
            cached = load_json_cache(
                cache_path,
                ttl_seconds=max(0, input.cache_ttl_seconds),
            )
            if cached:
                try:
                    out = RepoMapOutput.model_validate(cached)
                    return out.model_copy(
                        update={
                            "cache_hit": True,
                            "summary": f"{out.summary} (cache hit)",
                        }
                    )
                except Exception:
                    pass

        module_counts: Counter[str] = Counter()
        hotspot_candidates: list[tuple[int, str]] = []
        edge_counts: Counter[tuple[str, str]] = Counter()

        total_files = 0
        py_files = 0

        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in self._EXCLUDE_DIRS]
            current_dir = Path(dirpath)
            rel_dir = current_dir.relative_to(root)
            if not input.include_tests and any(part in {"test", "tests"} for part in rel_dir.parts):
                continue

            for filename in filenames:
                total_files += 1
                if not filename.endswith(".py"):
                    continue

                file_path = current_dir / filename
                rel_file = file_path.relative_to(root)

                if not input.include_tests and any(part in {"test", "tests"} for part in rel_file.parts):
                    continue
                if py_files >= max(1, input.max_files):
                    break

                py_files += 1
                owner = rel_file.parts[0] if len(rel_file.parts) > 1 else "root"
                module_counts[owner] += 1

                try:
                    text = file_path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue

                line_count = text.count("\n") + 1
                hotspot_candidates.append((line_count, str(rel_file)))
                self._extract_edges(text, owner, edge_counts)

            if py_files >= max(1, input.max_files):
                break

        top_modules = [
            f"{name}:{count}"
            for name, count in module_counts.most_common(10)
        ]
        hotspots = [
            f"{path}:{line_count} lines"
            for line_count, path in sorted(hotspot_candidates, reverse=True)[: max(1, input.max_hotspots)]
        ]
        import_edges = [
            f"{src}->{dst}:{count}"
            for (src, dst), count in edge_counts.most_common(max(1, input.max_edges))
        ]

        summary = (
            f"Scanned {total_files} files ({py_files} Python) under {root}. "
            f"Top module={top_modules[0] if top_modules else 'n/a'}. "
            f"Hotspots={len(hotspots)}. Import edges={len(import_edges)}."
        )

        detected_stacks = self._detect_stacks(root)
        if detected_stacks:
            summary += f" Stacks: {', '.join(detected_stacks)}."

        out = RepoMapOutput(
            root_path=str(root),
            total_files_scanned=total_files,
            python_files_scanned=py_files,
            top_modules=top_modules,
            hotspots=hotspots,
            import_edges=import_edges,
            detected_stacks=detected_stacks,
            summary=summary,
        )
        if cache_path is not None:
            write_json_cache(cache_path, out.model_dump())
        return out

    def _cache_key(self, root: Path, input: RepoMapInput) -> str:
        fingerprint = git_state_fingerprint(root) or self._filesystem_fingerprint(root, input)
        return stable_hash(
            {
                "tool": self.name,
                "root": str(root),
                "include_tests": input.include_tests,
                "max_files": input.max_files,
                "max_hotspots": input.max_hotspots,
                "max_edges": input.max_edges,
                "fingerprint": fingerprint,
            }
        )

    def _filesystem_fingerprint(self, root: Path, input: RepoMapInput) -> str:
        include_tests = input.include_tests
        return file_tree_signature(
            root=root,
            max_files=max(1, input.max_files),
            exclude_dirs=self._EXCLUDE_DIRS,
            matcher=lambda candidate: (
                candidate.suffix == ".py"
                and (include_tests or not self._is_test_path(candidate, root))
            ),
        )

    @staticmethod
    def _detect_stacks(root: Path) -> list[str]:
        """Detect technology stacks present in the repository root."""
        stacks: list[str] = []
        markers = {
            "python": ["pyproject.toml", "setup.py", "setup.cfg", "requirements.txt"],
            "node": ["package.json"],
            "go": ["go.mod"],
            "rust": ["Cargo.toml"],
            "java": ["pom.xml", "build.gradle", "build.gradle.kts"],
            "ruby": ["Gemfile"],
            "dotnet": ["*.csproj", "*.sln"],
        }
        for stack, files in markers.items():
            for marker in files:
                if "*" in marker:
                    # glob pattern
                    if any(root.glob(marker)):
                        stacks.append(stack)
                        break
                elif (root / marker).exists():
                    stacks.append(stack)
                    break
        return stacks

    @staticmethod
    def _is_test_path(path: Path, root: Path) -> bool:
        try:
            rel = path.relative_to(root)
        except ValueError:
            rel = path
        return any(part in {"test", "tests"} for part in rel.parts)

    def _extract_edges(
        self,
        text: str,
        owner: str,
        edge_counts: Counter[tuple[str, str]],
    ) -> None:
        for line in text.splitlines():
            target = ""
            m_from = self._FROM_RE.match(line)
            if m_from:
                target = m_from.group(1)
            else:
                m_import = self._IMPORT_RE.match(line)
                if m_import:
                    target = m_import.group(1)

            if not target:
                continue
            top_level = target.split(".", 1)[0]
            if top_level == owner:
                continue
            edge_counts[(owner, top_level)] += 1
