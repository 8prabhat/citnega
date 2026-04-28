## ── Citnega developer Makefile ────────────────────────────────────────────────
##
##  Usage:
##    make              → lint + unit tests (default, fast)
##    make all          → lint + full tests + security scans
##    make security     → all security scans
##    make test         → full test suite
##    make help         → list all targets
##
## Prerequisites: pip install -e ".[dev]"
## ────────────────────────────────────────────────────────────────────────────

PYTHON    ?= python
PYTEST    ?= $(PYTHON) -m pytest
SRC       := citnega/packages citnega/apps
TESTS     := tests

.PHONY: all default lint test test-unit test-integration test-cov \
        security security-deps security-sast security-semgrep security-secrets \
        secrets-baseline install install-security pre-commit-install \
        build clean help

## ── Default ──────────────────────────────────────────────────────────────────

default: lint test-unit

all: lint test security
	@echo ""
	@echo "✓ All checks passed."

## ── Install ──────────────────────────────────────────────────────────────────

install:
	pip install -e ".[dev]"

install-security:
	pip install "bandit[toml]>=1.8" pip-audit "detect-secrets>=1.5" "semgrep>=1.70"

## ── Linting & type checking ──────────────────────────────────────────────────

lint:
	@echo "── ruff ──────────────────────────────────────────────"
	ruff check .
	@echo "── mypy ──────────────────────────────────────────────"
	mypy citnega apps --ignore-missing-imports
	@echo "── import boundaries ─────────────────────────────────"
	lint-imports --config import-linter.ini

## ── Tests ────────────────────────────────────────────────────────────────────

test:
	$(PYTEST)

test-unit:
	$(PYTEST) tests/unit/ -q

test-integration:
	$(PYTEST) tests/integration/ -q

test-cov:
	$(PYTEST) --cov=citnega --cov-report=term-missing --cov-report=html

## ── Security ─────────────────────────────────────────────────────────────────

security: security-deps security-sast security-semgrep security-secrets
	@echo ""
	@echo "✓ Security scan complete."

security-deps:
	@echo "── pip-audit: dependency CVEs ────────────────────────"
	pip-audit

security-sast:
	@echo "── bandit: Python SAST ───────────────────────────────"
	bandit -r $(SRC) -c pyproject.toml -ll

security-semgrep:
	@echo "── semgrep: deep SAST (OWASP + Python) ──────────────"
	semgrep --config=p/python --config=p/security-audit --config=p/owasp-top-ten \
	        $(SRC) --error

security-secrets:
	@echo "── detect-secrets: secret scan ───────────────────────"
	@if [ -f .secrets.baseline ]; then \
	    detect-secrets audit .secrets.baseline --report --fail-on-unaudited; \
	else \
	    echo "No baseline found — run 'make secrets-baseline' first."; \
	    detect-secrets scan --exclude-files '.*\.lock$$' > /tmp/ds-scan.json; \
	    python3 -c "import json,sys; d=json.load(open('/tmp/ds-scan.json')); n=sum(len(v) for v in d.get('results',{}).values()); print(f'{n} potential secret(s) found') if n else print('No secrets found.'); sys.exit(1 if n else 0)"; \
	fi

# Generate (or regenerate) the secrets baseline — run this locally and commit the result.
secrets-baseline:
	@echo "Scanning and writing .secrets.baseline …"
	detect-secrets scan \
	    --exclude-files '\.git/.*' \
	    --exclude-files '.*\.lock$$' \
	    --exclude-files 'dist/.*' \
	    --exclude-files 'htmlcov/.*' \
	    > .secrets.baseline
	@echo "Review with: detect-secrets audit .secrets.baseline"
	@echo "Then commit .secrets.baseline"

## ── Pre-commit ───────────────────────────────────────────────────────────────

pre-commit-install:
	pre-commit install

pre-commit-run:
	pre-commit run --all-files

## ── Build ────────────────────────────────────────────────────────────────────

build:
	$(PYTHON) -m build

## ── Clean ────────────────────────────────────────────────────────────────────

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .mypy_cache .ruff_cache .pytest_cache htmlcov dist build
	rm -f bandit-report.json semgrep-report.json pip-audit-report.json secrets-scan.json

## ── Help ─────────────────────────────────────────────────────────────────────

help:
	@echo ""
	@echo "  Citnega developer targets"
	@echo "  ─────────────────────────────────────────────────────"
	@echo "  make                   lint + unit tests (default)"
	@echo "  make all               lint + tests + security"
	@echo ""
	@echo "  make install           pip install -e .[dev]"
	@echo "  make install-security  install security tools only"
	@echo ""
	@echo "  make lint              ruff + mypy + import-linter"
	@echo "  make test              full pytest suite"
	@echo "  make test-unit         unit tests only (fast)"
	@echo "  make test-integration  integration tests only"
	@echo "  make test-cov          tests + HTML coverage report"
	@echo ""
	@echo "  make security          all security scans"
	@echo "  make security-deps     pip-audit (dependency CVEs)"
	@echo "  make security-sast     bandit (Python code analysis)"
	@echo "  make security-semgrep  semgrep (OWASP + deep rules)"
	@echo "  make security-secrets  detect-secrets (leaked creds)"
	@echo "  make secrets-baseline  create/refresh .secrets.baseline"
	@echo ""
	@echo "  make pre-commit-install  install git hooks"
	@echo "  make pre-commit-run      run all hooks against all files"
	@echo ""
	@echo "  make build             build wheel"
	@echo "  make clean             remove all generated artefacts"
	@echo ""
