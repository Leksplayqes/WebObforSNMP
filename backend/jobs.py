"""Persistence helpers for test job metadata."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict

from .config import JOBS_DIR
from .result_repository import ResultRecord, ResultRepository


def job_path(job_id: str) -> Path:
    return JOBS_DIR / f"{job_id}.json"


def save_job(job_id: str, repository: ResultRepository) -> None:
    record = repository.get(job_id)
    if not record:
        return
    path = job_path(job_id)
    try:
        with path.open("w", encoding="utf-8") as file:
            json.dump(record.to_dict(), file, ensure_ascii=False, indent=2)
    except Exception as exc:  # pragma: no cover - logging only
        print(f"[jobs] save file for {job_id}: {exc}")


def _record_from_legacy(job: Dict[str, Any]) -> ResultRecord:
    job_id = job.get("id") or ""
    summary = job.get("summary") or {}
    status = summary.get("status") or "unknown"
    started = job.get("started")
    finished = job.get("finished")
    created = started or time.time()
    updated = finished or created
    return ResultRecord(
        id=job_id,
        type="tests",
        status=status,
        created_at=created,
        updated_at=updated,
        started_at=started,
        finished_at=finished,
        payload=job,
    )


def load_jobs_on_startup(repository: ResultRepository) -> None:
    for path in sorted(JOBS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime):
        try:
            with path.open("r", encoding="utf-8") as file:
                raw: Dict[str, Any] = json.load(file)
            if {"id", "type", "payload"}.issubset(raw.keys()):
                record = ResultRecord(
                    id=raw.get("id") or path.stem,
                    type=raw.get("type") or "tests",
                    status=raw.get("status") or "unknown",
                    created_at=raw.get("created_at") or time.time(),
                    updated_at=raw.get("updated_at") or time.time(),
                    started_at=raw.get("started_at"),
                    finished_at=raw.get("finished_at"),
                    payload=raw.get("payload") or {},
                )
            else:
                legacy = raw if isinstance(raw, dict) else {}
                legacy.setdefault("id", legacy.get("id") or path.stem)
                record = _record_from_legacy(legacy)
            repository.upsert(record)
        except Exception as exc:  # pragma: no cover - logging only
            print(f"[jobs] load failed {path.name}: {exc}")


__all__ = ["job_path", "save_job", "load_jobs_on_startup"]
