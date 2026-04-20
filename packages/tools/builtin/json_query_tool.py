"""JSONQueryTool — dot-path traversal over JSON files or strings."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType


class JSONQueryInput(BaseModel):
    source: str  # file path or raw JSON string
    query: str   # dot-path like "data.items[0].name" or "users[*].email"


class JSONQueryOutput(BaseModel):
    result: Any
    result_type: str
    count: int | None = None  # populated when result is a list


_INDEX_RE = re.compile(r"\[(\d+|\*)\]")


def _traverse(data: Any, path: str) -> Any:
    """Walk dot-path + index notation through parsed JSON."""
    if not path:
        return data

    parts: list[str | int | str] = []
    for segment in path.split("."):
        # split array indices off each segment
        pieces = _INDEX_RE.split(segment)
        for piece in pieces:
            if piece == "":
                continue
            elif piece == "*":
                parts.append("*")
            elif piece.isdigit():
                parts.append(int(piece))
            else:
                parts.append(piece)

    current = data
    for part in parts:
        if part == "*":
            if not isinstance(current, list):
                raise ValueError(f"[*] wildcard applied to non-list: {type(current).__name__}")
            # wildcard — collect all items; next parts applied to each
            remaining_idx = parts.index("*")
            return [_traverse(item, ".".join(str(p) for p in parts[remaining_idx + 1:])) for item in current]
        elif isinstance(part, int):
            if not isinstance(current, list):
                raise ValueError(f"Index [{part}] applied to non-list: {type(current).__name__}")
            current = current[part]
        else:
            if not isinstance(current, dict):
                raise ValueError(f"Key {part!r} applied to non-dict: {type(current).__name__}")
            current = current[part]
    return current


class JSONQueryTool(BaseCallable):
    name = "json_query"
    description = (
        "Extract a value from a JSON file or string using a dot-path query. "
        "Supports array index [n] and wildcard [*]. "
        "Example query: 'data.users[0].name' or 'results[*].id'."
    )
    callable_type = CallableType.TOOL
    input_schema = JSONQueryInput
    output_schema = JSONQueryOutput

    async def _execute(self, input_data: JSONQueryInput, context: object) -> JSONQueryOutput:
        source = input_data.source.strip()
        if source.startswith("{") or source.startswith("["):
            data = json.loads(source)
        else:
            data = json.loads(Path(source).read_text(encoding="utf-8"))

        result = _traverse(data, input_data.query)
        count = len(result) if isinstance(result, list) else None

        return JSONQueryOutput(
            result=result,
            result_type=type(result).__name__,
            count=count,
        )
