"""
ArtifactStore — filesystem-backed implementation of IArtifactStore.

All paths are resolved via PathResolver. Files are created with 0600
permissions via secure_write.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

from citnega.packages.protocol.interfaces.artifact_store import IArtifactStore
from citnega.packages.security.permissions import ensure_dir_permissions, ensure_file_permissions
from citnega.packages.shared.errors import ArtifactError

if TYPE_CHECKING:
    from pathlib import Path

    from citnega.packages.storage.path_resolver import PathResolver


class ArtifactStore(IArtifactStore):
    def __init__(self, path_resolver: PathResolver) -> None:
        self._root = path_resolver.artifacts_dir

    def _resolve(self, path: str) -> Path:
        """Resolve a relative artifact path against the artifacts root."""
        resolved = (self._root / path).resolve()
        # Security: must remain under artifacts root
        try:
            resolved.relative_to(self._root.resolve())
        except ValueError as exc:
            raise ArtifactError(f"Artifact path escapes root: {path!r}") from exc
        return resolved

    async def put_text(self, path: str, content: str) -> Path:
        full = self._resolve(path)
        await asyncio.to_thread(self._write, full, content.encode("utf-8"))
        return full

    async def put_json(self, path: str, data: dict[str, object]) -> Path:
        full = self._resolve(path)
        content = json.dumps(data, indent=2).encode("utf-8")
        await asyncio.to_thread(self._write, full, content)
        return full

    async def put_bytes(self, path: str, content: bytes) -> Path:
        full = self._resolve(path)
        await asyncio.to_thread(self._write, full, content)
        return full

    async def get(self, path: str) -> bytes:
        full = self._resolve(path)
        try:
            return await asyncio.to_thread(full.read_bytes)
        except FileNotFoundError as exc:
            raise ArtifactError(f"Artifact not found: {path!r}") from exc

    async def exists(self, path: str) -> bool:
        return self._resolve(path).exists()

    async def delete(self, path: str) -> None:
        full = self._resolve(path)
        try:
            await asyncio.to_thread(full.unlink, True)
        except Exception as exc:
            raise ArtifactError(
                f"Failed to delete artifact: {path!r}: {exc}", original=exc
            ) from exc

    @staticmethod
    def _write(full: Path, content: bytes) -> None:
        ensure_dir_permissions(full.parent)
        full.write_bytes(content)
        ensure_file_permissions(full)
