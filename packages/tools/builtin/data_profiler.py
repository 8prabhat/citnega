"""data_profiler — auto-generate a schema and quality profile for a data file."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class DataProfilerInput(BaseModel):
    file_path: str = Field(description="Path to the CSV or Excel file to profile.")
    sample_rows: int = Field(default=10000, description="Max rows to sample (for large files).")
    top_n: int = Field(default=5, description="Number of top values to show per column.")


class DataProfilerTool(BaseCallable):
    """Auto-generate a schema and data quality profile for a CSV or Excel file."""

    name = "data_profiler"
    description = (
        "Profile a CSV or Excel data file: infer schema, null percentages, "
        "cardinality, min/max, and top-N most frequent values per column. "
        "Returns a concise markdown report suitable for EDA or data quality review."
    )
    callable_type = CallableType.TOOL
    input_schema = DataProfilerInput
    output_schema = ToolOutput
    policy = tool_policy(
        timeout_seconds=60.0,
        requires_approval=False,
        network_allowed=False,
    )

    async def _execute(self, input: DataProfilerInput, context: CallContext) -> ToolOutput:
        try:
            import pandas as pd  # type: ignore[import-untyped]
        except ImportError:
            return ToolOutput(result="[data_profiler: pandas not installed — run: pip install pandas]")

        path = Path(input.file_path).expanduser().resolve()
        if not path.exists():
            return ToolOutput(result=f"[data_profiler: file not found: {path}]")

        try:
            if path.suffix.lower() in {".xls", ".xlsx", ".xlsm"}:
                df = pd.read_excel(path, nrows=input.sample_rows)
            else:
                df = pd.read_csv(path, nrows=input.sample_rows, low_memory=False)
        except Exception as exc:
            return ToolOutput(result=f"[data_profiler: read error: {exc}]")

        n_rows, n_cols = df.shape
        lines = [
            f"## Data Profile: {path.name}",
            f"**Rows sampled:** {n_rows:,}  |  **Columns:** {n_cols}",
            "",
            "| Column | Type | Null% | Unique | Min | Max | Top values |",
            "|--------|------|-------|--------|-----|-----|------------|",
        ]

        for col in df.columns:
            series = df[col]
            dtype = str(series.dtype)
            null_pct = f"{series.isnull().mean() * 100:.1f}%"
            n_unique = series.nunique()

            # min / max only for numeric and datetime
            try:
                col_min = str(series.min()) if not series.isnull().all() else "—"
                col_max = str(series.max()) if not series.isnull().all() else "—"
            except Exception:
                col_min = col_max = "—"

            top_vals = series.dropna().value_counts().head(input.top_n).index.tolist()
            top_str = ", ".join(str(v)[:20] for v in top_vals)

            lines.append(
                f"| {col[:30]} | {dtype} | {null_pct} | {n_unique:,} | {col_min[:15]} | {col_max[:15]} | {top_str} |"
            )

        # Duplicate row check
        n_dupes = int(df.duplicated().sum())
        lines.append(f"\n**Duplicate rows:** {n_dupes:,} ({n_dupes/n_rows*100:.1f}%)")

        # Fully null columns
        fully_null = [c for c in df.columns if df[c].isnull().all()]
        if fully_null:
            lines.append(f"**Fully null columns:** {', '.join(fully_null)}")

        return ToolOutput(result="\n".join(lines))
