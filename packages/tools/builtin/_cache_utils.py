"""Small cache helpers shared by repository introspection tools."""

from __future__ import annotations

from collections.abc import Callable
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any


def cache_file(root: Path, tool_name: str, key: str) -> Path:
    return root / ".citnega_cache" / tool_name / f"{key}.json"


def stable_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()


def load_json_cache(path: Path, *, ttl_seconds: int) -> dict[str, Any] | None:
    try:
        if not path.exists() or not path.is_file():
            return None
        age_s = time.time() - path.stat().st_mtime
        if ttl_seconds > 0 and age_s > ttl_seconds:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def write_json_cache(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, separators=(",", ":"), default=str), encoding="utf-8")
    tmp.replace(path)


def git_state_fingerprint(root: Path) -> str | None:
    try:
        head = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=6,
        )
        if head.returncode != 0:
            return None

        status = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        status_text = status.stdout if status.returncode == 0 else ""
        status_hash = hashlib.sha256(status_text.encode("utf-8", errors="replace")).hexdigest()[:16]

        return f"git:{head.stdout.strip()}:{status_hash}"
    except Exception:
        return None


def file_tree_signature(
    *,
    root: Path,
    matcher: Callable[[Path], bool],
    max_files: int,
    exclude_dirs: set[str] | frozenset[str] | None = None,
) -> str:
    max_files = max(1, max_files)
    excludes = set(exclude_dirs or ())

    count = 0
    total_size = 0
    max_mtime_ns = 0
    sample_paths: list[str] = []

    for dirpath, dirnames, filenames in os.walk(root):
        if excludes:
            dirnames[:] = [d for d in dirnames if d not in excludes]
        current = Path(dirpath)

        for filename in filenames:
            candidate = current / filename
            if not matcher(candidate):
                continue

            try:
                st = candidate.stat()
            except OSError:
                continue

            count += 1
            total_size += int(st.st_size)
            max_mtime_ns = max(max_mtime_ns, int(st.st_mtime_ns))
            if len(sample_paths) < 16:
                try:
                    sample_paths.append(str(candidate.relative_to(root)))
                except ValueError:
                    sample_paths.append(candidate.name)

            if count >= max_files:
                break

        if count >= max_files:
            break

    return stable_hash(
        {
            "count": count,
            "size": total_size,
            "mtime": max_mtime_ns,
            "samples": sample_paths,
        }
    )
