"""Data analysis, data science, and ML engineering skills."""

from __future__ import annotations

DATA_ML_SKILLS: list[dict] = [
    {
        "name": "eda_protocol",
        "description": "Exploratory data analysis protocol — profile, visualise, narrate insights.",
        "triggers": [
            "EDA", "exploratory data analysis", "explore data",
            "analyze dataset", "profile data", "data exploration",
        ],
        "preferred_tools": ["data_profiler", "pandas_analyze", "pivot_table", "render_chart"],
        "preferred_agents": ["data_analyst_agent"],
        "supported_modes": ["code", "research"],
        "tags": ["data-analysis", "EDA"],
        "body": """\
## Exploratory Data Analysis Protocol

**Step 1 — Load and profile:**
- Call `data_profiler` first: shape, dtypes, null%, cardinality, top values.
- Call `pandas_analyze` with operations=[shape, dtypes, describe, missing].

**Step 2 — Distributions:**
- For numeric columns: min, max, mean, median, std, skewness.
- For categorical columns: value_counts top 10, % coverage.
- Flag: skewed distributions, suspicious outliers, impossible values.

**Step 3 — Correlations:**
- Call `pandas_analyze` with operations=[corr] for numeric columns.
- Note strong correlations (|r| > 0.7) and anti-correlations.

**Step 4 — Key aggregations:**
- Call `pivot_table` for the most relevant group-by analysis.
- Examples: sales by region, errors by service, revenue by month.

**Step 5 — Visualise:**
- Call `render_chart` for: distribution histogram, trend line, top-N bar chart.
- Choose chart type to match the question (bar=compare, line=trend, scatter=correlation).

**Step 6 — Narrative:**
- Write: What is the data about? What is the data quality? Key patterns? Anomalies? Recommendations?
- Quantify every claim. Avoid vague language.
""",
    },
    {
        "name": "dashboard_design",
        "description": "KPI dashboard design — define metrics, choose charts, render and export.",
        "triggers": [
            "dashboard", "KPI report", "metrics report", "visualise KPIs",
            "build dashboard", "create report",
        ],
        "preferred_tools": ["render_chart", "create_excel", "write_pdf", "create_ppt"],
        "preferred_agents": ["data_analyst_agent"],
        "supported_modes": ["code"],
        "tags": ["data-analysis", "dashboard"],
        "body": """\
## Dashboard Design Protocol

**Step 1 — Define KPIs:**
- For each KPI: name, formula, data source column, target, frequency.
- Group into: Leading indicators (predictive) vs Lagging indicators (outcome).

**Step 2 — Choose chart types:**
- Trend over time → line chart
- Comparison across categories → bar chart
- Part-of-whole → pie chart (≤5 segments only)
- Correlation → scatter plot
- Distribution → histogram

**Step 3 — Render charts:**
- Call `render_chart` for each KPI visualisation.
- Use consistent colour scheme. Label axes. Add title. Include data source.

**Step 4 — Assemble output:**
- For Excel: call `create_excel` with a Summary sheet + one sheet per KPI.
- For PDF: call `write_pdf` with sections per KPI area.
- For slides: call `create_ppt` with one slide per KPI group.

**Step 5 — Commentary:**
- For each KPI: current value vs target, trend direction, key driver, recommended action.
""",
    },
    {
        "name": "ml_experiment",
        "description": "ML experiment protocol — EDA, feature engineering, baseline, evaluation.",
        "triggers": [
            "train model", "ML experiment", "machine learning", "feature engineering",
            "model evaluation", "classification", "regression", "clustering",
        ],
        "preferred_tools": ["data_profiler", "pandas_analyze", "run_shell", "render_chart"],
        "preferred_agents": ["data_scientist_agent"],
        "supported_modes": ["code"],
        "tags": ["data-science", "machine-learning"],
        "body": """\
## ML Experiment Protocol

**Step 1 — EDA:**
- Call `data_profiler` and `pandas_analyze` on the dataset.
- Check: class balance (for classifiers), feature distributions, nulls, outliers.

**Step 2 — Feature engineering:**
- Handle nulls: impute (median/mode) or drop if >30% null.
- Encode categoricals: ordinal encoding or one-hot (max 10 categories).
- Scale numerics: StandardScaler or MinMaxScaler depending on algorithm.
- Check for leakage: no features derived from the target.

**Step 3 — Baseline model:**
- Start simple: LogisticRegression (classifier) or LinearRegression (regressor).
- Use cross-validation (5-fold). Report mean ± std of primary metric.

**Step 4 — Iterate:**
- Try: RandomForest, GradientBoosting. Compare metrics.
- Feature importance: identify top 10 predictors.

**Step 5 — Evaluate:**
- Classification: accuracy, precision, recall, F1, AUC-ROC, confusion matrix.
- Regression: RMSE, MAE, R², residual plot.
- Call `render_chart` for: ROC curve, feature importance bar, learning curve.

**Step 6 — Document:**
- Dataset: rows, features, target, class balance.
- Best model: algorithm, hyperparameters, cross-val metrics.
- Call `write_kb` to persist experiment findings.
""",
    },
    {
        "name": "model_review",
        "description": "ML model audit — data leakage, bias, performance bounds, reproducibility check.",
        "triggers": [
            "review model", "model audit", "bias check", "model fairness",
            "audit ML model", "model governance",
        ],
        "preferred_tools": ["read_file", "pandas_analyze", "data_profiler"],
        "preferred_agents": ["data_scientist_agent", "security_agent"],
        "supported_modes": ["review"],
        "tags": ["data-science", "model-governance"],
        "body": """\
## ML Model Audit Protocol

**Step 1 — Data leakage check:**
- Are any features derived from or correlated with the target post-prediction?
- Is test data contaminated by training data?
- Are timestamps respected (no future data used for past predictions)?

**Step 2 — Bias and fairness:**
- Check performance metrics disaggregated by protected attributes (gender, age, ethnicity).
- Flag: differential error rates across groups > 5 percentage points.
- Assess: training data representation — is each group adequately represented?

**Step 3 — Performance bounds:**
- What is the worst-case performance on out-of-distribution data?
- Is there a confidence/uncertainty estimate available?
- What is the model's behaviour at the decision boundary?

**Step 4 — Reproducibility:**
- Is the random seed set? Are library versions pinned?
- Can the training pipeline be re-run from scratch to produce the same results?

**Step 5 — Report findings:**
- Structure: [SEVERITY] Finding — Evidence — Recommendation
- Severity: CRITICAL (production risk) | HIGH (material bias) | MEDIUM | LOW
""",
    },
    {
        "name": "model_deployment",
        "description": "ML model deployment checklist — package, test, deploy, smoke test, rollback.",
        "triggers": [
            "deploy model", "serve model", "MLOps", "model release",
            "model serving", "production model", "model pipeline",
        ],
        "preferred_tools": ["run_shell", "git_ops", "dependency_auditor", "api_tester"],
        "preferred_agents": ["ml_engineer_agent", "release_agent"],
        "supported_modes": ["operate", "code"],
        "tags": ["MLOps", "deployment"],
        "body": """\
## Model Deployment Protocol

**Pre-flight:**
1. `dependency_auditor` — no vulnerable packages in requirements.txt.
2. `git_ops status` — no uncommitted changes.
3. Unit tests pass: `run_shell` with test command.
4. Model artefact checksummed and version-tagged.

**Package:**
- Pin all dependency versions.
- Include: model file, inference code, preprocessing pipeline, schema validator.
- Document: input schema, output schema, expected latency, memory requirements.

**Deploy (verify-after discipline):**
For each step: state command → expected outcome → execute → verify.
- Deploy to staging first. Run full inference test suite.
- Check: latency p50/p95/p99, memory usage, CPU utilisation.
- Run `api_tester` against staging inference endpoint.

**Smoke test (production):**
- Send 100 representative samples. Compare outputs to staging.
- Monitor: error rate < 0.1%, latency within 20% of staging.

**Rollback plan:**
- Document rollback command before deploying.
- Keep previous model version accessible for at least 7 days.

**Post-deploy:**
- Call `write_kb` to record: model version, deploy date, baseline metrics.
""",
    },
]
