#!/usr/bin/env bash
# build_release.sh — Build distribution wheel
set -euo pipefail

echo "==> Running full test suite..."
uv run pytest --cov=packages --cov-fail-under=80

echo "==> Lint and format checks..."
uv run ruff check packages/ apps/
uv run ruff format --check packages/ apps/

echo "==> Type checking..."
uv run mypy packages/

echo "==> Architecture contracts..."
uv run lint-imports

echo "==> Building wheel..."
uv build

echo "==> Build artifacts:"
ls -lh dist/
