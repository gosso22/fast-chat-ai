"""
Logging configuration for the RAG Chatbot application.

Provides structured logging for debugging and monitoring.
"""

import logging
import sys
from typing import Optional


def setup_logging(level: Optional[str] = None) -> None:
    """Configure application-wide logging.

    Args:
        level: Log level string (DEBUG, INFO, WARNING, ERROR). Defaults to INFO.
    """
    log_level = getattr(logging, (level or "INFO").upper(), logging.INFO)

    fmt = (
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )
    date_fmt = "%Y-%m-%d %H:%M:%S"

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt, datefmt=date_fmt))

    # Configure root logger
    root = logging.getLogger()
    root.setLevel(log_level)
    # Avoid duplicate handlers on repeated calls
    if not root.handlers:
        root.addHandler(handler)

    # Application loggers
    for name in ("rag_chatbot", "rag_chatbot.errors", "app", "uvicorn"):
        app_logger = logging.getLogger(name)
        app_logger.setLevel(log_level)

    # Quieten noisy third-party loggers
    for noisy in ("sqlalchemy.engine", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
