"""
File permission enforcement helpers.

On Unix-like systems, applies mode 0700 to directories and 0600 to files.
On Windows, this is a no-op (the OS credential manager handles secrets,
and NTFS ACLs are set at directory creation by the OS).
"""

from __future__ import annotations

import contextlib
import os
import stat
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def is_unix() -> bool:
    return sys.platform != "win32"


def ensure_dir_permissions(path: Path, mode: int = 0o700) -> None:
    """
    Create directory (and parents) if missing, then enforce permissions.

    On Windows: only creates the directory, does not apply mode.
    """
    path.mkdir(parents=True, exist_ok=True)
    if is_unix():
        try:
            os.chmod(path, mode)
        except PermissionError:
            pass  # Best-effort — already-created dirs may be owned by another user


def ensure_file_permissions(path: Path, mode: int = 0o600) -> None:
    """
    Enforce file permissions.

    On Windows: no-op.
    """
    if is_unix() and path.exists():
        with contextlib.suppress(PermissionError):
            os.chmod(path, mode)


def check_dir_permissions(path: Path, expected_mode: int = 0o700) -> bool:
    """Return True if the directory has at most the expected permissions."""
    if not is_unix() or not path.exists():
        return True
    current = stat.S_IMODE(path.stat().st_mode)
    return (current & ~expected_mode) == 0


def check_file_permissions(path: Path, expected_mode: int = 0o600) -> bool:
    """Return True if the file has at most the expected permissions."""
    if not is_unix() or not path.exists():
        return True
    current = stat.S_IMODE(path.stat().st_mode)
    return (current & ~expected_mode) == 0


def secure_write(path: Path, content: str | bytes) -> None:
    """
    Write to a file and immediately restrict permissions to 0600.

    Creates parent directories with 0700 if needed.
    """
    ensure_dir_permissions(path.parent)
    if isinstance(content, str):
        path.write_text(content, encoding="utf-8")
    else:
        path.write_bytes(content)
    ensure_file_permissions(path)
