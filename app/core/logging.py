import json
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import BASE_DIR, get_settings
from .observability import get_correlation_id


# Reserved LogRecord attributes that should not be duplicated in the JSON payload.
_RESERVED_LOG_KEYS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "message",
    "asctime",
}


class CorrelationIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover - simple enrichment
        record.correlation_id = get_correlation_id() or "-"
        record.service = "sardoba-app"
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:  # pragma: no cover - formatting only
        payload = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "service": getattr(record, "service", "sardoba-app"),
            "logger": record.name,
            "correlation_id": getattr(record, "correlation_id", "-"),
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _RESERVED_LOG_KEYS or key in payload:
                continue
            try:
                json.dumps({key: value})
                payload[key] = value
            except TypeError:
                payload[key] = str(value)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def _build_handlers(settings) -> list[logging.Handler]:
    handlers: list[logging.Handler] = []
    formatter = JsonFormatter(datefmt="%Y-%m-%dT%H:%M:%S%z")
    filter_ = CorrelationIdFilter()

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(filter_)
    handlers.append(stream_handler)

    if settings.LOG_FILE_PATH:
        log_path = Path(settings.LOG_FILE_PATH)
        if not log_path.is_absolute():
            log_path = BASE_DIR / log_path
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.addFilter(filter_)
        handlers.append(file_handler)

    return handlers


def configure_logging() -> None:
    """
    Configure structured JSON logging with correlation id enrichment and
    rotating file handlers that write to a host-mounted path.
    """
    settings = get_settings()
    handlers = _build_handlers(settings)

    logging.basicConfig(
        level=settings.LOG_LEVEL,
        handlers=handlers,
        force=True,
    )

    # Make httpx, sqlalchemy, and uvicorn less chatty while preserving warnings/errors.
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
