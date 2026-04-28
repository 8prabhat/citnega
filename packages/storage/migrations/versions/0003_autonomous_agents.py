"""Add scheduled_runs table and session_type column for autonomous agents.

Revision ID: 0003_autonomous_agents
Revises:     0002_trace_spans
Create Date: 2026-04-22
"""

from __future__ import annotations

from alembic import op

revision = "0003_autonomous_agents"
down_revision = "0002_trace_spans"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add session_type to sessions (backwards-compatible default)
    op.execute("""
        ALTER TABLE sessions ADD COLUMN session_type TEXT NOT NULL DEFAULT 'interactive'
    """)

    # Add user_input to runs so stale runs can be replayed
    op.execute("""
        ALTER TABLE runs ADD COLUMN user_input TEXT
    """)

    # Durable scheduled-run table for SchedulerService
    op.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_runs (
            schedule_id   TEXT PRIMARY KEY,
            name          TEXT NOT NULL,
            schedule      TEXT NOT NULL,
            session_id    TEXT NOT NULL,
            prompt        TEXT NOT NULL,
            enabled       INTEGER NOT NULL DEFAULT 1,
            last_fired_at TEXT,
            next_fire_at  TEXT,
            created_at    TEXT NOT NULL
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_scheduled_runs_enabled
        ON scheduled_runs(enabled)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_scheduled_runs_enabled")
    op.execute("DROP TABLE IF EXISTS scheduled_runs")
    # SQLite does not support DROP COLUMN — downgrade leaves the added
    # columns in place (harmless for tests / local dev).
