"""
Logging tập trung cho toàn hệ thống.
- agent_logger: ghi hoạt động của các agent (routing, tool call, response) -> log/agent/
- db_logger: ghi hoạt động ghi/đọc DB (ticket, booking, memory) -> log/db/
"""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

AGENT_LOG_DIR = Path("log/agent")
DB_LOG_DIR = Path("log/db")
AGENT_LOG_DIR.mkdir(parents=True, exist_ok=True)
DB_LOG_DIR.mkdir(parents=True, exist_ok=True)

FORMATTER = logging.Formatter(
    "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def _build_logger(name: str, log_path: Path) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    if not logger.handlers:  # tránh add handler trùng lặp khi Streamlit rerun/reimport
        file_handler = RotatingFileHandler(
            log_path, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        file_handler.setFormatter(FORMATTER)
        logger.addHandler(file_handler)
        logger.propagate = False  # không in trùng ra console gốc của Streamlit

    return logger


agent_logger = _build_logger("agent", AGENT_LOG_DIR / "agent.log")
db_logger = _build_logger("db", DB_LOG_DIR / "db.log")