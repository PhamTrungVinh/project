"""
Centralized application logging.
- agent_logger: agent activity (routing, tool calls, responses) -> log/agent/
- db_logger: database read/write activity (tickets, bookings, memory) -> log/db/
"""
import json
import logging
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler
from pathlib import Path

AGENT_LOG_DIR = Path("log/agent")
DB_LOG_DIR = Path("log/db")
AGENT_LOG_DIR.mkdir(parents=True, exist_ok=True)
DB_LOG_DIR.mkdir(parents=True, exist_ok=True)

request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)


class JsonFormatter(logging.Formatter):
    """Emit machine-readable logs without requiring callers to change."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = request_id_context.get()
        if request_id:
            payload["request_id"] = request_id
        for field in ("route", "user_request"):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


FORMATTER = JsonFormatter()


def _build_logger(name: str, log_path: Path) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    if not logger.handlers:  # avoid duplicate handlers on Streamlit reruns/reimports
        file_handler = RotatingFileHandler(
            log_path, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        file_handler.setFormatter(FORMATTER)
        logger.addHandler(file_handler)
        logger.propagate = False  # avoid duplicate output in Streamlit's root console

    return logger


agent_logger = _build_logger("agent", AGENT_LOG_DIR / "agent.log")
db_logger = _build_logger("db", DB_LOG_DIR / "db.log")
app_logger = _build_logger("app", AGENT_LOG_DIR / "app.log")
