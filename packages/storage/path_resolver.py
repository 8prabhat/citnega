"""
PathResolver — the single authority for all application paths.

This is the ONLY module that imports ``platformdirs``.
All other packages call PathResolver to construct paths.
"""

from __future__ import annotations

from pathlib import Path

import platformdirs  # only imported here — enforced by import-linter

from citnega.packages.security.permissions import ensure_dir_permissions

APP_NAME    = "citnega"
APP_AUTHOR  = "citnega"


class PathResolver:
    """
    Resolves platform-appropriate paths for the Citnega app home.

    On first call to ``create_all()``, creates all required directories
    and applies 0700 permissions on Unix.
    """

    def __init__(self, app_home: Path | None = None) -> None:
        """
        Args:
            app_home: Override the app home directory (used in tests).
                      If None, uses platformdirs to determine the OS-default.
        """
        if app_home is not None:
            self._app_home = app_home
        else:
            self._app_home = Path(
                platformdirs.user_data_dir(APP_NAME, APP_AUTHOR)
            )

    @property
    def app_home(self) -> Path:
        return self._app_home

    @property
    def config_dir(self) -> Path:
        return self._app_home / "config"

    @property
    def db_dir(self) -> Path:
        return self._app_home / "db"

    @property
    def db_path(self) -> Path:
        return self.db_dir / "citnega.db"

    @property
    def logs_dir(self) -> Path:
        return self._app_home / "logs"

    @property
    def app_logs_dir(self) -> Path:
        return self.logs_dir / "app"

    @property
    def event_logs_dir(self) -> Path:
        return self.logs_dir / "events"

    @property
    def sessions_dir(self) -> Path:
        return self._app_home / "sessions"

    @property
    def artifacts_dir(self) -> Path:
        return self._app_home / "artifacts"

    @property
    def kb_dir(self) -> Path:
        return self._app_home / "kb"

    @property
    def kb_raw_dir(self) -> Path:
        return self.kb_dir / "raw"

    @property
    def kb_exports_dir(self) -> Path:
        return self.kb_dir / "exports"

    @property
    def checkpoints_dir(self) -> Path:
        return self._app_home / "checkpoints"

    @property
    def exports_dir(self) -> Path:
        return self._app_home / "exports"

    def session_dir(self, session_id: str) -> Path:
        return self.sessions_dir / session_id

    def artifact_dir(self, session_id: str, run_id: str) -> Path:
        return self.artifacts_dir / session_id / run_id

    def checkpoint_dir(self, session_id: str) -> Path:
        return self.checkpoints_dir / session_id

    def event_log_path(self, run_id: str) -> Path:
        return self.event_logs_dir / f"{run_id}.jsonl"

    def alembic_ini_path(self) -> Path:
        """Path to the Alembic ini relative to storage package."""
        from pathlib import Path as P
        return P(__file__).parent / "migrations" / "alembic.ini"

    def create_all(self) -> None:
        """Create all required directories with proper permissions."""
        dirs = [
            self.app_home,
            self.config_dir,
            self.db_dir,
            self.logs_dir,
            self.app_logs_dir,
            self.event_logs_dir,
            self.sessions_dir,
            self.artifacts_dir,
            self.kb_dir,
            self.kb_raw_dir,
            self.kb_exports_dir,
            self.checkpoints_dir,
            self.exports_dir,
        ]
        for d in dirs:
            ensure_dir_permissions(d, mode=0o700)

    def resolve_path_template(self, template: str, session_id: str) -> str:
        """Replace ${SESSION_ID} in path templates used in tool policies."""
        return template.replace("${SESSION_ID}", session_id)
