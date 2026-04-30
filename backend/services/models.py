"""Pydantic models used by API endpoints."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


class LogEntry(BaseModel):
    timestamp: str
    level: str
    message: str


class LogsResponse(BaseModel):
    total: int
    logs: List[LogEntry]


class UpgradeRequestBlock(BaseModel):
    block_type: Optional[str] = None
    slots: List[str] = []


class UpgradeRequestImg(BaseModel):
    image: Optional[str] = None



class LoopbackSettings(BaseModel):
    slot: Optional[int] = None
    port: Optional[int] = None


class ViaviTypeOfPort(BaseModel):
    Port1: str = "STM-1"
    Port2: str = "STM-1"


class ViaviUnitSettings(BaseModel):
    ipaddr: Optional[str] = None
    port: Optional[int] = None
    typeofport: Optional[ViaviTypeOfPort] = None


class ViaviSettings(BaseModel):
    NumOne: Optional[ViaviUnitSettings] = None
    NumTwo: Optional[ViaviUnitSettings] = None


class DeviceInfoRequest(BaseModel):
    ip_address: str
    password: Optional[str] = ""
    viavi: Optional[ViaviSettings] = None
    loopback: Optional[LoopbackSettings] = None


class TestsRunRequest(BaseModel):
    test_type: str = "manual"
    selected_tests: List[str]
    settings: Optional[Dict[str, Any]] = None


class TestDevice(BaseModel):
    name: Optional[str] = ""
    ipaddr: str
    password: Optional[str] = ""


class ApiErrorModel(BaseModel):
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None


class SuccessResponse(BaseModel):
    status: str = "success"
    meta: Optional[Dict[str, Any]] = None


class HistoryLimit(BaseModel):
    type: str
    limit: int
    total: int


class JobSummary(BaseModel):
    status: str
    total: Optional[int] = None
    passed: Optional[int] = None
    failed: Optional[int] = None
    skipped: Optional[int] = None
    duration: Optional[float] = None
    message: Optional[str] = None


class ResultRecordModel(BaseModel):
    id: str
    type: str
    status: str
    created_at: Optional[float] = None
    updated_at: Optional[float] = None
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    summary: Optional[JobSummary] = None

    @model_validator(mode="after")
    def _ensure_summary(self) -> "ResultRecordModel":
        if not self.summary and isinstance(self.payload.get("summary"), dict):
            self.summary = JobSummary.model_validate(self.payload["summary"])
        return self


class ResultListData(BaseModel):
    items: List[ResultRecordModel] = Field(default_factory=list)
    history: List[HistoryLimit] = Field(default_factory=list)


class ResultListResponse(SuccessResponse):
    data: ResultListData


class ResultDetailResponse(SuccessResponse):
    data: ResultRecordModel


class CatalogsResponse(SuccessResponse):
    data: Dict[str, Dict[str, str]]


class CheckConfParameters(BaseModel):
    ip: str
    password: str
    iterations: int = Field(default=3, ge=1, le=100)
    delay: int = Field(default=30, ge=1, le=600)


class CheckHashParameters(BaseModel):
    dir1: str
    dir2: str


class FpgaReloadParameters(BaseModel):
    ip: str
    password: Optional[str] = ""
    slot: int = Field(default=9, ge=0)
    max_attempts: int = Field(default=1000, ge=1, le=5000)


class UtilityRunRequest(BaseModel):
    utility: str
    parameters: object = Field(default_factory=dict)

    @model_validator(mode="after")
    def _normalise(self) -> "UtilityRunRequest":
        allowed = {
            "check_conf": CheckConfParameters,
            "check_hash": CheckHashParameters,
            "fpga_reload": FpgaReloadParameters,
        }
        if self.utility not in allowed:
            raise ValueError(f"Unsupported utility '{self.utility}'")
        model = allowed[self.utility]
        self.parameters = model.model_validate(self.parameters or {})
        return self


class TunnelLeaseModel(BaseModel):
    owner_id: str
    owner_kind: str
    port: int
    created_at: float
    expires_at: float
    ttl: float
    device_ip: str
    username: str
    last_heartbeat: float


class TunnelStatusResponse(BaseModel):
    alive: bool
    configured_ports: List[int]
    leases: List[TunnelLeaseModel]


class TunnelStatusEnvelope(SuccessResponse):
    data: TunnelStatusResponse


__all__ = [
    "LogEntry",
    "LogsResponse",
    "LoopbackSettings",
    "ViaviTypeOfPort",
    "ViaviUnitSettings",
    "ViaviSettings",
    "DeviceInfoRequest",
    "TestsRunRequest",
    "TestDevice",
    "ApiErrorModel",
    "SuccessResponse",
    "HistoryLimit",
    "JobSummary",
    "ResultRecordModel",
    "ResultListData",
    "ResultListResponse",
    "ResultDetailResponse",
    "CatalogsResponse",
    "CheckConfParameters",
    "CheckHashParameters",
    "FpgaReloadParameters",
    "UtilityRunRequest",
    "TunnelLeaseModel",
    "TunnelStatusResponse",
    "TunnelStatusEnvelope",
]
