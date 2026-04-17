# Evidence Pack

This directory stores generated artifacts for the 9+ delivery criteria.

## Reproducible Commands

Run the three mandated horizontal workflow demos:

```bash
.venv/bin/python scripts/run_horizontal_demos.py
```

Generate an independent rubric scorecard with command-backed evidence:

```bash
.venv/bin/python scripts/generate_9plus_scorecard.py
```

Generate benchmark-matrix evidence for the current OS/Python lane:

```bash
.venv/bin/python scripts/run_benchmark_matrix.py
```

This also appends lane history to:

```text
docs/evidence/benchmark_matrix_history.jsonl
```

The benchmark threshold policy used by the gate lives in:

```text
docs/evidence/benchmark_thresholds.json
```

Signed publication requires:

```bash
export CITNEGA_BENCHMARK_PUBLICATION_SIGNING_KEY_ID='benchmark-2026-04'
export CITNEGA_BENCHMARK_PUBLICATION_SIGNING_KEY='...'
export CITNEGA_BENCHMARK_PUBLICATION_REQUIRE_SIGNATURE='true'
```

## Generated Files

- `horizontal_demos_latest.json`
- `horizontal_demos_latest.md`
- `9plus_scorecard_latest.json`
- `9plus_scorecard_latest.md`
- `benchmark_matrix_latest.json`
- `benchmark_matrix_latest.md`
- `benchmark_matrix_history.jsonl`
- `benchmark_publication_latest.json`
- `benchmark_publication_latest.md`
- `benchmark_publication_history.jsonl`
- `benchmark_thresholds.json`

Timestamped snapshots are also written on each run.
