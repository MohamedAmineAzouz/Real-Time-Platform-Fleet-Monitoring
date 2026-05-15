"""Structured logging for the Streamlit analytics platform."""

from __future__ import annotations

import logging
from functools import lru_cache

from config.settings import get_settings


@lru_cache(maxsize=1)
def _configure_logging() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def get_logger(name: str) -> logging.Logger:
    _configure_logging()
    return logging.getLogger(name)
