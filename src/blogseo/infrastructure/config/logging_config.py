"""Configuration du logging standard (INFO/ERROR), console + fichier rotatif."""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

_CONSOLE_FORMAT = "%(asctime)s │ %(levelname)-7s │ %(name)-38s │ %(message)s"
_FILE_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(funcName)s:%(lineno)d | %(message)s"
_DATE_FORMAT = "%H:%M:%S"

_COLORS = {
    "DEBUG": "\033[38;5;245m",
    "INFO": "\033[38;5;39m",
    "WARNING": "\033[38;5;214m",
    "ERROR": "\033[38;5;203m",
    "CRITICAL": "\033[1;38;5;196m",
}
_RESET = "\033[0m"


class _ColorFormatter(logging.Formatter):
    """Colorise le niveau si la sortie est un terminal."""

    def __init__(self, fmt: str, datefmt: str, use_color: bool) -> None:
        super().__init__(fmt, datefmt)
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        if self.use_color:
            color = _COLORS.get(record.levelname, "")
            record.levelname = f"{color}{record.levelname}{_RESET}"
        return super().format(record)


def setup_logging(level: str = "INFO", log_dir: Path | None = None, run_id: str = "") -> None:
    """Installe les handlers console + fichier. Idempotent."""
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)  # les handlers filtrent, pas le root
    for handler in list(root.handlers):
        root.removeHandler(handler)

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(getattr(logging, level.upper(), logging.INFO))
    console.setFormatter(_ColorFormatter(_CONSOLE_FORMAT, _DATE_FORMAT, sys.stdout.isatty()))
    root.addHandler(console)

    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        filename = f"pipeline{'-' + run_id if run_id else ''}.log"
        file_handler = logging.handlers.RotatingFileHandler(
            log_dir / filename, maxBytes=2_000_000, backupCount=5, encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(_FILE_FORMAT))
        root.addHandler(file_handler)

    # Les bibliothèques tierces sont bavardes : on les calme.
    for noisy in ("httpx", "httpcore", "urllib3", "chromadb", "sentence_transformers",
                  "PIL", "primp", "asyncio", "telegram", "matplotlib"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
