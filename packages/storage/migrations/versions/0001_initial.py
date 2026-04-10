"""Initial schema — all tables for Citnega v1.

Revision ID: 0001_initial
Revises:     —
Create Date: 2026-04-08
"""

from __future__ import annotations

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Core tables ────────────────────────────────────────────────────────────

    op.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id                  TEXT PRIMARY KEY,
            name                        TEXT NOT NULL,
            framework                   TEXT NOT NULL,
            default_model_id            TEXT NOT NULL,
            local_only                  INTEGER NOT NULL DEFAULT 1,
            max_callable_depth          INTEGER NOT NULL DEFAULT 2,
            kb_enabled                  INTEGER NOT NULL DEFAULT 1,
            max_context_tokens          INTEGER NOT NULL DEFAULT 8192,
            approval_timeout_seconds    INTEGER NOT NULL DEFAULT 300,
            tags                        TEXT NOT NULL DEFAULT '[]',
            config_json                 TEXT NOT NULL,
            state                       TEXT NOT NULL DEFAULT 'idle',
            created_at                  TEXT NOT NULL,
            last_active_at              TEXT NOT NULL,
            run_count                   INTEGER NOT NULL DEFAULT 0
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_sessions_last_active
        ON sessions(last_active_at DESC)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            run_id          TEXT PRIMARY KEY,
            session_id      TEXT NOT NULL
                            REFERENCES sessions(session_id) ON DELETE CASCADE,
            state           TEXT NOT NULL,
            started_at      TEXT NOT NULL,
            finished_at     TEXT,
            turn_count      INTEGER NOT NULL DEFAULT 0,
            total_tokens    INTEGER NOT NULL DEFAULT 0,
            error_code      TEXT,
            error_message   TEXT
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_runs_session ON runs(session_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_runs_started ON runs(started_at DESC)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            message_id  TEXT PRIMARY KEY,
            session_id  TEXT NOT NULL
                        REFERENCES sessions(session_id) ON DELETE CASCADE,
            run_id      TEXT REFERENCES runs(run_id) ON DELETE SET NULL,
            role        TEXT NOT NULL,
            content     TEXT NOT NULL,
            timestamp   TEXT NOT NULL,
            metadata    TEXT NOT NULL DEFAULT '{}'
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_messages_session_time
        ON messages(session_id, timestamp)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS callable_invocations (
            invocation_id           TEXT PRIMARY KEY,
            run_id                  TEXT NOT NULL
                                    REFERENCES runs(run_id) ON DELETE CASCADE,
            callable_name           TEXT NOT NULL,
            callable_type           TEXT NOT NULL,
            depth                   INTEGER NOT NULL DEFAULT 0,
            parent_invocation_id    TEXT
                                    REFERENCES callable_invocations(invocation_id),
            input_hash              TEXT NOT NULL,
            input_summary           TEXT NOT NULL,
            output_size             INTEGER NOT NULL DEFAULT 0,
            duration_ms             INTEGER NOT NULL DEFAULT 0,
            policy_result           TEXT NOT NULL,
            error_code              TEXT,
            started_at              TEXT NOT NULL,
            finished_at             TEXT
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_invocations_run
        ON callable_invocations(run_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_invocations_callable
        ON callable_invocations(callable_name)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS approvals (
            approval_id     TEXT PRIMARY KEY,
            run_id          TEXT NOT NULL
                            REFERENCES runs(run_id) ON DELETE CASCADE,
            callable_name   TEXT NOT NULL,
            input_summary   TEXT NOT NULL,
            requested_at    TEXT NOT NULL,
            responded_at    TEXT,
            status          TEXT NOT NULL DEFAULT 'pending',
            user_note       TEXT
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_approvals_run ON approvals(run_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS checkpoints (
            checkpoint_id   TEXT PRIMARY KEY,
            session_id      TEXT NOT NULL
                            REFERENCES sessions(session_id) ON DELETE CASCADE,
            run_id          TEXT NOT NULL
                            REFERENCES runs(run_id) ON DELETE CASCADE,
            framework_name  TEXT NOT NULL,
            file_path       TEXT NOT NULL,
            size_bytes      INTEGER NOT NULL DEFAULT 0,
            state_summary   TEXT NOT NULL,
            created_at      TEXT NOT NULL
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_checkpoints_session
        ON checkpoints(session_id)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS run_summaries (
            session_id      TEXT PRIMARY KEY
                            REFERENCES sessions(session_id) ON DELETE CASCADE,
            summary_text    TEXT NOT NULL,
            message_count   INTEGER NOT NULL DEFAULT 0,
            updated_at      TEXT NOT NULL
        )
    """)

    # ── Knowledge Base tables ──────────────────────────────────────────────────

    op.execute("""
        CREATE TABLE IF NOT EXISTS kb_items (
            item_id             TEXT PRIMARY KEY,
            title               TEXT NOT NULL,
            content             TEXT NOT NULL,
            source_type         TEXT NOT NULL,
            source_session_id   TEXT,
            source_run_id       TEXT,
            tags                TEXT NOT NULL DEFAULT '[]',
            created_at          TEXT NOT NULL,
            updated_at          TEXT NOT NULL,
            content_hash        TEXT NOT NULL,
            file_path           TEXT
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_kb_source_type ON kb_items(source_type)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_kb_content_hash ON kb_items(content_hash)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_kb_created ON kb_items(created_at DESC)
    """)

    # FTS5 virtual table
    op.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS kb_fts USING fts5(
            item_id UNINDEXED,
            title,
            content,
            tags,
            tokenize = 'porter unicode61'
        )
    """)

    # Triggers to keep FTS in sync with kb_items
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS kb_items_ai
        AFTER INSERT ON kb_items
        BEGIN
            INSERT INTO kb_fts(item_id, title, content, tags)
            VALUES (NEW.item_id, NEW.title, NEW.content, NEW.tags);
        END
    """)
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS kb_items_ad
        AFTER DELETE ON kb_items
        BEGIN
            DELETE FROM kb_fts WHERE item_id = OLD.item_id;
        END
    """)
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS kb_items_au
        AFTER UPDATE ON kb_items
        BEGIN
            DELETE FROM kb_fts WHERE item_id = OLD.item_id;
            INSERT INTO kb_fts(item_id, title, content, tags)
            VALUES (NEW.item_id, NEW.title, NEW.content, NEW.tags);
        END
    """)


def downgrade() -> None:
    # Drop in reverse dependency order
    op.execute("DROP TRIGGER IF EXISTS kb_items_au")
    op.execute("DROP TRIGGER IF EXISTS kb_items_ad")
    op.execute("DROP TRIGGER IF EXISTS kb_items_ai")
    op.execute("DROP TABLE IF EXISTS kb_fts")
    op.execute("DROP TABLE IF EXISTS kb_items")
    op.execute("DROP TABLE IF EXISTS run_summaries")
    op.execute("DROP TABLE IF EXISTS checkpoints")
    op.execute("DROP TABLE IF EXISTS approvals")
    op.execute("DROP TABLE IF EXISTS callable_invocations")
    op.execute("DROP TABLE IF EXISTS messages")
    op.execute("DROP TABLE IF EXISTS runs")
    op.execute("DROP TABLE IF EXISTS sessions")
