from __future__ import annotations

import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    """Configure stdout-friendly logging for local runs and Docker."""

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root_logger.addHandler(handler)
    root_logger.setLevel(level.upper())
