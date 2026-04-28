"""Add trace_spans table for structured invocation tracing.

Revision ID: 0002_trace_spans
Revises:     0001_initial
Create Date: 2026-04-21
"""

from __future__ import annotations

from alembic import op

revision = "0002_trace_spans"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS trace_spans (
            span_id     TEXT PRIMARY KEY,
            run_id      TEXT NOT NULL,
            turn_id     TEXT,
            step_id     TEXT,
            tool_name   TEXT NOT NULL,
            start_ts    TEXT NOT NULL,
            end_ts      TEXT NOT NULL,
            input_hash  TEXT,
            output_hash TEXT,
            success     INTEGER NOT NULL DEFAULT 1
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_trace_spans_run_id
        ON trace_spans(run_id)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_trace_spans_run_id")
    op.execute("DROP TABLE IF EXISTS trace_spans")
