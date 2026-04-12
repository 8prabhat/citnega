"""
Structlog JSONL logging configuration.

Sets up structlog with:
  - LogScrubber processor (strips sensitive fields)
  - JSONL output to logs/app/<date>.jsonl
  - schema_version on every record
  - Correlation fields: run_id, session_id, invocation_id
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging
import sys
from typing import TYPE_CHECKING, Any

import structlog

from citnega.packages.security.scrubber import LogScrubber

if TYPE_CHECKING:
    from pathlib import Path

_LOG_SCHEMA_VERSION = 1


def _add_schema_version(logger: Any, method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    event_dict["schema_version"] = _LOG_SCHEMA_VERSION
    return event_dict


def _add_logger_name(logger: Any, method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    if "logger" not in event_dict and logger is not None:
        event_dict["logger"] = getattr(logger, "name", str(logger))
    return event_dict


def configure_logging(
    level: str = "INFO",
    log_dir: Path | None = None,
    scrubber: LogScrubber | None = None,
) -> None:
    """
    Configure structlog for the process.

    Args:
        level:    Log level string (DEBUG | INFO | WARNING | ERROR).
        log_dir:  Directory to write JSONL log files. None = stdout only.
        scrubber: LogScrubber instance. Defaults to a new instance.
    """
    if scrubber is None:
        scrubber = LogScrubber()

    # Build the processor chain
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _add_schema_version,
        scrubber,  # redact before any output
    ]

    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)

    # Route through stdlib logging so handlers can be file-based
    structlog.configure(
        processors=[*shared_processors, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
        foreign_pre_chain=shared_processors,
    )

    # Root handler → stdout
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)

    handlers: list[logging.Handler] = [stdout_handler]

    # File handler → daily JSONL
    if log_dir is not None:
        today = datetime.now(tz=UTC).date().isoformat()
        log_file = log_dir / f"{today}.jsonl"
        file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    root = logging.getLogger()
    root.handlers.clear()
    for h in handlers:
        root.addHandler(h)

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root.setLevel(numeric_level)

    # Quieten noisy third-party loggers
    for noisy in ("sqlalchemy", "alembic", "aiosqlite", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> Any:
    """Return a structlog logger bound to the given name."""
    return structlog.get_logger(name)


# Named loggers as module-level singletons — import and use directly.
runtime_logger = structlog.get_logger("citnega.runtime")
model_gateway_logger = structlog.get_logger("citnega.model_gateway")
storage_logger = structlog.get_logger("citnega.storage")
kb_logger = structlog.get_logger("citnega.kb")
security_logger = structlog.get_logger("citnega.security")
tui_logger = structlog.get_logger("citnega.tui")
cli_logger = structlog.get_logger("citnega.cli")
