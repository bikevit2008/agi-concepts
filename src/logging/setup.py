from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

_LOG_FILE_HANDLER: logging.FileHandler | None = None


def setup_logging(
    level: str = "INFO",
    json_dir: str = "logs",
    console_enabled: bool = True,
    project_root: Path | None = None,
) -> structlog.stdlib.BoundLogger:
    """Configure structlog with JSON file output and optional rich console output.

    Creates a log file per run: logs/run_YYYYMMDD_HHMMSS.json
    Returns the root bound logger.
    """
    global _LOG_FILE_HANDLER

    root = project_root or Path(__file__).resolve().parent.parent.parent
    log_dir = root / json_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"run_{timestamp}.json"

    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Standard library logging setup
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    # Clear existing handlers
    root_logger.handlers.clear()

    # JSON file handler
    file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
    file_handler.setLevel(numeric_level)
    _LOG_FILE_HANDLER = file_handler
    root_logger.addHandler(file_handler)

    # Console handler (optional)
    if console_enabled:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(numeric_level)
        root_logger.addHandler(console_handler)

    # Shared processors
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    # structlog configuration
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # JSON formatter for file handler
    json_formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
    )
    file_handler.setFormatter(json_formatter)

    # Console formatter
    if console_enabled and len(root_logger.handlers) > 1:
        console_formatter = structlog.stdlib.ProcessorFormatter(
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.dev.ConsoleRenderer(colors=True),
            ],
        )
        root_logger.handlers[1].setFormatter(console_formatter)

    logger: structlog.stdlib.BoundLogger = structlog.get_logger("consciousness")
    logger.info("logging_initialized", log_file=str(log_file), level=level)
    return logger


def get_logger(name: str = "consciousness") -> structlog.stdlib.BoundLogger:
    """Get a named structlog logger."""
    return structlog.get_logger(name)
