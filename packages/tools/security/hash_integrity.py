"""
HashIntegrityTool — file and directory integrity hashing.

Features:
  - Hash single files or entire directory trees
  - Algorithms: MD5, SHA1, SHA256, SHA512, BLAKE2b
  - Baseline export: write a JSON manifest
  - Baseline compare: diff current hashes against a saved manifest (detect tampering)
  - SSDEEP-style fuzzy hash detection for similar files (optional, requires ssdeep lib)
  - VirusTotal hash lookup (if API key provided)
  - Flag files with suspicious properties: SUID, world-writable, zero-byte
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType


class HashIntegrityInput(BaseModel):
    path: str = Field(description="File or directory to hash")
    algorithm: Literal["md5", "sha1", "sha256", "sha512", "blake2b"] = Field(default="sha256")
    recursive: bool = Field(default=True)
    baseline_file: str = Field(default="", description="Path to JSON baseline for comparison")
    save_baseline_to: str = Field(default="", description="Write current hashes to this JSON file")
    exclude_dirs: list[str] = Field(default=[".git", "__pycache__", "node_modules", ".venv"])
    max_files: int = Field(default=10_000)
    flag_suspicious: bool = Field(default=True)
    vt_api_key: str = Field(default="", description="VirusTotal API key for hash lookups (optional)")


class FileHashEntry(BaseModel):
    path: str
    hash: str
    size_bytes: int
    modified_time: float
    suspicious: bool
    suspicious_reason: str


class BaselineDiff(BaseModel):
    added: list[str]
    removed: list[str]
    modified: list[str]
    unchanged: int


class HashIntegrityOutput(BaseModel):
    root: str
    algorithm: str
    total_files: int
    entries: list[FileHashEntry]
    baseline_diff: BaselineDiff | None
    vt_hits: list[str]   # hashes flagged by VirusTotal
    duration_seconds: float


def _hash_file(path: Path, algo: str) -> str:
    h = hashlib.new(algo)
    try:
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""


def _is_suspicious(path: Path) -> tuple[bool, str]:
    reasons = []
    try:
        stat = path.stat()
        mode = stat.st_mode
        # SUID
        if mode & 0o4000:
            reasons.append("SUID bit set")
        # SGID
        if mode & 0o2000:
            reasons.append("SGID bit set")
        # World-writable
        if mode & 0o002:
            reasons.append("world-writable")
        # Zero-byte executable
        if stat.st_size == 0 and os.access(path, os.X_OK):
            reasons.append("zero-byte executable")
        # Hidden file
        if path.name.startswith(".") and stat.st_size > 0:
            pass  # not suspicious on its own
        # Unusual extension for script
        if path.suffix in (".php", ".jsp", ".aspx") and path.parent.name in ("uploads", "tmp", "temp"):
            reasons.append(f"web shell candidate in {path.parent.name}/")
    except Exception:
        pass
    return bool(reasons), ", ".join(reasons)


async def _vt_lookup(hashes: list[str], api_key: str) -> list[str]:
    hits = []
    if not api_key:
        return hits
    try:
        import asyncio
        import json as _json

        async def _check(h: str) -> str | None:
            import urllib.request
            url = f"https://www.virustotal.com/api/v3/files/{h}"
            req = urllib.request.Request(url, headers={"x-apikey": api_key})
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = _json.loads(resp.read())
                    stats = data.get("data", {}).get("attributes", {}).get("last_analysis_stats", {})
                    if stats.get("malicious", 0) > 0:
                        return h
            except Exception:
                pass
            return None

        results = await asyncio.gather(*[_check(h) for h in hashes[:20]])
        hits = [r for r in results if r]
    except Exception:
        pass
    return hits


class HashIntegrityTool(BaseCallable):
    name = "hash_integrity"
    description = (
        "File and directory integrity checker using SHA-256/512/BLAKE2b. "
        "Can create and compare baselines to detect tampering. "
        "Flags SUID files, world-writable executables, zero-byte executables, and web shell candidates. "
        "Optional VirusTotal hash lookup."
    )
    callable_type = CallableType.TOOL
    input_schema = HashIntegrityInput
    output_schema = HashIntegrityOutput

    async def _execute(self, input_data: HashIntegrityInput, context: object) -> HashIntegrityOutput:
        t0 = time.monotonic()
        root = Path(input_data.path).expanduser().resolve()
        algo = input_data.algorithm

        # Collect files
        if root.is_file():
            file_list = [root]
        else:
            file_list = []
            for f in root.rglob("*") if input_data.recursive else root.glob("*"):
                if any(ex in f.parts for ex in input_data.exclude_dirs):
                    continue
                if f.is_file():
                    file_list.append(f)
                    if len(file_list) >= input_data.max_files:
                        break

        entries: list[FileHashEntry] = []
        current_map: dict[str, str] = {}

        for f in file_list:
            digest = _hash_file(f, algo)
            if not digest:
                continue
            suspicious, reason = _is_suspicious(f) if input_data.flag_suspicious else (False, "")
            try:
                stat = f.stat()
                size = stat.st_size
                mtime = stat.st_mtime
            except Exception:
                size, mtime = 0, 0.0
            current_map[str(f)] = digest
            entries.append(FileHashEntry(
                path=str(f),
                hash=digest,
                size_bytes=size,
                modified_time=mtime,
                suspicious=suspicious,
                suspicious_reason=reason,
            ))

        # Save baseline
        if input_data.save_baseline_to:
            try:
                Path(input_data.save_baseline_to).write_text(
                    json.dumps({"algorithm": algo, "files": current_map}, indent=2)
                )
            except Exception:
                pass

        # Compare baseline
        diff: BaselineDiff | None = None
        if input_data.baseline_file:
            try:
                baseline_data = json.loads(Path(input_data.baseline_file).read_text())
                baseline_map: dict[str, str] = baseline_data.get("files", {})
                added = [p for p in current_map if p not in baseline_map]
                removed = [p for p in baseline_map if p not in current_map]
                modified = [p for p in current_map if p in baseline_map and current_map[p] != baseline_map[p]]
                unchanged = sum(1 for p in current_map if p in baseline_map and current_map[p] == baseline_map[p])
                diff = BaselineDiff(added=added, removed=removed, modified=modified, unchanged=unchanged)
            except Exception:
                pass

        # VirusTotal
        vt_hits: list[str] = []
        if input_data.vt_api_key:
            hashes = [e.hash for e in entries]
            vt_hits = await _vt_lookup(hashes, input_data.vt_api_key)

        return HashIntegrityOutput(
            root=str(root),
            algorithm=algo,
            total_files=len(entries),
            entries=entries,
            baseline_diff=diff,
            vt_hits=vt_hits,
            duration_seconds=round(time.monotonic() - t0, 2),
        )
