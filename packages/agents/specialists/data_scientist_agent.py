"""DataScientistAgent — ML experiments, feature engineering, model evaluation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from citnega.packages.agents.specialists._specialist_base import SpecialistBase, SpecialistOutput
from citnega.packages.protocol.callables.types import CallablePolicy, CallableType

if TYPE_CHECKING:
    from citnega.packages.protocol.callables.context import CallContext


class DataScientistInput(BaseModel):
    task: str = Field(description="Data science task — e.g. 'train a classifier on churn.csv', 'feature engineer the dataset', 'evaluate model performance'.")
    file_path: str = Field(default="", description="Path to dataset or model file.")
    target_column: str = Field(default="", description="Target/label column name for supervised learning tasks.")
    script_path: str = Field(default="", description="Optional path to an existing Python script to run or review.")


class DataScientistAgent(SpecialistBase):
    name = "data_scientist_agent"
    description = (
        "Data science specialist for machine learning experiments, feature engineering, "
        "model evaluation, and statistical inference. Can profile datasets, write and run "
        "training scripts, evaluate model metrics, and generate experiment reports. "
        "Use for: classification, regression, clustering, NLP tasks, model audits."
    )
    callable_type = CallableType.SPECIALIST
    input_schema = DataScientistInput
    output_schema = SpecialistOutput
    policy = CallablePolicy(
        timeout_seconds=180.0,
        requires_approval=False,
        network_allowed=False,
        max_output_bytes=512 * 1024,
        max_depth_allowed=3,
    )

    SYSTEM_PROMPT = (
        "You are a senior data scientist. Follow the full ML lifecycle: "
        "EDA → feature engineering → baseline model → iterate → evaluate → document. "
        "Always report: dataset shape, class balance, feature importance, and key metrics "
        "(accuracy, F1, AUC-ROC for classifiers; RMSE, MAE, R² for regressors). "
        "Warn about data leakage, class imbalance, and overfitting. "
        "Write reproducible, well-commented Python code when generating scripts."
    )
    TOOL_WHITELIST = [
        "pandas_analyze", "data_profiler", "sql_query", "run_shell",
        "read_file", "write_file", "render_chart", "write_kb", "read_kb", "perf_profiler",
    ]

    async def _execute(self, input: DataScientistInput, context: CallContext) -> SpecialistOutput:
        tool_calls_made: list[str] = []
        child_ctx = context.child(self.name, self.callable_type)
        gathered: list[str] = [f"Task: {input.task}"]

        if input.target_column:
            gathered.append(f"Target column: {input.target_column}")

        if input.file_path:
            profiler = self._get_tool("data_profiler")
            if profiler:
                try:
                    from citnega.packages.tools.builtin.data_profiler import DataProfilerInput
                    result = await profiler.invoke(DataProfilerInput(file_path=input.file_path), child_ctx)
                    if result.success:
                        gathered.append(f"Dataset profile:\n{result.get_output_field('result')}")
                        tool_calls_made.append("data_profiler")
                except Exception:
                    pass

        if input.script_path:
            reader = self._get_tool("read_file")
            if reader:
                try:
                    from citnega.packages.tools.builtin.read_file import ReadFileInput
                    result = await reader.invoke(ReadFileInput(path=input.script_path), child_ctx)
                    if result.success:
                        gathered.append(f"Existing script:\n{result.get_output_field('result')}")
                        tool_calls_made.append("read_file")
                except Exception:
                    pass

        prompt = "\n\n---\n\n".join(gathered)
        response = await self._call_model(prompt, context)
        return SpecialistOutput(response=response, tool_calls_made=tool_calls_made)
