# ADR-0002: SQLite with WAL Mode

**Status:** Accepted  
**Date:** 2026-04-08

## Context

Citnega is a local-first application. It needs persistent storage for sessions, runs, messages, KB items, and invocation traces. Enterprise databases (PostgreSQL, MySQL) add operational complexity incompatible with a local-first tool.

## Decision

Use **SQLite in WAL (Write-Ahead Logging) mode** as the sole persistence store.

Configuration (applied via `DatabaseFactory` on every connection):
```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
PRAGMA temp_store = MEMORY;
```

Schema migrations managed by **Alembic** from day one.

Writes are serialized via a single `asyncio.Lock` in `DatabaseFactory`. Reads are concurrent (WAL allows this without blocking).

## Consequences

- Zero operational overhead for users (no server to start).
- Concurrent reads work natively with WAL.
- Single-process write serialization keeps things simple.
- Alembic migrations provide a clear upgrade path.
- FTS5 full-text search is built into SQLite — no separate search engine needed for KB v1.
