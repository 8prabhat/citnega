"""dependency_auditor — scan project dependencies for outdated or vulnerable packages."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext

_PYPI_URL = "https://pypi.org/pypi/{package}/json"


class DependencyAuditorInput(BaseModel):
    path: str = Field(
        default="",
        description="Directory to scan (defaults to cwd). Recursively finds dependency files.",
    )
    file_patterns: list[str] = Field(
        default_factory=lambda: ["requirements.txt", "requirements*.txt", "pyproject.toml"],
        description="Glob patterns for dependency files to scan.",
    )
    check_latest: bool = Field(
        default=True,
        description="Check PyPI for the latest version of each package (requires network).",
    )


class DependencyAuditorTool(BaseCallable):
    """Scan requirements files and pyproject.toml for outdated or pinned packages."""

    name = "dependency_auditor"
    description = (
        "Scan project dependency files (requirements.txt, pyproject.toml) and report "
        "packages that are pinned to old versions. Optionally checks PyPI for the "
        "latest available version of each package."
    )
    callable_type = CallableType.TOOL
    input_schema = DependencyAuditorInput
    output_schema = ToolOutput
    policy = tool_policy(
        timeout_seconds=60.0,
        requires_approval=False,
        network_allowed=True,
        max_output_bytes=128 * 1024,
    )

    async def _execute(self, input: DependencyAuditorInput, context: CallContext) -> ToolOutput:
        scan_root = Path(input.path).expanduser().resolve() if input.path else Path.cwd()
        if not scan_root.exists():
            return ToolOutput(result=f"[dependency_auditor: directory not found: {scan_root}]")

        dep_files: list[Path] = []
        for pattern in input.file_patterns:
            dep_files.extend(scan_root.rglob(pattern))
        dep_files = sorted(set(dep_files))

        if not dep_files:
            return ToolOutput(
                result=f"No dependency files found in {scan_root} (patterns: {input.file_patterns})"
            )

        packages: dict[str, str] = {}
        for dep_file in dep_files:
            try:
                self._parse_deps(dep_file, packages)
            except Exception:
                pass

        if not packages:
            return ToolOutput(result="No package dependencies found in the scanned files.")

        rows: list[str] = []
        if input.check_latest:
            try:
                import httpx
                async with httpx.AsyncClient(timeout=10.0) as client:
                    for pkg, pinned_ver in sorted(packages.items()):
                        latest = await self._fetch_latest(client, pkg)
                        flag = ""
                        if latest and pinned_ver and pinned_ver != latest:
                            flag = " ← update available"
                        rows.append(
                            f"  {pkg}=={pinned_ver or '(unpinned)'}"
                            f"  →  latest: {latest or '?'}{flag}"
                        )
            except ImportError:
                rows = [
                    f"  {pkg}=={ver or '(unpinned)'}"
                    for pkg, ver in sorted(packages.items())
                ]
                rows.append("\n[Note: httpx not installed — version comparison skipped]")
        else:
            rows = [
                f"  {pkg}=={ver or '(unpinned)'}"
                for pkg, ver in sorted(packages.items())
            ]

        header = (
            f"Dependency audit: {len(packages)} package(s) found "
            f"across {len(dep_files)} file(s)\n"
            f"Files scanned: {', '.join(f.name for f in dep_files)}\n"
        )
        return ToolOutput(result=header + "\n".join(rows))

    @staticmethod
    def _parse_deps(dep_file: Path, packages: dict[str, str]) -> None:
        text = dep_file.read_text(encoding="utf-8", errors="replace")
        if dep_file.name == "pyproject.toml":
            for match in re.finditer(r'"([A-Za-z0-9_\-]+)\s*([><=!~^][^"]*)"', text):
                pkg, ver = match.group(1).lower(), match.group(2).strip()
                ver = ver.lstrip("=~^><! ").split(",")[0].strip()
                packages.setdefault(pkg, ver)
        else:
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                for sep in ("==", ">=", "<=", "~=", "!=", ">", "<"):
                    if sep in line:
                        pkg, ver = line.split(sep, 1)
                        packages.setdefault(pkg.strip().lower(), ver.split(",")[0].strip())
                        break
                else:
                    if re.match(r"^[A-Za-z0-9_\-]+$", line):
                        packages.setdefault(line.lower(), "")

    @staticmethod
    async def _fetch_latest(client: object, package: str) -> str:
        try:
            import httpx as _httpx

            resp = await client.get(_PYPI_URL.format(package=package))  # type: ignore[attr-defined]
            if resp.status_code == 200:
                data = resp.json()
                return data.get("info", {}).get("version", "")
        except Exception:
            pass
        return ""
