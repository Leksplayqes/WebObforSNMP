"""FastAPI routes for auxiliary utility executions."""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .models import (
    HistoryLimit,
    ResultDetailResponse,
    ResultListData,
    ResultListResponse,
    ResultRecordModel,
    UtilityRunRequest,
)
from .utils import UtilityService, get_utility_service

router = APIRouter(prefix="/utilities", tags=["utilities"])


class GenericUtilityRunRequest(BaseModel):
    parameters: Dict[str, Any] = Field(default_factory=dict)


def _to_record(data: dict) -> ResultRecordModel:
    return ResultRecordModel.model_validate(data)


@router.get("/registry", summary="Список доступных утилит (data-driven)")
def util_registry(service: UtilityService = Depends(get_utility_service)) -> Dict[str, Any]:
    payload = service.registry_payload()
    return {"status": "success", "data": payload.get("items", [])}


@router.get("/jobs", response_model=ResultListResponse, summary="История запусков утилит")
def util_jobs(service: UtilityService = Depends(get_utility_service)) -> ResultListResponse:
    repo = service.results
    items = [_to_record(record.to_dict()) for record in repo.list()]
    data = ResultListData(
        items=items,
        history=[HistoryLimit(type="utilities", limit=repo.limit, total=repo.count())],
    )
    return ResultListResponse(status="success", data=data)


@router.get("/{job_id}", response_model=ResultDetailResponse, summary="Получить запись утилиты")
def util_status(job_id: str, service: UtilityService = Depends(get_utility_service)) -> ResultDetailResponse:
    record = service.results.get(job_id)
    if not record:
        raise HTTPException(status_code=404, detail="util job not found")
    return ResultDetailResponse(status="success", data=_to_record(record.to_dict()))


@router.get("/{job_id}/json", summary="Скачать JSON-файл результата утилиты")
def util_job_json(job_id: str, service: UtilityService = Depends(get_utility_service)) -> FileResponse:
    path = service.get_job_json_path(job_id)
    if not path:
        raise HTTPException(status_code=404, detail="JSON-файл для этой утилиты не найден")
    return FileResponse(path, media_type="application/json", filename=path.name)


@router.post("/run/{utility_id}", response_model=ResultDetailResponse, summary="Запустить утилиту (универсальный API)")
def util_run_generic(
    utility_id: str,
    req: GenericUtilityRunRequest,
    background: BackgroundTasks,
    service: UtilityService = Depends(get_utility_service),
) -> ResultDetailResponse:
    record_dict = service.start_job_generic(utility_id, req.parameters)
    job_id = record_dict["id"]
    background.add_task(service.execute_job, job_id)
    record = _to_record(record_dict)
    meta = {"success": False, "queued": True, "utility_id": utility_id}
    return ResultDetailResponse(status="success", data=record, meta=meta)


@router.post("/run", response_model=ResultDetailResponse, summary="Запустить утилиту (legacy)")
def util_run(
    req: UtilityRunRequest,
    background: BackgroundTasks,
    service: UtilityService = Depends(get_utility_service),
) -> ResultDetailResponse:
    record_dict = service.start_job(req)
    job_id = record_dict["id"]
    background.add_task(service.execute_job, job_id)
    record = _to_record(record_dict)
    meta = {"success": False, "queued": True, "legacy": True}
    return ResultDetailResponse(status="success", data=record, meta=meta)


__all__ = ["router"]
