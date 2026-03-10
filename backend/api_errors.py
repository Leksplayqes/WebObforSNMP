"""Unified API error handling utilities."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


LOGGER = logging.getLogger("osmktester.api")


class ApiException(Exception):
    """Application level exception with rich error metadata."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "INTERNAL_ERROR",
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


def _error_payload(code: str, message: str, *, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "status": "error",
        "error": {
            "code": code,
            "message": message,
        },
    }
    if details:
        payload["error"]["details"] = details
    return payload


def api_error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    """Return a JSON error response following the unified schema."""

    return JSONResponse(
        status_code=status_code,
        content=_error_payload(code, message, details=details),
    )


async def _handle_request_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
    LOGGER.warning("Request validation failed: %s", exc)
    details = {"errors": exc.errors()}
    return api_error_response(
        status_code=422,
        code="VALIDATION_ERROR",
        message="Запрос не прошёл валидацию",
        details=details,
    )


async def _handle_http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) else "Внутренняя ошибка"
    LOGGER.warning("HTTP exception: %s", message)
    return api_error_response(
        status_code=exc.status_code,
        code=f"HTTP_{exc.status_code}",
        message=message,
    )


async def _handle_api_exception(_: Request, exc: ApiException) -> JSONResponse:
    LOGGER.warning("API exception: %s", exc.message)
    return api_error_response(
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        details=exc.details or None,
    )


async def _handle_generic_exception(_: Request, exc: Exception) -> JSONResponse:
    LOGGER.exception("Unhandled error", exc_info=exc)
    return api_error_response(
        status_code=500,
        code="INTERNAL_ERROR",
        message="Произошла непредвиденная ошибка",
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Install unified exception handlers for the FastAPI app."""

    app.add_exception_handler(RequestValidationError, _handle_request_validation)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(ApiException, _handle_api_exception)
    app.add_exception_handler(Exception, _handle_generic_exception)


__all__ = ["ApiException", "register_exception_handlers", "api_error_response", "LOGGER"]
