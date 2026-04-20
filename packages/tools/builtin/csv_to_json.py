"""csv_to_json — convert a CSV file to JSON using stdlib only."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext

_VALID_ORIENTS = {"records", "columns", "index"}


class CSVToJSONInput(BaseModel):
    file_path: str = Field(description="Path to the CSV file to convert.")
    orient: str = Field(
        default="records",
        description=(
            "JSON structure: "
            "records = [{col: val, ...}, ...] (list of row dicts), "
            "columns = {col: [val, ...], ...} (column arrays), "
            "index = {row_idx: {col: val}, ...} (dict keyed by row number)."
        ),
    )
    output_path: str = Field(default="", description="Optional path to write the JSON file. If empty, returns JSON inline.")
    max_rows: int = Field(default=0, description="Max rows to convert (0 = all).")
    encoding: str = Field(default="utf-8", description="CSV file encoding.")
    delimiter: str = Field(default=",", description="CSV delimiter character.")


class CSVToJSONTool(BaseCallable):
    """Convert a CSV file to JSON. Uses stdlib csv + json — no external dependencies."""

    name = "csv_to_json"
    description = (
        "Convert a CSV file to JSON. "
        "Orient options: records (list of row dicts), columns (column arrays), index (row-indexed dict). "
        "Returns JSON inline or writes to a file. Pure stdlib — no pandas required."
    )
    callable_type = CallableType.TOOL
    input_schema = CSVToJSONInput
    output_schema = ToolOutput
    policy = tool_policy(
        timeout_seconds=30.0,
        requires_approval=False,
        network_allowed=False,
    )

    async def _execute(self, input: CSVToJSONInput, context: CallContext) -> ToolOutput:
        orient = input.orient.lower().strip()
        if orient not in _VALID_ORIENTS:
            return ToolOutput(result=f"[csv_to_json: unknown orient '{orient}'. Valid: records | columns | index]")

        path = Path(input.file_path).expanduser().resolve()
        if not path.exists():
            return ToolOutput(result=f"[csv_to_json: file not found: {path}]")

        try:
            with path.open(encoding=input.encoding, newline="") as f:
                reader = csv.DictReader(f, delimiter=input.delimiter)
                rows: list[dict[str, Any]] = []
                for i, row in enumerate(reader):
                    if input.max_rows and i >= input.max_rows:
                        break
                    rows.append(dict(row))
        except Exception as exc:
            return ToolOutput(result=f"[csv_to_json: read error: {exc}]")

        if not rows:
            return ToolOutput(result="[csv_to_json: CSV is empty or has no data rows]")

        if orient == "records":
            data = rows
        elif orient == "columns":
            cols = list(rows[0].keys())
            data = {col: [r.get(col) for r in rows] for col in cols}  # type: ignore[assignment]
        else:  # index
            data = {str(i): row for i, row in enumerate(rows)}  # type: ignore[assignment]

        try:
            json_str = json.dumps(data, ensure_ascii=False, indent=2)
        except Exception as exc:
            return ToolOutput(result=f"[csv_to_json: JSON serialisation error: {exc}]")

        if input.output_path:
            out = Path(input.output_path).expanduser().resolve()
            out.parent.mkdir(parents=True, exist_ok=True)
            try:
                out.write_text(json_str, encoding="utf-8")
                return ToolOutput(result=f"JSON written: {out}  ({len(rows)} rows, orient={orient})")
            except Exception as exc:
                return ToolOutput(result=f"[csv_to_json: write error: {exc}]")

        # Return inline (cap at 100 rows to avoid flooding context)
        if len(rows) > 100:
            preview_data = rows[:100] if orient == "records" else data
            preview_str = json.dumps(preview_data, ensure_ascii=False, indent=2)
            return ToolOutput(result=f"{len(rows)} rows converted (showing first 100):\n{preview_str}")

        return ToolOutput(result=f"{len(rows)} rows converted (orient={orient}):\n{json_str}")
