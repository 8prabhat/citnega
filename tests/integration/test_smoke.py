"""Integration smoke tests — verify bootstrap + ApplicationService lifecycle."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_app_creates_and_shuts_down(live_app) -> None:
    """ApplicationService starts and shuts down cleanly."""
    assert live_app is not None
