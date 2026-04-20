"""DataAnalystAgent — EDA, statistical analysis, visualisation, insight narrative."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.agents.specialists._specialist_base import SpecialistBase, SpecialistOutput
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class DataAnalystInput(BaseModel):
    task: str = Field(description="Analysis task — e.g. 'profile sales.csv', 'find top 10 customers by revenue', 'show monthly trend'.")
    file_path: str = Field(default="", description="Path to the data file (CSV/Excel) if applicable.")
    chart_output: str = Field(default="", description="Optional file path to write a chart image.")
    report_output: str = Field(default="", description="Optional file path to write a PDF/Excel report.")


class DataAnalystAgent(SpecialistBase):
    name = "data_analyst_agent"
    description = (
        "Data analysis specialist for EDA, statistical profiling, aggregations, trend analysis, "
        "and visualisation. Works with CSV and Excel files. Can produce charts (PNG), "
        "Excel reports, and narrative summaries. Use for: data exploration, KPI reporting, "
        "cohort analysis, distribution analysis, or any question about a dataset."
    )
    callable_type = CallableType.SPECIALIST
    input_schema = DataAnalystInput
    output_schema = SpecialistOutput
    policy = CallablePolicy(
        timeout_seconds=120.0,
        requires_approval=False,
        network_allowed=False,
        max_output_bytes=512 * 1024,
        max_depth_allowed=3,
    )

    SYSTEM_PROMPT = (
        "You are a senior data analyst. When given a dataset, always start by profiling it "
        "(shape, dtypes, nulls, basic stats). Then answer the question with evidence from the data. "
        "Use aggregations, pivot tables, and charts to support your narrative. "
        "Present numbers clearly — round appropriately, add units, label axes. "
        "Highlight outliers, trends, and anomalies. Be concise but data-driven."
    )
    TOOL_WHITELIST = [
        "pandas_analyze", "data_profiler", "pivot_table", "sql_query",
        "render_chart", "create_excel", "write_pdf", "read_file", "write_kb", "read_kb",
    ]

    async def _execute(self, input: DataAnalystInput, context: CallContext) -> SpecialistOutput:
        tool_calls_made: list[str] = []
        child_ctx = context.child(self.name, self.callable_type)
        gathered: list[str] = [f"Task: {input.task}"]

        # Profile the file if provided
        if input.file_path:
            profiler = self._get_tool("data_profiler")
            if profiler:
                try:
                    from citnega.packages.tools.builtin.data_profiler import DataProfilerInput
                    result = await profiler.invoke(DataProfilerInput(file_path=input.file_path), child_ctx)
                    if result.success:
                        gathered.append(f"Data profile:\n{result.get_output_field('result')}")
                        tool_calls_made.append("data_profiler")
                except Exception:
                    pass

            analyzer = self._get_tool("pandas_analyze")
            if analyzer:
                try:
                    from citnega.packages.tools.builtin.pandas_analyze import PandasAnalyzeInput
                    result = await analyzer.invoke(
                        PandasAnalyzeInput(file_path=input.file_path, operations=["head", "describe", "missing"]),
                        child_ctx,
                    )
                    if result.success:
                        gathered.append(f"Statistical summary:\n{result.get_output_field('result')}")
                        tool_calls_made.append("pandas_analyze")
                except Exception:
                    pass

        if input.chart_output:
            gathered.append(f"Chart output path: {input.chart_output}")
        if input.report_output:
            gathered.append(f"Report output path: {input.report_output}")

        prompt = "\n\n---\n\n".join(gathered)
        response = await self._call_model(prompt, context)

        return SpecialistOutput(response=response, tool_calls_made=tool_calls_made)
