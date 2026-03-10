"""Base interfaces for pluggable utilities."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Type

from pydantic import BaseModel


class UtilityError(Exception):
    """Structured error for utilities."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: Optional[Dict[str, Any]] = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.retryable = retryable

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
            "retryable": self.retryable,
        }


@dataclass(frozen=True)
class UtilityMeta:
    id: str
    title: str
    description: str = ""
    tags: tuple[str, ...] = ()
    requires_tunnel: bool = False
    default_timeout_sec: Optional[float] = None


class UtilityContext:
    """Execution context passed to utilities."""

    def __init__(self, *, job_id: str, service: Any) -> None:
        # service is UtilityService (avoid circular typing)
        self.job_id = job_id
        self._service = service

    @property
    def tunnel_service(self) -> Any:
        return self._service.tunnel_service

    def report(self, *, result: Any = None, summary: Optional[Dict[str, Any]] = None) -> None:
        """Update running payload (used for progress)."""
        self._service._report_progress(self.job_id, result=result, summary=summary)

    def set_error(self, err: UtilityError) -> None:
        self._service._set_structured_error(self.job_id, err)


class UtilityBase:
    """Base class for a utility plugin."""
    meta: UtilityMeta
    InputModel: Type[BaseModel]
    OutputModel: Type[BaseModel]

    def validate(self, raw: Dict[str, Any]) -> BaseModel:
        return self.InputModel.model_validate(raw)

    def input_schema(self) -> Dict[str, Any]:
        # Pydantic v2
        return self.InputModel.model_json_schema()

    def output_schema(self) -> Dict[str, Any]:
        return self.OutputModel.model_json_schema()

    def run(self, ctx: UtilityContext, params: BaseModel) -> BaseModel:
        """Override in subclasses. Must return OutputModel instance."""
        raise NotImplementedError
