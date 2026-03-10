"""FastAPI routes for managing pytest executions."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse

from backend.services.models import (
    CatalogsResponse,
    HistoryLimit,
    ResultDetailResponse,
    ResultListData,
    ResultListResponse,
    ResultRecordModel,
    SuccessResponse,
    TestsRunRequest,
)
from .services import TestExecutionService, get_test_service

router = APIRouter(prefix="/tests", tags=["tests"])


@router.get("/types", response_model=CatalogsResponse, summary="Справочники тестов")
def get_types(service: TestExecutionService = Depends(get_test_service)) -> CatalogsResponse:
    return CatalogsResponse(status="success", data=service.list_catalogs())


def _convert(record: dict) -> ResultRecordModel:
    summary = record.get("summary") or {}
    if summary.get("status") is None:
        summary = {**summary, "status": record.get("status")}
        record = {**record, "summary": summary}
    return ResultRecordModel.model_validate(record)


@router.get("/jobs", response_model=ResultListResponse, summary="История прогонов тестов")
def list_jobs(service: TestExecutionService = Depends(get_test_service)) -> ResultListResponse:
    repo = service.results
    items = [_convert(record.to_dict()) for record in repo.list()]
    data = ResultListData(
        items=items,
        history=[HistoryLimit(type="tests", limit=repo.limit, total=repo.count())],
    )
    return ResultListResponse(status="success", data=data)


@router.get("/status", response_model=ResultDetailResponse, summary="Статус конкретного прогона")
def tests_status(job_id: str, service: TestExecutionService = Depends(get_test_service)) -> ResultDetailResponse:
    record = service.get_job(job_id)
    return ResultDetailResponse(status="success", data=_convert(record.to_dict()))


@router.post("/run", response_model=ResultDetailResponse, summary="Запустить тесты")
def tests_run(
        req: TestsRunRequest,
        background_tasks: BackgroundTasks,
        service: TestExecutionService = Depends(get_test_service),
):
    result = service.run(req, background_tasks)
    record = _convert(result.get("record") or {})
    meta = {"success": bool(result.get("success", False)), "job_id": result.get("job_id")}
    if result.get("error"):
        meta["error"] = result["error"]
    return ResultDetailResponse(status="success", data=record, meta=meta)


@router.post("/stop", response_model=SuccessResponse, summary="Остановить прогоны")
def tests_stop(job_id: str, service: TestExecutionService = Depends(get_test_service)) -> SuccessResponse:
    result = service.stop(job_id)
    if not result.get("success", False) and result.get("error") == "job not found":
        raise HTTPException(status_code=404, detail=result.get("error"))
    meta = {"success": bool(result.get("success", False))}
    if result.get("message"):
        meta["message"] = result["message"]
    if result.get("error"):
        meta["error"] = result["error"]
    return SuccessResponse(status="success", meta=meta)


@router.get("/jobfile")
def download_jobfile(job_id: str, service: TestExecutionService = Depends(get_test_service)):
    path = service.job_file(job_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="job file not found")
    return FileResponse(str(path), media_type="application/json", filename=f"{job_id}.json")


__all__ = ["router"]
