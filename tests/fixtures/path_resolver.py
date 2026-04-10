"""PathResolver fixture using a temp directory."""

from __future__ import annotations

from pathlib import Path

import pytest

from citnega.packages.storage.path_resolver import PathResolver


@pytest.fixture
def tmp_path_resolver(tmp_path: Path) -> PathResolver:
    """A PathResolver backed by a temporary directory."""
    resolver = PathResolver(app_home=tmp_path)
    resolver.create_all()
    return resolver
