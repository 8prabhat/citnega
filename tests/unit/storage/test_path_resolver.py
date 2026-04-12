"""Unit tests for PathResolver."""

from __future__ import annotations

from typing import TYPE_CHECKING

from citnega.packages.storage.path_resolver import PathResolver

if TYPE_CHECKING:
    from pathlib import Path


class TestPathResolver:
    def test_custom_app_home(self, tmp_path: Path) -> None:
        resolver = PathResolver(app_home=tmp_path)
        assert resolver.app_home == tmp_path

    def test_derived_paths(self, tmp_path: Path) -> None:
        resolver = PathResolver(app_home=tmp_path)
        assert resolver.db_dir == tmp_path / "db"
        assert resolver.db_path == tmp_path / "db" / "citnega.db"
        assert resolver.logs_dir == tmp_path / "logs"
        assert resolver.kb_dir == tmp_path / "kb"
        assert resolver.checkpoints_dir == tmp_path / "checkpoints"

    def test_create_all_creates_directories(self, tmp_path: Path) -> None:
        resolver = PathResolver(app_home=tmp_path)
        resolver.create_all()
        assert resolver.db_dir.is_dir()
        assert resolver.logs_dir.is_dir()
        assert resolver.app_logs_dir.is_dir()
        assert resolver.event_logs_dir.is_dir()
        assert resolver.kb_raw_dir.is_dir()
        assert resolver.checkpoints_dir.is_dir()

    def test_workfolder_moves_runtime_data_under_memory(self, tmp_path: Path) -> None:
        workfolder = tmp_path / "workfolder"
        resolver = PathResolver(app_home=tmp_path / "app-home", workfolder_root=workfolder)
        resolver.create_all()

        assert resolver.memory_dir == workfolder / "memory"
        assert resolver.db_dir == workfolder / "memory" / "db"
        assert resolver.logs_dir == workfolder / "memory" / "logs"
        assert resolver.sessions_dir == workfolder / "memory" / "sessions"
        assert resolver.workspace_agents_dir == workfolder / "agents"
        assert resolver.workspace_tools_dir == workfolder / "tools"
        assert resolver.workspace_workflows_dir == workfolder / "workflows"
        assert resolver.workspace_agents_dir.is_dir()
        assert resolver.workspace_tools_dir.is_dir()
        assert resolver.workspace_workflows_dir.is_dir()

    def test_session_dir(self, tmp_path: Path) -> None:
        resolver = PathResolver(app_home=tmp_path)
        assert resolver.session_dir("my-session") == tmp_path / "sessions" / "my-session"

    def test_artifact_dir(self, tmp_path: Path) -> None:
        resolver = PathResolver(app_home=tmp_path)
        d = resolver.artifact_dir("session-1", "run-1")
        assert d == tmp_path / "artifacts" / "session-1" / "run-1"

    def test_event_log_path(self, tmp_path: Path) -> None:
        resolver = PathResolver(app_home=tmp_path)
        p = resolver.event_log_path("run-abc")
        assert p.name == "run-abc.jsonl"
        assert p.parent == resolver.event_logs_dir

    def test_path_template_substitution(self, tmp_path: Path) -> None:
        resolver = PathResolver(app_home=tmp_path)
        result = resolver.resolve_path_template("~/citnega/${SESSION_ID}/output", "my-session")
        assert result == "~/citnega/my-session/output"

    def test_alembic_ini_exists(self, tmp_path: Path) -> None:
        resolver = PathResolver(app_home=tmp_path)
        ini = resolver.alembic_ini_path()
        assert ini.exists(), f"alembic.ini not found at {ini}"
