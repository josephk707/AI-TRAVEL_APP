"""
Structured logging setup.

Emits leveled, structured (key=value) log lines to stdout so a hosting
platform's log collector (or a future centralized logging stack — see
docs/DEPLOYMENT_PLAN.md §8) can parse them without a custom agent in Phase 1.
"""

import logging
import sys

from app.core.config import get_settings


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = (
            f'time="{self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z")}" '
            f"level={record.levelname} "
            f'logger="{record.name}" '
            f'message="{record.getMessage()}"'
        )
        if record.exc_info:
            base += f"\n{self.formatException(record.exc_info)}"
        return base


def configure_logging() -> None:
    settings = get_settings()
    root = logging.getLogger()
    root.setLevel(settings.log_level)

    # Avoid duplicate handlers on reload (uvicorn --reload re-imports).
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter())
    root.addHandler(handler)

    # Quiet down noisy third-party loggers at DEBUG unless explicitly asked for.
    logging.getLogger("uvicorn.access").setLevel(settings.log_level)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
