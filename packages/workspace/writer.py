"""
WorkspaceWriter — writes generated source files to the workfolder.

Workfolder layout::

    <workfolder>/
    ├── memory/
    ├── agents/
    ├── tools/
    └── workflows/

All filenames are derived from the class name via PascalCase → snake_case
conversion.  Each write is atomic: content is written to a .tmp file then
renamed so partial writes never leave a broken module on disk.
"""

from __future__ import annotations

import os
from pathlib import Path

from citnega.packages.workspace.templates import pascal_to_snake


class WorkspaceWriter:
    """
    Manages file layout inside a single workfolder.

    Args:
        workfolder: Absolute path to the user's workfolder directory.
    """

    _SUBDIRS = ("memory", "agents", "tools", "workflows")

    def __init__(self, workfolder: Path) -> None:
        self._root = Path(workfolder)

    # ── Public API ─────────────────────────────────────────────────────────────

    def ensure_dirs(self) -> None:
        """Create memory/, agents/, tools/, and workflows/ subdirectories if absent."""
        for sub in self._SUBDIRS:
            (self._root / sub).mkdir(parents=True, exist_ok=True)

    def write_tool(self, class_name: str, source: str) -> Path:
        """Write a tool module to tools/<snake_name>.py."""
        return self._write(self._root / "tools", class_name, source)

    def write_agent(self, class_name: str, source: str) -> Path:
        """Write an agent module to agents/<snake_name>.py."""
        return self._write(self._root / "agents", class_name, source)

    def write_workflow(self, class_name: str, source: str) -> Path:
        """Write a workflow module to workflows/<snake_name>.py."""
        return self._write(self._root / "workflows", class_name, source)

    @property
    def root(self) -> Path:
        return self._root

    @property
    def memory_dir(self) -> Path:
        return self._root / "memory"

    @property
    def agents_dir(self) -> Path:
        return self._root / "agents"

    @property
    def tools_dir(self) -> Path:
        return self._root / "tools"

    @property
    def workflows_dir(self) -> Path:
        return self._root / "workflows"

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _write(self, directory: Path, class_name: str, source: str) -> Path:
        """Atomically write ``source`` to ``directory/<filename>.py``."""
        directory.mkdir(parents=True, exist_ok=True)
        filename = self._class_to_filename(class_name) + ".py"
        target = directory / filename
        tmp = target.with_suffix(".tmp")
        try:
            tmp.write_text(source, encoding="utf-8")
            os.replace(tmp, target)  # atomic on POSIX; near-atomic on Windows
        finally:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
        return target

    @staticmethod
    def _class_to_filename(class_name: str) -> str:
        """Convert PascalCase class name to snake_case filename.

        Examples:
            WebScraperTool   → web_scraper_tool
            MySpecialistAgent → my_specialist_agent
        """
        return pascal_to_snake(class_name)
