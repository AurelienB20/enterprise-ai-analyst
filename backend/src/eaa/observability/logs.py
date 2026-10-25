"""Process-wide logging: plain text for development, one JSON object per line in production.

Every record carries the correlation ID of the request being served. It lives in a
context variable, so the tasks a request starts inherit it.

Logs must never hold personal data, secrets or query results: log identifiers, counts
and durations, not values.
"""

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from eaa.config import LogFormat, LogLevel

TEXT_FORMAT = "%(asctime)s %(levelname)s [%(name)s] [%(correlation_id)s] %(message)s"

correlation_id_var: ContextVar[str | None] = ContextVar("eaa_correlation_id", default=None)

# Attributes every LogRecord has; anything else was passed with ``extra=``.
_STANDARD_ATTRIBUTES = frozenset(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


class CorrelationIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = correlation_id_var.get() or "-"
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        entry.update(
            (key, value) for key, value in vars(record).items() if key not in _STANDARD_ATTRIBUTES
        )
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str, ensure_ascii=False)


def configure_logging(level: LogLevel, log_format: LogFormat = "text") -> None:
    """Configure root logging once for the whole process."""
    handler = logging.StreamHandler()
    handler.addFilter(CorrelationIdFilter())
    formatter = JsonFormatter() if log_format == "json" else logging.Formatter(TEXT_FORMAT)
    handler.setFormatter(formatter)
    logging.basicConfig(level=level, handlers=[handler], force=True)
