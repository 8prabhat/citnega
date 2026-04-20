"""Verify that StatusBar is no longer referenced in builtin.py (A5)."""

from __future__ import annotations

import sys


def test_statusbar_not_imported_in_builtin() -> None:
    """StatusBar was removed; builtin.py must not reference it."""
    mod_name = "citnega.apps.tui.slash_commands.builtin"
    # Force a clean import
    if mod_name in sys.modules:
        del sys.modules[mod_name]

    import citnega.apps.tui.slash_commands.builtin as builtin_mod

    assert not hasattr(builtin_mod, "StatusBar"), (
        "StatusBar was found as an attribute of builtin.py — it should have been removed"
    )

    # Also verify StatusBar is not in the module's source
    import inspect
    source = inspect.getsource(builtin_mod)
    assert "StatusBar" not in source, (
        "StatusBar string still appears in builtin.py source — dead import was not removed"
    )
