"""Central logging configuration for backend services."""
from __future__ import annotations

import logging
from logging.config import dictConfig
from typing import Any, Dict


def _build_config() -> Dict[str, Any]:
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
            }
        },
        "handlers": {
            "stderr": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "level": "INFO",
            }
        },
        "loggers": {
            "osmktester": {
                "handlers": ["stderr"],
                "level": "INFO",
                "propagate": False,
            },
            "osmktester.api": {
                "handlers": ["stderr"],
                "level": "INFO",
                "propagate": False,
            },
        },
        "root": {
            "handlers": ["stderr"],
            "level": "WARNING",
        },
    }


def configure_logging() -> None:
    dictConfig(_build_config())
    logging.getLogger("osmktester").info("Logging configured")


__all__ = ["configure_logging"]
