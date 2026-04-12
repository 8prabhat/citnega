"""PathResolver fixture using a temp directory."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from citnega.packages.storage.path_resolver import PathResolver

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def tmp_path_resolver(tmp_path: Path) -> PathResolver:
    """A PathResolver backed by a temporary directory."""
    resolver = PathResolver(app_home=tmp_path)
    resolver.create_all()
    return resolver
