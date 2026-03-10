"""Endpoints to manage execution results history."""
from __future__ import annotations

from typing import Iterable, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from .models import (
    HistoryLimit,
    ResultDetailResponse,
    ResultListData,
    ResultListResponse,
    ResultRecordModel,
    SuccessResponse,
)
from backend.result_repository import ResultRecord, ResultRepository
from backend.services import TestExecutionService, UtilityService, get_test_service, get_utility_service

router = APIRouter(prefix="/results", tags=["results"])


def _convert(record: ResultRecord) -> ResultRecordModel:
    return ResultRecordModel.model_validate(record.to_dict())


def _limits(*repos: ResultRepository) -> List[HistoryLimit]:
    limits: List[HistoryLimit] = []
    for repo in repos:
        limits.append(
            HistoryLimit(type=getattr(repo, "_type", "unknown"), limit=repo.limit, total=repo.count())
        )
    return limits


def _attach_repo_type(repo: ResultRepository, repo_type: str) -> ResultRepository:
    setattr(repo, "_type", repo_type)
    return repo


@router.get("", response_model=ResultListResponse, summary="Получить историю запусков")
def list_results(
        job_type: Optional[str] = Query(None, description="Фильтр по типу: tests или utilities"),
        tests: TestExecutionService = Depends(get_test_service),
        utils: UtilityService = Depends(get_utility_service),
) -> ResultListResponse:
    repos: List[ResultRepository] = []
    items: List[ResultRecordModel] = []

    test_repo = _attach_repo_type(tests.results, "tests")
    util_repo = _attach_repo_type(utils.results, "utilities")

    def append_records(source: Iterable[ResultRecord]) -> None:
        for record in source:
            items.append(_convert(record))

    if job_type is None or job_type == "tests":
        repos.append(test_repo)
        append_records(test_repo.list())
    if job_type is None or job_type == "utilities":
        repos.append(util_repo)
        append_records(util_repo.list())

    items.sort(key=lambda record: record.updated_at or record.created_at or 0.0, reverse=True)
    data = ResultListData(items=items, history=_limits(*repos))
    return ResultListResponse(status="success", data=data)


@router.get("/{result_id}", response_model=ResultDetailResponse, summary="Получить результат по идентификатору")
def get_result(
        result_id: str,
        job_type: Optional[str] = Query(None, description="Тип записи: tests или utilities"),
        tests: TestExecutionService = Depends(get_test_service),
        utils: UtilityService = Depends(get_utility_service),
) -> ResultDetailResponse:
    repos: List[ResultRepository] = []
    if job_type in (None, "tests"):
        repos.append(_attach_repo_type(tests.results, "tests"))
    if job_type in (None, "utilities"):
        repos.append(_attach_repo_type(utils.results, "utilities"))

    for repo in repos:
        record = repo.get(result_id)
        if record:
            return ResultDetailResponse(status="success", data=_convert(record))

    raise HTTPException(status_code=404, detail="result not found")


@router.delete("/{result_id}", response_model=SuccessResponse, summary="Удалить запись из истории")
def delete_result(
        result_id: str,
        job_type: Optional[str] = Query(None, description="Тип записи: tests или utilities"),
        tests: TestExecutionService = Depends(get_test_service),
        utils: UtilityService = Depends(get_utility_service),
) -> SuccessResponse:
    repos: List[ResultRepository] = []
    if job_type in (None, "tests"):
        repos.append(_attach_repo_type(tests.results, "tests"))
    if job_type in (None, "utilities"):
        repos.append(_attach_repo_type(utils.results, "utilities"))

    deleted = False
    for repo in repos:
        deleted = repo.delete(result_id) or deleted

    if not deleted:
        raise HTTPException(status_code=404, detail="result not found")

    return SuccessResponse(status="success")


all = ["router"]
