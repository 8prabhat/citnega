"""render_chart — generate a chart image from data using matplotlib."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from citnega.packages.protocol.callables.base import BaseCallable
from citnega.packages.protocol.callables.types import CallableType
from citnega.packages.tools.builtin._tool_base import ToolOutput, tool_policy

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext

_VALID_TYPES = {"bar", "line", "pie", "scatter", "area", "histogram"}


class RenderChartInput(BaseModel):
    chart_type: str = Field(
        description="Chart type: bar | line | pie | scatter | area | histogram"
    )
    labels: list[str] = Field(
        default_factory=list,
        description="X-axis labels (bar/line/area/pie) or category names.",
    )
    datasets: list[dict[str, Any]] = Field(
        description=(
            "One or more data series. Each dict: {label: str, values: list[float]}. "
            "For scatter: {label: str, x: list[float], y: list[float]}."
        )
    )
    title: str = Field(default="", description="Chart title.")
    x_label: str = Field(default="", description="X-axis label.")
    y_label: str = Field(default="", description="Y-axis label.")
    filename: str = Field(description="Output file path, e.g. ~/Desktop/chart.png")
    width_inches: float = Field(default=10.0, description="Figure width in inches.")
    height_inches: float = Field(default=6.0, description="Figure height in inches.")
    dpi: int = Field(default=150, description="Output resolution.")


class RenderChartTool(BaseCallable):
    """Generate a chart image (PNG) from structured data using matplotlib."""

    name = "render_chart"
    description = (
        "Render a chart (bar, line, pie, scatter, area, histogram) as a PNG image. "
        "Accepts multiple data series. Returns the path of the created image file."
    )
    callable_type = CallableType.TOOL
    input_schema = RenderChartInput
    output_schema = ToolOutput
    policy = tool_policy(
        timeout_seconds=30.0,
        requires_approval=False,
        network_allowed=False,
    )

    async def _execute(self, input: RenderChartInput, context: CallContext) -> ToolOutput:
        try:
            import matplotlib  # type: ignore[import-untyped]
            matplotlib.use("Agg")  # non-interactive backend — no display required
            import matplotlib.pyplot as plt  # type: ignore[import-untyped]
        except ImportError:
            return ToolOutput(result="[render_chart: matplotlib not installed — run: pip install matplotlib]")

        chart_type = input.chart_type.lower().strip()
        if chart_type not in _VALID_TYPES:
            return ToolOutput(result=f"[render_chart: unknown chart_type '{chart_type}'. Valid: {', '.join(sorted(_VALID_TYPES))}]")

        out_path = Path(input.filename).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

        fig, ax = plt.subplots(figsize=(input.width_inches, input.height_inches))

        try:
            if chart_type == "pie":
                ds = input.datasets[0] if input.datasets else {}
                values = ds.get("values", [])
                ax.pie(values, labels=input.labels or None, autopct="%1.1f%%", startangle=90)
                ax.axis("equal")

            elif chart_type == "scatter":
                for ds in input.datasets:
                    ax.scatter(ds.get("x", []), ds.get("y", []), label=ds.get("label", ""))

            elif chart_type == "histogram":
                for ds in input.datasets:
                    ax.hist(ds.get("values", []), label=ds.get("label", ""), alpha=0.7)

            elif chart_type == "area":
                x = range(len(input.labels)) if input.labels else range(
                    max((len(ds.get("values", [])) for ds in input.datasets), default=0)
                )
                for ds in input.datasets:
                    ax.fill_between(list(x), ds.get("values", []), alpha=0.5, label=ds.get("label", ""))
                    ax.plot(list(x), ds.get("values", []))
                if input.labels:
                    ax.set_xticks(list(x))
                    ax.set_xticklabels(input.labels, rotation=30, ha="right")

            elif chart_type == "bar":
                import numpy as np  # type: ignore[import-untyped]
                n_groups = len(input.labels) if input.labels else max(
                    (len(ds.get("values", [])) for ds in input.datasets), default=0
                )
                n_series = len(input.datasets)
                bar_width = 0.8 / max(n_series, 1)
                x = np.arange(n_groups)
                for i, ds in enumerate(input.datasets):
                    offset = (i - n_series / 2 + 0.5) * bar_width
                    ax.bar(x + offset, ds.get("values", []), width=bar_width, label=ds.get("label", ""))
                if input.labels:
                    ax.set_xticks(x)
                    ax.set_xticklabels(input.labels, rotation=30, ha="right")

            else:  # line
                x = range(len(input.labels)) if input.labels else range(
                    max((len(ds.get("values", [])) for ds in input.datasets), default=0)
                )
                for ds in input.datasets:
                    ax.plot(list(x), ds.get("values", []), marker="o", label=ds.get("label", ""))
                if input.labels:
                    ax.set_xticks(list(x))
                    ax.set_xticklabels(input.labels, rotation=30, ha="right")

        except Exception as exc:
            plt.close(fig)
            return ToolOutput(result=f"[render_chart: plot error: {exc}]")

        if input.title:
            ax.set_title(input.title)
        if input.x_label:
            ax.set_xlabel(input.x_label)
        if input.y_label:
            ax.set_ylabel(input.y_label)
        if any(ds.get("label") for ds in input.datasets) and chart_type != "pie":
            ax.legend()

        fig.tight_layout()
        try:
            fig.savefig(str(out_path), dpi=input.dpi)
        except Exception as exc:
            return ToolOutput(result=f"[render_chart: save error: {exc}]")
        finally:
            plt.close(fig)

        return ToolOutput(result=f"Chart created: {out_path}  ({out_path.stat().st_size} bytes)")
