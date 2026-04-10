"""
KB export — write knowledge base items to JSONL or Markdown.

Both formats write to the PathResolver's kb_exports_dir so that the
artifact is accessible at a known location.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from citnega.packages.protocol.models.kb import KBItem


def export_jsonl(items: list[KBItem], dest: Path) -> Path:
    """
    Write *items* to a JSONL file.  One JSON object per line.

    Returns the path of the written file.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8") as fh:
        for item in items:
            fh.write(item.model_dump_json() + "\n")
    return dest


def export_markdown(items: list[KBItem], dest: Path) -> Path:
    """
    Write *items* to a Markdown file.

    Each item becomes an H2 section with its content as a block-quote.
    Returns the path of the written file.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8") as fh:
        fh.write("# Citnega Knowledge Base Export\n\n")
        fh.write(
            f"*Exported: {datetime.now(tz=timezone.utc).isoformat()}*\n\n"
        )
        for item in items:
            fh.write(f"## {item.title}\n\n")
            if item.tags:
                fh.write(f"*Tags: {', '.join(item.tags)}*\n\n")
            fh.write(f"*Type: {item.source_type.value}*\n\n")
            # Indent as a block quote
            quoted = "\n".join(f"> {line}" for line in item.content.splitlines())
            fh.write(quoted + "\n\n")
            fh.write(f"---\n\n")
    return dest


def default_export_path(kb_exports_dir: Path, fmt: str = "jsonl") -> Path:
    """Return a timestamped export path inside *kb_exports_dir*."""
    stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S")
    return kb_exports_dir / f"kb_export_{stamp}.{fmt}"
