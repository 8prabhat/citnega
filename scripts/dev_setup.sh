#!/usr/bin/env bash
# dev_setup.sh — Set up the Citnega development environment
set -euo pipefail

echo "==> Checking for uv..."
if ! command -v uv &> /dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi

echo "==> Installing all dependencies..."
uv sync --all-extras

echo "==> Installing pre-commit hooks..."
uv run pre-commit install

echo "==> Running initial database migration..."
bash "$(dirname "$0")/run_migrations.sh"

echo "==> Running tests to verify setup..."
uv run pytest tests/unit/ -q

echo ""
echo "Development environment ready."
echo "  Run TUI:      uv run citnega"
echo "  Run CLI:      uv run citnega-cli"
echo "  Run tests:    uv run pytest"
echo "  Lint:         uv run ruff check ."
echo "  Type check:   uv run mypy packages/"
