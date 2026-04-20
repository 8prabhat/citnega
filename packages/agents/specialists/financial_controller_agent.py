"""FinancialControllerAgent — financial reporting, variance analysis, reconciliation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.agents.specialists._specialist_base import SpecialistBase, SpecialistOutput
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class FinancialControllerInput(BaseModel):
    task: str = Field(description="Finance task — e.g. 'variance analysis for Q3', 'reconcile accounts', 'build P&L summary', 'month-end close checklist'.")
    data_file: str = Field(default="", description="Path to financial data file (CSV/Excel).")
    budget_file: str = Field(default="", description="Path to budget/forecast file for variance analysis.")
    output_file: str = Field(default="", description="Optional path to write the report (Excel/PDF).")
    period: str = Field(default="", description="Reporting period, e.g. 'Q3 2025', 'October 2025'.")


class FinancialControllerAgent(SpecialistBase):
    name = "financial_controller_agent"
    description = (
        "Financial controller specialist for P&L analysis, variance reporting, account reconciliation, "
        "budget vs actuals, and month-end close procedures. "
        "Produces Excel reports, PDF summaries, and structured financial narratives. "
        "Use for: management accounts, board packs, variance analysis, cash flow forecasting, "
        "GL reconciliation, and financial data profiling."
    )
    callable_type = CallableType.SPECIALIST
    input_schema = FinancialControllerInput
    output_schema = SpecialistOutput
    policy = CallablePolicy(
        timeout_seconds=120.0,
        requires_approval=False,
        network_allowed=False,
        max_output_bytes=512 * 1024,
        max_depth_allowed=3,
    )

    SYSTEM_PROMPT = (
        "You are a senior financial controller. Never fabricate or estimate figures — "
        "only work with data provided or retrieved from files. "
        "For variance analysis: show actual, budget, variance (£/$), variance (%), and explain drivers. "
        "For reconciliations: show opening balance, movements, closing balance, and flag unreconciled items. "
        "Present numbers in consistent format (2 decimal places, currency symbol, thousands separator). "
        "Flag material variances (>10% or >£10k) prominently."
    )
    TOOL_WHITELIST = [
        "sql_query", "pandas_analyze", "pivot_table", "data_profiler",
        "create_excel", "write_pdf", "render_chart", "read_file", "calculate", "write_kb", "read_kb",
    ]

    async def _execute(self, input: FinancialControllerInput, context: CallContext) -> SpecialistOutput:
        tool_calls_made: list[str] = []
        child_ctx = context.child(self.name, self.callable_type)
        gathered: list[str] = [f"Task: {input.task}"]

        if input.period:
            gathered.append(f"Reporting period: {input.period}")

        for label, path in [("Actuals data", input.data_file), ("Budget/forecast data", input.budget_file)]:
            if not path:
                continue
            analyzer = self._get_tool("pandas_analyze")
            if analyzer:
                try:
                    from citnega.packages.tools.builtin.pandas_analyze import PandasAnalyzeInput
                    result = await analyzer.invoke(
                        PandasAnalyzeInput(file_path=path, operations=["head", "describe", "shape"]),
                        child_ctx,
                    )
                    if result.success:
                        gathered.append(f"{label}:\n{result.get_output_field('result')}")
                        tool_calls_made.append("pandas_analyze")
                except Exception:
                    pass

        if input.output_file:
            gathered.append(f"Output file: {input.output_file}")

        prompt = "\n\n---\n\n".join(gathered)
        response = await self._call_model(prompt, context)
        return SpecialistOutput(response=response, tool_calls_made=tool_calls_made)
