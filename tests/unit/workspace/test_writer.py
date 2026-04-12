"""Unit tests for workspace/writer.py"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from citnega.packages.workspace.writer import WorkspaceWriter

if TYPE_CHECKING:
    from pathlib import Path


class TestWorkspaceWriter:
    def test_ensure_dirs_creates_subdirectories(self, tmp_path: Path) -> None:
        w = WorkspaceWriter(tmp_path)
        w.ensure_dirs()
        assert (tmp_path / "memory").is_dir()
        assert (tmp_path / "agents").is_dir()
        assert (tmp_path / "tools").is_dir()
        assert (tmp_path / "workflows").is_dir()

    def test_ensure_dirs_idempotent(self, tmp_path: Path) -> None:
        w = WorkspaceWriter(tmp_path)
        w.ensure_dirs()
        w.ensure_dirs()  # second call must not raise

    def test_write_tool_creates_file(self, tmp_path: Path) -> None:
        w = WorkspaceWriter(tmp_path)
        w.ensure_dirs()
        path = w.write_tool("MyTool", "# source\n")
        assert path.exists()
        assert path.name == "my_tool.py"
        assert path.parent == tmp_path / "tools"

    def test_write_agent_creates_file(self, tmp_path: Path) -> None:
        w = WorkspaceWriter(tmp_path)
        w.ensure_dirs()
        path = w.write_agent("ResearchAgent", "# source\n")
        assert path.exists()
        assert path.name == "research_agent.py"

    def test_write_workflow_creates_file(self, tmp_path: Path) -> None:
        w = WorkspaceWriter(tmp_path)
        w.ensure_dirs()
        path = w.write_workflow("DataPipelineWorkflow", "# source\n")
        assert path.exists()
        assert path.name == "data_pipeline_workflow.py"

    def test_write_creates_parent_dirs(self, tmp_path: Path) -> None:
        w = WorkspaceWriter(tmp_path)
        # Do NOT call ensure_dirs — write should create parent automatically
        path = w.write_tool("MyTool", "# source\n")
        assert path.exists()

    def test_write_file_content(self, tmp_path: Path) -> None:
        w = WorkspaceWriter(tmp_path)
        source = "class MyTool:\n    name = 'my_tool'\n"
        path = w.write_tool("MyTool", source)
        assert path.read_text(encoding="utf-8") == source

    def test_overwrite_replaces_content(self, tmp_path: Path) -> None:
        w = WorkspaceWriter(tmp_path)
        w.write_tool("MyTool", "version 1\n")
        w.write_tool("MyTool", "version 2\n")
        path = tmp_path / "tools" / "my_tool.py"
        assert path.read_text() == "version 2\n"

    @pytest.mark.parametrize(
        "class_name,expected",
        [
            ("WebScraperTool", "web_scraper_tool"),
            ("ResearchAgent", "research_agent"),
            ("DataPipeline", "data_pipeline"),
            ("SimpleClass", "simple_class"),
        ],
    )
    def test_class_to_filename(self, class_name: str, expected: str) -> None:
        assert WorkspaceWriter._class_to_filename(class_name) == expected

    def test_root_property(self, tmp_path: Path) -> None:
        w = WorkspaceWriter(tmp_path)
        assert w.root == tmp_path
        assert w.memory_dir == tmp_path / "memory"
        assert w.agents_dir == tmp_path / "agents"
        assert w.tools_dir == tmp_path / "tools"
        assert w.workflows_dir == tmp_path / "workflows"
