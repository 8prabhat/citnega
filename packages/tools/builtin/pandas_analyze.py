"""pandas_analyze — run common analytical operations on CSV/Excel files."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext

_VALID_OPS = {"describe", "head", "dtypes", "value_counts", "corr", "groupby", "shape", "missing"}


class PandasAnalyzeInput(BaseModel):
    file_path: str = Field(description="Path to a CSV or Excel file to analyze.")
    operations: list[str] = Field(
        default_factory=lambda: ["shape", "dtypes", "describe", "missing"],
        description=(
            "Operations to run: describe | head | dtypes | value_counts | "
            "corr | groupby | shape | missing"
        ),
    )
    groupby_col: str = Field(default="", description="Column to group by (required for groupby).")
    agg_col: str = Field(default="", description="Column to aggregate in groupby (defaults to count).")
    agg_func: str = Field(default="count", description="Aggregation function: count | sum | mean | max | min.")
    value_counts_col: str = Field(default="", description="Column for value_counts operation.")
    head_rows: int = Field(default=5, description="Number of rows to show for head operation.")
    sample_rows: int = Field(default=10000, description="Max rows to read (for performance on large files).")


class PandasAnalyzeTool(BaseCallable):
    """Analyze a CSV or Excel file using pandas — describe, profile, group, correlate."""

    name = "pandas_analyze"
    description = (
        "Run analytical operations on a CSV or Excel data file using pandas. "
        "Supports: describe (stats), head (preview), dtypes (schema), value_counts, "
        "corr (correlation matrix), groupby, shape, missing (null analysis). "
        "Returns results as a markdown-formatted string."
    )
    callable_type = CallableType.TOOL
    input_schema = PandasAnalyzeInput
    output_schema = ToolOutput
    policy = tool_policy(
        timeout_seconds=60.0,
        requires_approval=False,
        network_allowed=False,
    )

    async def _execute(self, input: PandasAnalyzeInput, context: CallContext) -> ToolOutput:
        try:
            import pandas as pd  # type: ignore[import-untyped]
        except ImportError:
            return ToolOutput(result="[pandas_analyze: pandas not installed — run: pip install pandas]")

        path = Path(input.file_path).expanduser().resolve()
        if not path.exists():
            return ToolOutput(result=f"[pandas_analyze: file not found: {path}]")

        try:
            if path.suffix.lower() in {".xls", ".xlsx", ".xlsm"}:
                df = pd.read_excel(path, nrows=input.sample_rows)
            else:
                df = pd.read_csv(path, nrows=input.sample_rows)
        except Exception as exc:
            return ToolOutput(result=f"[pandas_analyze: read error: {exc}]")

        parts: list[str] = [f"**File:** {path.name}  |  **Rows loaded:** {len(df):,}  |  **Columns:** {len(df.columns)}"]

        ops = [o.lower().strip() for o in input.operations]
        unknown = [o for o in ops if o not in _VALID_OPS]
        if unknown:
            parts.append(f"⚠ Unknown operations ignored: {unknown}")

        for op in ops:
            if op not in _VALID_OPS:
                continue
            try:
                if op == "shape":
                    parts.append(f"\n### shape\n{df.shape[0]:,} rows × {df.shape[1]} columns")

                elif op == "dtypes":
                    rows = "\n".join(f"  {col:<30} {str(dtype)}" for col, dtype in df.dtypes.items())
                    parts.append(f"\n### dtypes\n```\n{rows}\n```")

                elif op == "head":
                    parts.append(f"\n### head ({input.head_rows} rows)\n{df.head(input.head_rows).to_markdown(index=False)}")

                elif op == "describe":
                    parts.append(f"\n### describe (numeric)\n{df.describe().to_markdown()}")

                elif op == "missing":
                    missing = df.isnull().sum()
                    missing_pct = (missing / len(df) * 100).round(1)
                    miss_df = pd.DataFrame({"null_count": missing, "null_%": missing_pct})
                    miss_df = miss_df[miss_df["null_count"] > 0]
                    if miss_df.empty:
                        parts.append("\n### missing\nNo null values found.")
                    else:
                        parts.append(f"\n### missing\n{miss_df.to_markdown()}")

                elif op == "corr":
                    numeric = df.select_dtypes(include="number")
                    if numeric.shape[1] < 2:
                        parts.append("\n### corr\nNot enough numeric columns.")
                    else:
                        parts.append(f"\n### corr\n{numeric.corr().round(3).to_markdown()}")

                elif op == "value_counts":
                    col = input.value_counts_col or df.columns[0]
                    if col not in df.columns:
                        parts.append(f"\n### value_counts\nColumn '{col}' not found.")
                    else:
                        vc = df[col].value_counts().head(20)
                        parts.append(f"\n### value_counts ({col})\n{vc.to_markdown()}")

                elif op == "groupby":
                    if not input.groupby_col or input.groupby_col not in df.columns:
                        parts.append(f"\n### groupby\ngroupby_col '{input.groupby_col}' not found.")
                    else:
                        agg_col = input.agg_col if input.agg_col and input.agg_col in df.columns else None
                        agg_func = input.agg_func
                        if agg_col:
                            result = getattr(df.groupby(input.groupby_col)[agg_col], agg_func)()
                        else:
                            result = df.groupby(input.groupby_col).size().rename("count")
                        parts.append(f"\n### groupby ({input.groupby_col})\n{result.head(30).to_markdown()}")

            except Exception as exc:
                parts.append(f"\n### {op}\n⚠ Error: {exc}")

        return ToolOutput(result="\n".join(parts))
