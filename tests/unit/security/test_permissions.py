"""Unit tests for permissions module."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest

from citnega.packages.security.permissions import (
    check_dir_permissions,
    check_file_permissions,
    ensure_dir_permissions,
    ensure_file_permissions,
    secure_write,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestDirectoryPermissions:
    def test_creates_directory(self, tmp_path: Path) -> None:
        target = tmp_path / "new_dir"
        ensure_dir_permissions(target)
        assert target.is_dir()

    def test_creates_nested_directories(self, tmp_path: Path) -> None:
        target = tmp_path / "a" / "b" / "c"
        ensure_dir_permissions(target)
        assert target.is_dir()

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix only")
    def test_applies_mode_on_unix(self, tmp_path: Path) -> None:
        target = tmp_path / "restricted"
        ensure_dir_permissions(target, mode=0o700)
        assert check_dir_permissions(target, 0o700)


class TestFilePermissions:
    @pytest.mark.skipif(sys.platform == "win32", reason="Unix only")
    def test_applies_0600_on_unix(self, tmp_path: Path) -> None:
        f = tmp_path / "secret.txt"
        f.write_text("secret")
        ensure_file_permissions(f, mode=0o600)
        assert check_file_permissions(f, 0o600)


class TestSecureWrite:
    def test_creates_file_with_content(self, tmp_path: Path) -> None:
        target = tmp_path / "sub" / "file.txt"
        secure_write(target, "hello world")
        assert target.read_text() == "hello world"

    def test_writes_bytes(self, tmp_path: Path) -> None:
        target = tmp_path / "data.bin"
        secure_write(target, b"\x00\x01\x02")
        assert target.read_bytes() == b"\x00\x01\x02"

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix only")
    def test_file_has_0600_permissions(self, tmp_path: Path) -> None:
        target = tmp_path / "secure.txt"
        secure_write(target, "data")
        assert check_file_permissions(target, 0o600)
