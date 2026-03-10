"""Custom FastAPI middleware helpers."""
from __future__ import annotations

import time
from typing import Callable

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware

from .api_errors import LOGGER


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every HTTP request with execution time."""

    async def dispatch(self, request: Request, call_next: Callable):  # type: ignore[override]
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:  # pragma: no cover - defensive logging
            duration = (time.perf_counter() - start) * 1000
            LOGGER.exception(
                "Unhandled error for %s %s in %.2f ms", request.method, request.url.path, duration
            )
            raise
        duration = (time.perf_counter() - start) * 1000
        LOGGER.info(
            "Handled %s %s -> %s in %.2f ms",
            request.method,
            request.url.path,
            response.status_code,
            duration,
        )
        return response


def install_middleware(app: FastAPI) -> None:
    app.add_middleware(RequestLoggingMiddleware)


__all__ = ["install_middleware", "RequestLoggingMiddleware"]
