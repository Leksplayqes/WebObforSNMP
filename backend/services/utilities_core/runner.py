"""Utility job runner (synchronous execution invoked from BackgroundTasks)."""
from __future__ import annotations

import time
from typing import Any, Dict

from .base import UtilityContext, UtilityError


class UtilityJobRunner:
    def __init__(self, service: Any) -> None:
        # service is UtilityService (to avoid circular typing)
        self._service = service

    def execute(self, job_id: str) -> None:
        record = self._service.results.get(job_id)
        if not record:
            return

        util_id = record.type
        payload = record.payload
        params_raw = payload.get("params", {}) or {}

        util = self._service.registry.get(util_id)
        if not util:
            self._service._fail_job(job_id, payload, UtilityError("UNKNOWN_UTILITY", f"Unknown utility: {util_id}"))
            return

        # mark running
        self._service._mark_running(job_id, payload)

        ctx = UtilityContext(job_id=job_id, service=self._service)

        try:
            params = util.validate(params_raw)
        except Exception as exc:
            self._service._fail_job(
                job_id,
                payload,
                UtilityError("VALIDATION", f"Invalid parameters: {exc}", details={"utility": util_id}, retryable=False),
            )
            return

        try:
            out = util.run(ctx, params)
            # normalize
            payload["result"] = out.model_dump() if hasattr(out, "model_dump") else out
            self._service._complete_job(job_id, payload)
        except UtilityError as ue:
            self._service._fail_job(job_id, payload, ue)
        except Exception as exc:
            self._service._fail_job(
                job_id,
                payload,
                UtilityError("UNEXPECTED", str(exc), details={"utility": util_id}, retryable=False),
            )
