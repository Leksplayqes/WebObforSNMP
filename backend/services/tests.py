"""Service layer encapsulating pytest job orchestration."""
from __future__ import annotations

import copy
import datetime
import json
import os
import re
import sys
import time
from functools import lru_cache
from pathlib import Path
from subprocess import PIPE, STDOUT, Popen
from threading import RLock
from typing import Any, Dict, Iterable, List

try:
    import yaml
except ImportError:  # optional dependency
    yaml = None

from fastapi import BackgroundTasks, HTTPException
from shared.catalogs import ALARM_TESTS_CATALOG, COMM_TEST_CATALOG, OTHER_TEST_CATALOG, STAT_TEST_CATALOG, SYNC_TESTS_CATALOG

from ..config import PROJECT_ROOT, REPORT_DIR, ensure_config
from ..jobs import job_path, load_jobs_on_startup, save_job
from ..result_repository import ResultRecord, ResultRepository
from ..traps.context import trap_listener_context
from ..traps.manager import stop_trap_listener
from .models import TestsRunRequest
from .tunnels import TunnelConfigurationError, TunnelManagerError, TunnelPortsBusyError, TunnelService, get_tunnel_service

JOB_CONTEXT_DIR = REPORT_DIR / "contexts"
JOB_CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
CURRENT_EQ_PROFILES_FILE = PROJECT_ROOT / "CurrentEQ.yaml"


class TestExecutionService:
    def __init__(self, tunnel_service: TunnelService, *, project_root: Path = PROJECT_ROOT, report_dir: Path = REPORT_DIR) -> None:
        self._tunnel_service = tunnel_service
        self._project_root = project_root
        self._report_dir = report_dir
        self._results = ResultRepository(limit=20)
        self._running_procs: Dict[str, Popen] = {}
        self._lock = RLock()
        load_jobs_on_startup(self._results)

    def list_catalogs(self) -> Dict[str, Dict[str, str]]:
        return {"alarm_tests": ALARM_TESTS_CATALOG, "sync_tests": SYNC_TESTS_CATALOG, "stat_tests": STAT_TEST_CATALOG, "comm_tests": COMM_TEST_CATALOG, "other_tests": OTHER_TEST_CATALOG}

    def list_jobs(self) -> List[Dict[str, object]]:
        return [record.to_dict() for record in self._results.list()]

    def get_job(self, job_id: str) -> ResultRecord:
        record = self._results.get(job_id)
        if not record:
            raise HTTPException(status_code=404, detail="job not found")
        return record

    def job_file(self, job_id: str) -> Path:
        return job_path(job_id)

    def run(self, request: TestsRunRequest, background_tasks: BackgroundTasks) -> Dict[str, object]:
        job_id = _generate_job_id(request.test_type)
        nodeids = [_norm_nodeid(x) for x in (request.selected_tests or []) if x.strip()]
        if not nodeids:
            raise HTTPException(status_code=400, detail="Не выбраны тесты для запуска")

        cfg = ensure_config()
        devices = _extract_devices(request, cfg)
        if not devices:
            settings = request.settings if isinstance(request.settings, dict) else {}
            target_ip = str(settings.get("target_device_ip") or "").strip()
            if target_ip:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Профиль устройства {target_ip} не найден. "
                        "Нажмите ‘Проверить подключение’ для выбранного профиля и запустите тесты снова."
                    ),
                )
            raise HTTPException(status_code=400, detail="Не настроены устройства для запуска тестов")
        selected_device = devices[0]
        ip = selected_device.get("ipaddr") or ""
        device_password = selected_device.get("pass") or selected_device.get("password") or ""
        lease_key = self._lease_key(job_id)

        try:
            lease = self._tunnel_service.reserve(lease_key, "tests", ip=ip, username="admin", password=device_password, ttl=3600.0, track=True)
        except TunnelPortsBusyError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except TunnelConfigurationError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except TunnelManagerError as exc:
            raise HTTPException(status_code=500, detail=f"Ошибка подготовки туннеля: {exc}") from exc

        context_path = JOB_CONTEXT_DIR / f"{_safe_filename(job_id)}.json"
        _write_job_context(context_path, _build_job_context(cfg, selected_device, lease.port))

        started = time.time()
        payload: Dict[str, object] = {
            "id": job_id,
            "config": request.model_dump(),
            "started": started,
            "finished": None,
            "summary": {"status": "queued", "total": 0, "passed": 0, "failed": 0, "skipped": 0, "duration": 0.0},
            "cases": [],
            "stdout": "",
            "stderr": "",
            "returncode": None,
            "expected_total": None,
            "lease_port": lease.port,
            "device": selected_device,
            "devices": devices,
            "context_path": str(context_path),
            "title": _make_title(nodeids),
        }
        try:
            record = self._results.create(record_id=job_id, type="tests", status="queued", payload=payload, started_at=started)
            save_job(job_id, self._results)
            background_tasks.add_task(self._execute_tests, job_id, nodeids)
            return {"success": True, "job_id": job_id, "record": record.to_dict()}
        except Exception:
            self._tunnel_service.release(lease_key)
            raise

    def stop(self, job_id: str) -> Dict[str, object]:
        try:
            record = self.get_job(job_id)
        except HTTPException:
            return {"success": False, "error": "job not found"}
        job = record.payload
        proc = self._running_procs.get(job_id)
        if proc:
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except Exception:
                    proc.kill()
            finally:
                with self._lock:
                    self._running_procs.pop(job_id, None)
                if (job.get("trap") or {}).get("started_by_job"):
                    stop_trap_listener()
        job["returncode"] = getattr(proc, "returncode", None)
        job["finished"] = time.time()
        job["summary"] = _recalc_summary(job.get("cases") or [], finished=True)
        self._results.update(job_id, status="stopped", payload=job, finished_at=job["finished"])
        save_job(job_id, self._results)
        self._tunnel_service.release(self._lease_key(job_id))
        return {"success": True, "message": "job stopped"}

    def _lease_key(self, job_id: str) -> str:
        return f"tests:{job_id}"

    def _execute_tests(self, job_id: str, nodeids: Iterable[str]) -> None:
        record = self._results.get(job_id)
        if not record:
            return
        payload = record.payload
        report_path = str(self._report_dir / f"{_safe_filename(job_id)}.xml")
        cmd = [sys.executable, "-m", "pytest", "-vv", "-rA", "--tb=short", "--color=no", f"--junitxml={report_path}", *nodeids]
        env = os.environ.copy()
        context_path = payload.get("context_path")
        if context_path:
            env["OIDSTATUS_TEST_CONTEXT"] = str(context_path)
            env["OIDSTATUS_CONTEXT_FILE"] = str(context_path)
        proc = Popen(cmd, cwd=str(self._project_root), env=env, text=True, stdout=PIPE, stderr=STDOUT, bufsize=1, universal_newlines=True)
        with self._lock:
            self._running_procs[job_id] = proc

        collect_re = re.compile(r"collected\s+(\d+)\s+items?")
        cases_map: Dict[str, Dict[str, object]] = {}
        payload.update({"stdout": "", "stderr": "", "cases": [], "summary": {"status": "running", "total": 0, "passed": 0, "failed": 0, "skipped": 0, "duration": 0.0}})
        self._results.update(job_id, status="running", payload=payload)
        save_job(job_id, self._results)

        with trap_listener_context() as (trap_started_by_job, trap_start_result):
            payload["trap"] = {"enabled": True, "started_by_job": trap_started_by_job, "pid": trap_start_result.get("pid"), "start_result": trap_start_result}
            try:
                if proc.stdout is not None:
                    for line in proc.stdout:
                        if mcol := collect_re.search(line):
                            payload["expected_total"] = int(mcol.group(1))
                        payload["stdout"] += line
                        if match := _VERBOSE_LINE.match(line.strip()):
                            nodeid = _norm_nodeid(match.group("nodeid").strip())
                            case = cases_map.get(nodeid) or {"name": nodeid.split("::")[-1], "nodeid": nodeid, "status": match.group("status"), "duration": None, "message": None}
                            case["status"] = match.group("status")
                            cases_map[nodeid] = case
                            payload["cases"] = list(cases_map.values())
                            payload["summary"] = _recalc_summary(payload["cases"], finished=False)
                            self._results.update(job_id, status="running", payload=payload)
                            save_job(job_id, self._results)
                proc.wait()
                payload["returncode"] = proc.returncode
                payload["finished"] = time.time()
                if os.path.exists(report_path):
                    cases, _ = _parse_junit_report(report_path)
                    payload["cases"] = cases
                    payload["summary"] = _recalc_summary(cases, finished=True)
                elif not payload.get("cases"):
                    payload["summary"] = {"status": "error", "total": 0, "passed": 0, "failed": 1, "skipped": 0, "duration": 0.0, "message": "pytest did not produce junit xml; check stdout/stderr"}
                final_state = "completed" if payload["summary"].get("status") == "passed" else "failed"
                self._results.update(job_id, status=final_state, payload=payload, finished_at=payload.get("finished"))
                save_job(job_id, self._results)
            finally:
                with self._lock:
                    self._running_procs.pop(job_id, None)
                self._tunnel_service.release(self._lease_key(job_id))

    @property
    def results(self) -> ResultRepository:
        return self._results



def _generate_job_id() -> str:
    import json
    with open(r"C:\Users\mikhailov_gs.SUPERTEL\PycharmProjects\STwebTestingNew\ui_state.json", 'r',
              encoding='utf-8') as js:
        data = json.load(js)
    return f"{datetime.datetime.now():%d-%m-%Y %H-%M-%S} - {data['test_type_radio']} tests"


def _generate_job_id(test_type: str = "tests") -> str:
    return f"{datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')}-{_safe_filename(test_type or 'tests')}"


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "job")).strip("_") or "job"


def _write_job_context(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _load_profile_registry() -> Dict[str, Any]:
    """Load the frontend device profile registry from CurrentEQ.yaml.

    The file may contain real YAML (written by MainConnectFunc) or JSON
    (written by older frontend code). Backend test launch must understand both
    formats so it can build an immutable per-job snapshot for the selected IP.
    """
    if not CURRENT_EQ_PROFILES_FILE.exists():
        return {}
    try:
        text = CURRENT_EQ_PROFILES_FILE.read_text(encoding="utf-8")
    except Exception:
        return {}
    if not text.strip():
        return {}

    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    if yaml is not None:
        try:
            data = yaml.safe_load(text) or {}
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    return {}


def _profile_from_registry(target_ip: str) -> Dict[str, Any] | None:
    if not target_ip:
        return None
    payload = _load_profile_registry()
    devices = payload.get("devices") if isinstance(payload, dict) else None
    if isinstance(devices, dict) and isinstance(devices.get(target_ip), dict):
        return copy.deepcopy(devices[target_ip])

    current = payload.get("CurrentEQ") if isinstance(payload, dict) else None
    if isinstance(current, dict):
        current_ip = str(current.get("ipaddr") or current.get("ip_address") or "").strip()
        if current_ip == target_ip:
            return copy.deepcopy(current)
    return None


def _normalise_snmp_type(value: Any) -> str:
    key = str(value or "").strip().lower().replace("_", "").replace("-", "")
    if not key:
        return "SnmpV2"
    if key in {"snmpv3", "snmp3", "v3"} or key.endswith("v3") or key.endswith("3"):
        return "SnmpV3"
    if key in {"snmpv2", "snmpv2c", "snmp2", "v2", "v2c"} or key.endswith("v2") or key.endswith("2"):
        return "SnmpV2"
    return str(value).strip()


def _normalise_device_profile(item: Dict[str, Any], fallback_name: str = "target") -> Dict[str, Any]:
    profile = copy.deepcopy(item)
    profile["pass"] = profile.get("pass") if profile.get("pass") is not None else profile.get("password", "")
    profile["password"] = profile.get("password") if profile.get("password") is not None else profile.get("pass", "")
    profile["ipaddr"] = str(profile.get("ipaddr") or profile.get("ip_address") or "").strip()
    profile["name"] = str(profile.get("name") or fallback_name or "target")
    profile["snmp_type"] = _normalise_snmp_type(profile.get("snmp_type"))
    profile.setdefault("slots_dict", {})
    profile.setdefault("loopback", {})
    profile.setdefault("active_slots", {})

    if not isinstance(profile.get("viavi_config"), dict):
        viavi_source = profile.get("viavi")
        if not isinstance(viavi_source, dict):
            viavi_block = profile.get("VIAVIcontrol")
            if isinstance(viavi_block, dict):
                viavi_source = viavi_block.get("settings")
        if isinstance(viavi_source, dict):
            profile["viavi_config"] = copy.deepcopy(viavi_source)

    if not isinstance(profile.get("wiring"), list):
        wiring_source = profile.get("viavi_wiring")
        if not isinstance(wiring_source, list):
            viavi_block = profile.get("VIAVIcontrol")
            if isinstance(viavi_block, dict):
                wiring_source = viavi_block.get("wiring")
        if isinstance(wiring_source, list):
            profile["wiring"] = copy.deepcopy(wiring_source)

    return profile


def _build_job_context(cfg: Dict[str, Any], selected_device: Dict[str, Any], snmp_port: int) -> Dict[str, Any]:
    context = copy.deepcopy(cfg)
    profile = _normalise_device_profile(selected_device)
    profile["snmp_port"] = int(snmp_port)

    viavi_block = copy.deepcopy(context.get("VIAVIcontrol") if isinstance(context.get("VIAVIcontrol"), dict) else {})
    if isinstance(profile.get("viavi_config"), dict):
        viavi_block["settings"] = copy.deepcopy(profile["viavi_config"])
    if isinstance(profile.get("wiring"), list):
        viavi_block["wiring"] = copy.deepcopy(profile["wiring"])
    if viavi_block:
        context["VIAVIcontrol"] = viavi_block
        if isinstance(viavi_block.get("settings"), dict):
            profile["viavi_config"] = copy.deepcopy(viavi_block["settings"])
        if isinstance(viavi_block.get("wiring"), list):
            profile["wiring"] = copy.deepcopy(viavi_block["wiring"])

    context["CurrentEQ"] = profile
    context.setdefault("Devices", {})
    if profile.get("ipaddr"):
        context["Devices"][profile["ipaddr"]] = copy.deepcopy(profile)
    return context


def _norm_nodeid(node_id: str) -> str:
    return node_id.replace(" ::", "::").replace(":: ", "::").replace(" / ", "/").strip()


def _extract_devices(request: TestsRunRequest, cfg: Dict[str, object]) -> List[Dict[str, Any]]:
    settings = request.settings if isinstance(request.settings, dict) else {}
    target_ip = str(settings.get("target_device_ip") or "").strip()

    if isinstance(settings.get("device"), dict) and str(settings["device"].get("ipaddr") or settings["device"].get("ip_address") or "").strip():
        return [_normalise_device_profile(settings["device"])]
    if isinstance(settings.get("devices"), list):
        devices = [_normalise_device_profile(item, f"device-{idx + 1}") for idx, item in enumerate(settings["devices"]) if isinstance(item, dict)]
        devices = [item for item in devices if item.get("ipaddr")]
        if devices:
            return devices

    registry_profile = _profile_from_registry(target_ip)
    if registry_profile:
        return [_normalise_device_profile(registry_profile)]

    for registry in [cfg.get("Devices"), cfg.get("devices")]:
        if target_ip and isinstance(registry, dict) and isinstance(registry.get(target_ip), dict):
            return [_normalise_device_profile(registry[target_ip])]

    current = cfg.get("CurrentEQ") if isinstance(cfg, dict) else None
    if isinstance(current, dict) and (current.get("ipaddr") or current.get("ip_address")):
        current_ip = str(current.get("ipaddr") or current.get("ip_address") or "").strip()
        # Не используем старый CurrentEQ, если пользователь явно выбрал другой IP.
        if not target_ip or current_ip == target_ip:
            return [_normalise_device_profile(current, "current")]

    return []


def _make_title(nodeids: Iterable[str]) -> str:
    names = [{**{v: k for k, v in SYNC_TESTS_CATALOG.items()}, **{v: k for k, v in ALARM_TESTS_CATALOG.items()}, **{v: k for k, v in COMM_TEST_CATALOG.items()}}.get(n, n) for n in nodeids]
    return names[0] if len(names) == 1 else f"{len(names)} тестов: {', '.join(names)}"


def _recalc_summary(cases: Iterable[Dict[str, object]], finished: bool) -> Dict[str, object]:
    cases_list = list(cases)
    total = len(cases_list)
    passed = sum(1 for case in cases_list if case["status"] == "PASSED")
    failed = sum(1 for case in cases_list if case["status"] in ("FAILED", "ERROR"))
    skipped = sum(1 for case in cases_list if case["status"] == "SKIPPED")
    duration = sum(float(case.get("duration") or 0.0) for case in cases_list)
    return {"status": "running" if not finished else ("passed" if failed == 0 else "failed"), "total": total, "passed": passed, "failed": failed, "skipped": skipped, "duration": duration}


def _parse_junit_report(xml_path: str) -> tuple[List[Dict[str, object]], Dict[str, object]]:
    import xml.etree.ElementTree as ET
    cases: List[Dict[str, object]] = []
    for testcase in ET.parse(xml_path).getroot().findall(".//testcase"):
        name = testcase.get("name") or ""
        classname = testcase.get("classname") or ""
        duration = float(testcase.get("time") or 0.0)
        nodeid = f"{classname}::{name}" if classname else name
        status, message = "PASSED", None
        for tag, value in [("failure", "FAILED"), ("error", "ERROR"), ("skipped", "SKIPPED")]:
            el = testcase.find(tag)
            if el is not None:
                status, message = value, (el.get("message") or "").strip()
                break
        cases.append({"name": name, "nodeid": nodeid, "status": status, "duration": duration, "message": message})
    return cases, _recalc_summary(cases, finished=True)


@lru_cache()
def get_test_service() -> TestExecutionService:
    return TestExecutionService(get_tunnel_service())


_VERBOSE_LINE = re.compile(r"^(?P<nodeid>[^ ]+::[^\s]+?)\s+(?P<status>PASSED|FAILED|ERROR|SKIPPED|XPASS|XFAIL)")

__all__ = ["TestExecutionService", "get_test_service"]
