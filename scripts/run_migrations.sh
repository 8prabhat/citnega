#!/usr/bin/env bash
# run_migrations.sh — Run Alembic migrations to head
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "==> Running Alembic migrations..."
cd "$PROJECT_ROOT/packages/storage"
uv run alembic upgrade head
echo "==> Migrations complete."
