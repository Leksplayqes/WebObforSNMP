"""Typed representations of backend API responses."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


class TestCatalogs(BaseModel):
    alarm_tests: Dict[str, str] = Field(default_factory=dict)
    sync_tests: Dict[str, str] = Field(default_factory=dict)
    stat_tests: Dict[str, str] = Field(default_factory=dict)
    comm_tests: Dict[str, str] = Field(default_factory=dict)
    other_tests: Dict[str, str] = Field(default_factory=dict)


class TestCase(BaseModel):
    name: Optional[str] = None
    nodeid: Optional[str] = None
    status: Optional[str] = None
    duration: Optional[float] = None
    message: Optional[str] = None


class JobSummary(BaseModel):
    status: str = "queued"
    total: Optional[int] = None
    passed: Optional[int] = None
    failed: Optional[int] = None
    skipped: Optional[int] = None
    duration: Optional[float] = None
    message: Optional[str] = None


class TestRunPayload(BaseModel):
    id: str
    summary: JobSummary = Field(default_factory=JobSummary)
    cases: List[TestCase] = Field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    expected_total: Optional[int] = None
    returncode: Optional[int] = None
    finished: Optional[float] = None
    started: Optional[float] = None


class TestRunRecord(BaseModel):
    id: str
    type: str
    status: str
    payload: TestRunPayload = Field(default_factory=TestRunPayload)
    summary: Optional[JobSummary] = None
    created_at: Optional[float] = None
    updated_at: Optional[float] = None
    started_at: Optional[float] = None
    finished_at: Optional[float] = None

    @model_validator(mode="after")
    def _sync_summary(self) -> "TestRunRecord":
        if not self.summary and isinstance(self.payload.summary, JobSummary):
            self.summary = self.payload.summary
        return self


class MaskEnable(BaseModel):
    name: str = ""
    ipaddr: str = ""
    slots_dict: Dict[str, Any] = Field(default_factory=dict)


class DeviceInfo(BaseModel):
    name: str = ""
    ipaddr: str = ""
    slots_dict: Dict[str, Any] = Field(default_factory=dict)
    viavi: Dict[str, Any] = Field(default_factory=dict)
    loopback: Dict[str, Any] = Field(default_factory=dict)


class UtilityJobPayload(BaseModel):
    id: str
    type: str
    params: Dict[str, Any] = Field(default_factory=dict)
    result: Any = None
    error: Optional[str] = None
    started: Optional[float] = None
    finished: Optional[float] = None
    duration: Optional[float] = None
    summary: Optional[JobSummary] = None


class UtilityJobRecord(BaseModel):
    id: str
    type: str
    status: str
    payload: UtilityJobPayload = Field(default_factory=UtilityJobPayload)
    summary: Optional[JobSummary] = None
    created_at: Optional[float] = None
    updated_at: Optional[float] = None
    started_at: Optional[float] = None
    finished_at: Optional[float] = None

    @model_validator(mode="after")
    def _sync_summary(self) -> "UtilityJobRecord":
        if not self.summary and isinstance(self.payload.summary, JobSummary):
            self.summary = self.payload.summary
        return self


class HistoryLimit(BaseModel):
    type: str
    limit: int
    total: int


class MetaResponse(BaseModel):
    status: str = "success"
    meta: Dict[str, Any] = Field(default_factory=dict)

    @property
    def success(self) -> bool:
        return bool(self.meta.get("success", True))

    @property
    def error(self) -> Optional[str]:
        value = self.meta.get("error")
        return str(value) if value is not None else None

    @property
    def message(self) -> Optional[str]:
        value = self.meta.get("message")
        return str(value) if value is not None else None


class TestRunResponse(MetaResponse):
    data: Optional[TestRunRecord] = None

    @property
    def record(self) -> Optional[TestRunRecord]:
        return self.data

    @property
    def job_id(self) -> Optional[str]:
        value = self.meta.get("job_id")
        return str(value) if value is not None else None


class UtilityJobResponse(MetaResponse):
    data: Optional[UtilityJobRecord] = None

    @property
    def record(self) -> Optional[UtilityJobRecord]:
        return self.data


class StopTestResponse(MetaResponse):
    data: Dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "DeviceInfo",
    "TestCatalogs",
    "TestCase",
    "JobSummary",
    "HistoryLimit",
    "TestRunPayload",
    "TestRunRecord",
    "TestRunResponse",
    "UtilityJobPayload",
    "UtilityJobRecord",
    "UtilityJobResponse",
    "StopTestResponse",
]
