"""Service layer for long-running utility jobs (pluggable utilities)."""
from __future__ import annotations

import time
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import HTTPException

from ..result_repository import ResultRepository
from .tunnels import TunnelService, get_tunnel_service
from .utilities_core import ResultStore, UtilityError, UtilityJobRunner, UtilityRegistry
from .utility_plugins import register_all


class UtilityService:
    """Executes diagnostic utilities and tracks their progress.

    Основная идея масштабирования:
    - конкретные утилиты живут в plugins/ и регистрируются в UtilityRegistry
    - роуты/история/статусы/JSON-хранилище общие и не меняются при добавлении утилит
    """

    def __init__(self, tunnel_service: TunnelService) -> None:
        self._tunnel_service = tunnel_service

        repo = ResultRepository(limit=50)

        # backend/util_history/*.json
        base_dir = Path(__file__).resolve().parent.parent
        history_dir = base_dir / "util_history"

        self._store = ResultStore(repo=repo, history_dir=history_dir)
        self._store.load_from_disk()
        self._registry = UtilityRegistry()
        register_all(self._registry)

        self._runner = UtilityJobRunner(self)
    # -------------------------------------------------------
    # Public API: list/get
    # -------------------------------------------------------
    @property
    def results(self) -> ResultRepository:
        return self._store.repo

    @property
    def registry(self) -> UtilityRegistry:
        return self._registry

    @property
    def tunnel_service(self) -> TunnelService:
        return self._tunnel_service

    def get_job_json_path(self, job_id: str) -> Optional[Path]:
        return self._store.json_path(job_id)

    def registry_payload(self) -> Dict[str, Any]:
        """Data-driven description of utilities for UI."""
        items: list[Dict[str, Any]] = []
        for util in self._registry.list():
            items.append(
                {
                    "id": util.meta.id,
                    "title": util.meta.title,
                    "description": util.meta.description,
                    "tags": list(util.meta.tags),
                    "requires_tunnel": util.meta.requires_tunnel,
                    "default_timeout_sec": util.meta.default_timeout_sec,
                    "input_schema": util.input_schema(),
                    "output_schema": util.output_schema(),
                }
            )
        return {"items": items}

    # -------------------------------------------------------
    # Create + Execute jobs
    # -------------------------------------------------------
    def start_job_generic(self, utility_id: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Create a queued job for a given utility_id and params (new universal API)."""
        if not self._registry.get(utility_id):
            raise HTTPException(status_code=400, detail=f"Unsupported utility {utility_id}")

        job_id = uuid.uuid4().hex[:12]
        started = time.time()
        payload: Dict[str, Any] = {
            "id": job_id,
            "type": utility_id,
            "params": parameters,
            "result": None,
            "error": None,          # legacy string
            "error_obj": None,      # new structured error
            "started": started,
            "finished": None,
            "summary": {"status": "queued"},
        }
        self._store.create(record_id=job_id, type=utility_id, status="queued", payload=payload, started_at=started)
        rec = self._store.get(job_id)
        return rec.to_dict() if rec else {"id": job_id}

    def execute_job(self, job_id: str) -> None:
        """Execute a previously created job (called from BackgroundTasks)."""
        self._runner.execute(job_id)

    # -------------------------------------------------------
    # Backward-compatible API (old /utilities/run with UtilityRunRequest)
    # -------------------------------------------------------
    def start_job(self, request: Any) -> Dict[str, Any]:
        """Compatibility wrapper for existing UtilityRunRequest model."""
        utility_id = getattr(request, "utility", None)
        parameters = getattr(request, "parameters", None) or {}
        if not utility_id:
            raise HTTPException(status_code=400, detail="utility is required")
        return self.start_job_generic(str(utility_id), dict(parameters))

    def run(self, request: Any) -> Dict[str, Any]:
        """Synchronous run (compat)."""
        record_dict = self.start_job(request)
        job_id = record_dict["id"]
        self.execute_job(job_id)
        rec = self._store.get(job_id)
        if not rec:
            raise HTTPException(status_code=500, detail="utility job disappeared")
        payload = rec.to_dict()
        success = rec.status == "completed"
        err = None
        if isinstance(payload.get("payload"), dict):
            err = payload["payload"].get("error")
        return {"success": success, "record": payload, "error": err}

    # -------------------------------------------------------
    # Internal helpers used by runner/context
    # -------------------------------------------------------
    def _mark_running(self, job_id: str, payload: Dict[str, Any]) -> None:
        payload.setdefault("summary", {})["status"] = "running"
        self._store.update(job_id, status="running", payload=payload)

    def _report_progress(self, job_id: str, *, result: Any = None, summary: Optional[Dict[str, Any]] = None) -> None:
        rec = self._store.get(job_id)
        if not rec:
            return
        payload = rec.payload
        if result is not None:
            payload["result"] = result
        if summary:
            payload.setdefault("summary", {}).update(summary)
        # update duration in summary
        started = payload.get("started")
        if started:
            payload.setdefault("summary", {})["duration"] = max(time.time() - started, 0.0)
        self._store.update(job_id, status="running", payload=payload)

    def _set_structured_error(self, job_id: str, err: UtilityError) -> None:
        rec = self._store.get(job_id)
        if not rec:
            return
        payload = rec.payload
        payload["error_obj"] = err.to_dict()
        payload["error"] = err.message  # keep legacy string for old UI
        self._store.update(job_id, status="running", payload=payload)

    def _complete_job(self, job_id: str, payload: Dict[str, Any]) -> None:
        finished = time.time()
        payload["finished"] = finished
        duration = max(finished - (payload.get("started") or finished), 0.0)
        payload["duration"] = duration
        payload.setdefault("summary", {}).update({"status": "completed", "duration": duration})
        rec = self._store.update(job_id, status="completed", payload=payload, finished_at=finished)
        self._store.dump_final(rec)

    def _fail_job(self, job_id: str, payload: Dict[str, Any], err: UtilityError) -> None:
        finished = time.time()
        payload["finished"] = finished
        duration = max(finished - (payload.get("started") or finished), 0.0)
        payload["duration"] = duration
        payload["error_obj"] = err.to_dict()
        payload["error"] = err.message
        payload.setdefault("summary", {}).update({"status": "failed", "duration": duration, "message": err.message})
        rec = self._store.update(job_id, status="failed", payload=payload, finished_at=finished)
        self._store.dump_final(rec)


@lru_cache()
def get_utility_service() -> UtilityService:
    return UtilityService(get_tunnel_service())


__all__ = ["UtilityService", "get_utility_service"]
