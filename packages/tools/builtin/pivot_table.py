"""pivot_table — build a pivot table from a CSV/Excel file using pandas."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext

_VALID_AGGFUNCS = {"sum", "mean", "count", "max", "min", "median", "std"}


class PivotTableInput(BaseModel):
    file_path: str = Field(description="Path to a CSV or Excel data file.")
    index: str = Field(description="Column to use as pivot row labels.")
    columns: str = Field(default="", description="Column to spread as pivot column headers (optional).")
    values: str = Field(description="Column whose values to aggregate.")
    aggfunc: str = Field(default="sum", description="Aggregation: sum | mean | count | max | min | median | std")
    fill_value: float = Field(default=0.0, description="Value to fill missing cells.")
    max_rows: int = Field(default=50, description="Max rows to display in output.")
    output_csv: str = Field(default="", description="Optional path to write the pivot as CSV.")


class PivotTableTool(BaseCallable):
    """Build a pivot table from a CSV or Excel file and return it as a markdown table."""

    name = "pivot_table"
    description = (
        "Create a pivot table from a CSV or Excel data file using pandas. "
        "Specify index (row labels), optional columns (column headers), "
        "values column, and aggregation function (sum/mean/count/max/min/median/std). "
        "Returns the pivot as a markdown table. Optionally writes to CSV."
    )
    callable_type = CallableType.TOOL
    input_schema = PivotTableInput
    output_schema = ToolOutput
    policy = tool_policy(
        timeout_seconds=60.0,
        requires_approval=False,
        network_allowed=False,
    )

    async def _execute(self, input: PivotTableInput, context: CallContext) -> ToolOutput:
        try:
            import pandas as pd  # type: ignore[import-untyped]
        except ImportError:
            return ToolOutput(result="[pivot_table: pandas not installed — run: pip install pandas]")

        aggfunc = input.aggfunc.lower().strip()
        if aggfunc not in _VALID_AGGFUNCS:
            return ToolOutput(result=f"[pivot_table: unknown aggfunc '{aggfunc}'. Valid: {', '.join(sorted(_VALID_AGGFUNCS))}]")

        path = Path(input.file_path).expanduser().resolve()
        if not path.exists():
            return ToolOutput(result=f"[pivot_table: file not found: {path}]")

        try:
            if path.suffix.lower() in {".xls", ".xlsx", ".xlsm"}:
                df = pd.read_excel(path)
            else:
                df = pd.read_csv(path, low_memory=False)
        except Exception as exc:
            return ToolOutput(result=f"[pivot_table: read error: {exc}]")

        for col, label in [(input.index, "index"), (input.values, "values")]:
            if col not in df.columns:
                return ToolOutput(result=f"[pivot_table: column '{col}' ({label}) not found. Available: {list(df.columns)}]")

        columns_arg = input.columns if input.columns and input.columns in df.columns else None

        try:
            pivot = pd.pivot_table(
                df,
                index=input.index,
                columns=columns_arg,
                values=input.values,
                aggfunc=aggfunc,
                fill_value=input.fill_value,
            )
        except Exception as exc:
            return ToolOutput(result=f"[pivot_table: pivot error: {exc}]")

        display = pivot.head(input.max_rows)
        md = display.to_markdown()
        truncation = f"\n_(showing {input.max_rows} of {len(pivot)} rows)_" if len(pivot) > input.max_rows else ""

        csv_note = ""
        if input.output_csv:
            csv_path = Path(input.output_csv).expanduser().resolve()
            csv_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                pivot.to_csv(str(csv_path))
                csv_note = f"\nCSV written: {csv_path}"
            except Exception as exc:
                csv_note = f"\n⚠ CSV write failed: {exc}"

        header = f"**Pivot:** {input.index} × {columns_arg or '(none)'} → {input.values} ({aggfunc})  |  {len(pivot)} row(s)\n"
        return ToolOutput(result=header + md + truncation + csv_note)
