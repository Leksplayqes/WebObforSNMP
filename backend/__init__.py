"""Expose the FastAPI application and commonly used constants."""
from __future__ import annotations

from .app import app, create_app
from shared.catalogs import ALARM_TESTS_CATALOG, SYNC_TESTS_CATALOG,STAT_TEST_CATALOG

__all__ = [
    "app",
    "create_app",
    "ALARM_TESTS_CATALOG",
    "SYNC_TESTS_CATALOG",
    "STAT_TEST_CATALOG"
]
