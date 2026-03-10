"""HTTP API client used by the Streamlit frontend."""
from __future__ import annotations

import time
from typing import Any, Dict, Iterable, List, Optional

import requests

from shared.catalogs import ALARM_TESTS_CATALOG, SYNC_TESTS_CATALOG, STAT_TEST_CATALOG, COMM_TEST_CATALOG

from models import (
    MaskEnable,
    DeviceInfo,
    HistoryLimit,
    StopTestResponse,
    TestCatalogs,
    TestRunRecord,
    TestRunResponse,
    UtilityJobRecord,
    UtilityJobResponse
)


class BackendApiError(RuntimeError):
    """Raised when the backend API request fails."""


class BackendApiClient:
    """Typed client wrapper around backend REST endpoints."""

    def __init__(self, base_url: str, *, default_timeout: int = 100) -> None:
        self._base_url = base_url.rstrip("/")
        self._session = requests.Session()
        self._default_timeout = default_timeout
        self._catalog_cache: Optional[tuple[float, TestCatalogs]] = None
        self._catalog_ttl = 30

    # Low level helpers ------------------------------------------------
    def _build_url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return f"{self._base_url}{path}"

    def _request(
            self,
            method: str,
            path: str,
            *,
            timeout: Optional[int] = None,
            params: Optional[Dict[str, Any]] = None,
            json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = self._build_url(path)
        try:
            response = self._session.request(
                method,
                url,
                timeout=timeout or self._default_timeout,
                params=params,
                json=json,
            )
        except requests.RequestException as exc:  # pragma: no cover - thin wrapper
            raise BackendApiError(f"{method} {path}: {exc}") from exc
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:  # pragma: no cover - thin wrapper
            body = (response.text or "")[:400]
            raise BackendApiError(f"{method} {path}: {exc} | body: {body}") from exc
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise BackendApiError(f"{method} {path}: invalid JSON response") from exc

    def _ensure_envelope(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            raise BackendApiError("unexpected response type")

        status = payload.get("status")

        if status != "success":
            error = payload.get("error") or {}
            message = error.get("message") or "Backend error"
            raise BackendApiError(message)
        return payload

    def _unwrap(self, payload: Dict[str, Any]) -> tuple[Any, Dict[str, Any]]:
        envelope = self._ensure_envelope(payload)
        data = envelope.get("data")
        meta = envelope.get("meta") or {}
        return data, meta

    def _get(self, path: str, *, timeout: Optional[int] = None, params: Optional[Dict[str, Any]] = None) -> Dict[
        str, Any]:
        return self._request("GET", path, timeout=timeout, params=params)

    def _post(
            self,
            path: str,
            payload: Optional[Dict[str, Any]] = None,
            *,
            timeout: Optional[int] = None,
            params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self._request("POST", path, timeout=timeout, params=params, json=payload or {})

    # Tests ------------------------------------------------------------
    def get_test_catalogs(self) -> TestCatalogs:
        now = time.time()
        if self._catalog_cache and now - self._catalog_cache[0] < self._catalog_ttl:
            return self._catalog_cache[1]
        try:
            data, _ = self._unwrap(self._get("/tests/types"))
        except BackendApiError:
            data = {
                "alarm_tests": ALARM_TESTS_CATALOG,
                "sync_tests": SYNC_TESTS_CATALOG,
                "stat_tests": STAT_TEST_CATALOG,
                "comm_tests": COMM_TEST_CATALOG
            }
        catalogs = TestCatalogs.model_validate(data or {})
        self._catalog_cache = (now, catalogs)
        return catalogs

    def list_test_jobs(self) -> tuple[List[TestRunRecord], List[HistoryLimit]]:
        data, _ = self._unwrap(self._get("/tests/jobs", timeout=250))
        items = [TestRunRecord.model_validate(item) for item in (data or {}).get("items", [])]
        history = [HistoryLimit.model_validate(item) for item in (data or {}).get("history", [])]
        return items, history

    def get_test_status(self, job_id: str) -> TestRunRecord:
        data, _ = self._unwrap(self._get("/tests/status", params={"job_id": job_id}))
        return TestRunRecord.model_validate(data)

    def run_tests(self, payload: Dict[str, Any]) -> TestRunResponse:
        data = self._ensure_envelope(self._post("/tests/run", payload, timeout=120))
        return TestRunResponse.model_validate(data)

    def stop_test(self, job_id: str) -> StopTestResponse:
        data = self._ensure_envelope(self._post("/tests/stop", params={"job_id": job_id}))
        return StopTestResponse.model_validate(data)

    def download_jobfile(self, job_id: str) -> bytes:
        response = self._session.get(self._build_url("/tests/jobfile"), params={"job_id": job_id})
        response.raise_for_status()
        return response.content

    # Utilities --------------------------------------------------------
    def list_util_jobs(self) -> tuple[List[UtilityJobRecord], List[HistoryLimit]]:
        data, _ = self._unwrap(self._get("/utilities/jobs"))
        items = [UtilityJobRecord.model_validate(item) for item in (data or {}).get("items", [])]
        history = [HistoryLimit.model_validate(item) for item in (data or {}).get("history", [])]
        return items, history

    def get_util_status(self, job_id: str) -> UtilityJobRecord:
        data, _ = self._unwrap(self._get(f"/utilities/{job_id}"))
        return UtilityJobRecord.model_validate(data)

    def download_utility_json(self, job_id: str) -> bytes:
        try:
            resp = self._session.get(f"{self._base_url}/utilities/{job_id}/json", timeout=30)
        except Exception as exc:
            raise BackendApiError(f"Ошибка запроса /utilities/{job_id}/json: {exc}") from exc

        if resp.status_code != 200:
            raise BackendApiError(
                f"Не удалось скачать JSON для утилиты {job_id}: "
                f"{resp.status_code} {resp.text}"
            )

        return resp.content

    # Device -----------------------------------------------------------
    def ping_device(self, ip: str) -> bool:
        try:
            data = self._post("/ping", {"ip_address": ip})
        except BackendApiError:
            return False
        return bool(data.get("success")) if data else False

    def fetch_device_info(
            self,
            *,
            ip: str,
            password: str,
            snmp_type: str,
            viavi: Optional[Dict[str, Any]] = None,
            loopback: Optional[Dict[str, Any]] = None,
    ) -> DeviceInfo:
        payload = {
            "ip_address": ip,
            "password": password,
            "snmp_type": snmp_type,
            "viavi": viavi or {},
            "loopback": loopback or {},
        }
        data = self._post("/device/info", payload, timeout=500)
        return DeviceInfo.model_validate(data or {})

    def run_port_unmask(
            self,
            *,
            ip: str,
            password: str,
            snmp_type: str,
    ) -> MaskEnable:
        payload = {
            "ip_address": ip,
            "password": password,
            "snmp_type": snmp_type

        }
        data = self._post("/device/unmask", payload, timeout=50)
        return MaskEnable.model_validate(data or {})

    def traps_start(self) -> dict:
        return self._ensure_envelope(self._post("/traps/start"))

    def traps_stop(self) -> dict:
        return self._ensure_envelope(self._post("/traps/stop"))

    def traps_status(self) -> dict:
        data, _ = self._unwrap(self._get("/traps/status"))
        return data or {}

    def traps_events(self, *, limit: int = 200, order: str = "desc") -> list[dict]:
        data, _ = self._unwrap(self._get("/traps/events", params={"limit": limit, "order": order}))
        return data.get("items", [])

    def get_utilities_registry(self) -> list[dict]:
        data, _ = self._unwrap(self._get("/utilities/registry"))
        if isinstance(data, dict):
            return data.get("items", [])
        return data or []

    def run_utility(self, utility_id: str, params: dict) -> UtilityJobResponse:
        payload = {"parameters": params}
        data = self._ensure_envelope(
            self._post(f"/utilities/run/{utility_id}", payload))
        return UtilityJobResponse.model_validate(data)


def normalise_nodeids(nodeids: Iterable[str]) -> List[str]:
    return [node.replace(" ::", "::").replace(":: ", "::").replace(" / ", "/").strip() for node in nodeids]


__all__ = [
    "BackendApiClient",
    "BackendApiError",
    "normalise_nodeids",
]
