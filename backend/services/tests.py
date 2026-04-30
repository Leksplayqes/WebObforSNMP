"""Service layer encapsulating pytest job orchestration."""
from __future__ import annotations

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
from typing import Dict, Iterable, List, Optional
from fastapi import BackgroundTasks, HTTPException
import streamlit as st
from shared.catalogs import ALARM_TESTS_CATALOG, SYNC_TESTS_CATALOG, STAT_TEST_CATALOG, COMM_TEST_CATALOG, OTHER_TEST_CATALOG
from ..config import PROJECT_ROOT, REPORT_DIR, ensure_config, json_set
from ..jobs import job_path, load_jobs_on_startup, save_job
from backend.services.models import TestsRunRequest
from ..result_repository import ResultRecord, ResultRepository
from ..traps.context import trap_listener_context
from ..traps.manager import stop_trap_listener
from .tunnels import (
    TunnelConfigurationError,
    TunnelManagerError,
    TunnelPortsBusyError,
    TunnelService,
    get_tunnel_service,
)

DEFAULT_API_BASE_URL = "http://192.168.72.55:8000"


class TestExecutionService:

    def __init__(
            self,
            tunnel_service: TunnelService,
            *,
            project_root: Path = PROJECT_ROOT,
            report_dir: Path = REPORT_DIR,
    ) -> None:
        self._tunnel_service = tunnel_service
        self._project_root = project_root
        self._report_dir = report_dir
        self._results = ResultRepository(limit=20)
        self._running_procs: Dict[str, Popen] = {}
        self._lock = RLock()
        load_jobs_on_startup(self._results)

    # ------------------------------------------------------------------
    def list_catalogs(self) -> Dict[str, Dict[str, str]]:
        return {"alarm_tests": ALARM_TESTS_CATALOG, "sync_tests": SYNC_TESTS_CATALOG, "stat_tests": STAT_TEST_CATALOG,
                "comm_tests": COMM_TEST_CATALOG, "other_tests": OTHER_TEST_CATALOG}

    def list_jobs(self) -> List[Dict[str, object]]:
        return [record.to_dict() for record in self._results.list()]

    def get_job(self, job_id: str) -> ResultRecord:
        record = self._results.get(job_id)
        if not record:
            raise HTTPException(status_code=404, detail="job not found")
        return record

    def job_file(self, job_id: str) -> Path:
        return job_path(job_id)

    # ------------------------------------------------------------------
    def run(self, request: TestsRunRequest, background_tasks: BackgroundTasks) -> Dict[str, object]:
        if self._running_procs:
            raise HTTPException(
                status_code=409,
                detail="Уже выполняется тестовый запуск. Параллельные прогоны отключены из-за общего CurrentEQ.",
            )
        job_id = _generate_job_id()
        nodeids = [_norm_nodeid(x) for x in (request.selected_tests or []) if x.strip()]
        if not nodeids:
            raise HTTPException(status_code=400, detail="Не выбраны тесты для запуска")

        devices = _extract_devices(request, ensure_config())
        if not devices:
            raise HTTPException(
                status_code=400,
                detail="Не настроены устройства для запуска тестов: передайте settings.devices или заполните CurrentEQ",
            )
        selected_device = devices[0]
        ip = selected_device.get("ipaddr") or ""
        password = selected_device.get("password") or ""

        name_by_nodeid = {**{v: k for k, v in SYNC_TESTS_CATALOG.items()},
                          **{v: k for k, v in ALARM_TESTS_CATALOG.items()},
                          **{v: k for k, v in COMM_TEST_CATALOG.items()}}
        category_by_nodeid = {**{v: "Синхронизация" for v in SYNC_TESTS_CATALOG.values()},
                              **{v: "Аварии" for v in ALARM_TESTS_CATALOG.values()},
                              **{v: "Статистика" for v in STAT_TEST_CATALOG.values()},
                              **{v: "Коммутация" for v in COMM_TEST_CATALOG.values()}}
        names = [name_by_nodeid.get(n, n) for n in nodeids]
        categories = {category_by_nodeid.get(n) for n in nodeids if category_by_nodeid.get(n)}
        # Determine category label
        category_label = ""
        if len(categories) == 1:
            category_label = categories.pop()
        elif len(categories) > 1:
            category_label = " и ".join(sorted(categories))
        # Form title string
        if len(names) == 1:
            title = f"{category_label}: {names[0]}"
        else:
            if category_label:
                title = f"{len(names)} тестов: {category_label}: {', '.join(names)}"
            else:
                title = f"{len(names)} тестов: {', '.join(names)}"
        lease_key = self._lease_key(job_id)
        try:
            lease = self._tunnel_service.reserve(
                lease_key,
                "tests",
                ip=ip,
                username="admin",
                password=password,
                ttl=3600.0,
                track=True,
            )
        except TunnelPortsBusyError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except TunnelConfigurationError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except TunnelManagerError as exc:
            raise HTTPException(status_code=500, detail=f"Ошибка подготовки туннеля: {exc}") from exc

        started = time.time()
        payload: Dict[str, object] = {
            "id": job_id,
            "config": request.model_dump(),
            "started": started,
            "finished": None,
            "summary": {
                "status": "queued",
                "total": 0,
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "duration": 0.0,
            },
            "cases": [],
            "stdout": "",
            "stderr": "",
            "returncode": None,
            "expected_total": None,
            "lease_port": lease.port,
            "device": selected_device,
            "devices": devices,
            "title": title,
        }
        full_cfg_snapshot = dict(ensure_config() or {})
        current_eq_snapshot = dict((full_cfg_snapshot.get("CurrentEQ") or {}))
        current_eq_snapshot.update({
            "name": str(selected_device.get("name") or current_eq_snapshot.get("name") or ""),
            "ipaddr": str(selected_device.get("ipaddr") or current_eq_snapshot.get("ipaddr") or ""),
            "pass": str(selected_device.get("password") or current_eq_snapshot.get("pass") or ""),
        })
        full_cfg_snapshot["CurrentEQ"] = current_eq_snapshot
        payload["current_eq_snapshot"] = current_eq_snapshot
        safe_ip = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in str(selected_device.get("ipaddr") or ""))
        if safe_ip:
            snapshot_file = self._project_root / "device_contexts" / f"{safe_ip}.json"
            snapshot_file.parent.mkdir(parents=True, exist_ok=True)
            snapshot_file.write_text(json.dumps(full_cfg_snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
            payload["current_eq_snapshot_path"] = str(snapshot_file)
        try:
            record = self._results.create(
                record_id=job_id,
                type="tests",
                status="queued",
                payload=payload,
                started_at=started,
            )
            save_job(job_id, self._results)
        except Exception:
            self._tunnel_service.release(lease_key)
            raise

        try:
            background_tasks.add_task(self._execute_tests, job_id, nodeids)
        except Exception:
            self._tunnel_service.release(lease_key)
            raise
        return {"success": True, "job_id": job_id, "record": record.to_dict()}

    def stop(self, job_id: str) -> Dict[str, object]:
        try:
            record = self.get_job(job_id)
        except HTTPException:
            return {"success": False, "error": "job not found"}

        job = record.payload
        proc = self._running_procs.get(job_id)
        if not proc:
            if (job.get("summary") or {}).get("status") == "running":
                job["summary"]["status"] = "stopped"
                job["finished"] = time.time()
                self._results.update(
                    job_id,
                    status="stopped",
                    payload=job,
                    finished_at=job["finished"],
                )
                save_job(job_id, self._results)
            self._tunnel_service.release(self._lease_key(job_id))
            return {"success": True, "message": "job is not running"}

        try:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
            code = proc.returncode
        except Exception as exc:
            return {"success": False, "error": f"terminate failed: {exc}"}
        finally:
            with self._lock:
                self._running_procs.pop(job_id, None)

            # If the trap listener was started for this job, stop it as well.
            # (Safe to call multiple times; manager returns not_running if already stopped.)
            trap_info = (job.get("trap") or {}) if isinstance(job, dict) else {}
            if trap_info.get("started_by_job"):
                stop_trap_listener()

        cases = job.get("cases") or []
        job["returncode"] = code
        job["finished"] = time.time()
        job["summary"] = _recalc_summary(cases, finished=True)
        self._results.update(
            job_id,
            status="stopped",
            payload=job,
            finished_at=job["finished"],
        )
        save_job(job_id, self._results)
        self._tunnel_service.release(self._lease_key(job_id))
        return {"success": True, "message": "job stopped"}

    # Internal helpers -------------------------------------------------
    def _lease_key(self, job_id: str) -> str:
        return f"tests:{job_id}"

    def _execute_tests(self, job_id: str, nodeids: Iterable[str]) -> None:
        record = self._results.get(job_id)
        if not record:
            return

        payload = record.payload
        device_ctx = (payload.get("device") or {}) if isinstance(payload, dict) else {}
        snapshot_ctx = (payload.get("current_eq_snapshot") or {}) if isinstance(payload, dict) else {}
        if isinstance(device_ctx, dict):
            try:
                json_set(["CurrentEQ"], {
                    "name": str(device_ctx.get("name") or ""),
                    "ipaddr": str(device_ctx.get("ipaddr") or ""),
                    "pass": str(device_ctx.get("password") or device_ctx.get("pass") or ""),
                })
            except Exception as exc:
                payload["stderr"] = (payload.get("stderr") or "") + f"\n[WARN] failed to set CurrentEQ for job: {exc}\n"
                self._results.update(job_id, payload=payload)
                save_job(job_id, self._results)
        payload["expected_total"] = None
        report_path = str(self._report_dir / f"{job_id}.xml")
        self._results.update(job_id, payload=payload)
        save_job(job_id, self._results)

        cmd = [
            sys.executable,
            "-m",
            "pytest",
            "-vv",
            "-rA",
            "--tb=short",
            "--color=no",
            f"--junitxml={report_path}",
            *nodeids,
        ]
        proc_env = dict(os.environ)
        if isinstance(snapshot_ctx, dict) and snapshot_ctx:
            try:
                proc_env["OSMK_CURRENT_EQ_SNAPSHOT"] = json.dumps(snapshot_ctx, ensure_ascii=False)
            except Exception:
                pass
        snapshot_path = payload.get("current_eq_snapshot_path")
        if snapshot_path:
            proc_env["OSMK_CURRENT_EQ_SNAPSHOT_PATH"] = str(snapshot_path)
            proc_env["OSMK_CONFIG_SNAPSHOT_PATH"] = str(snapshot_path)

        proc = Popen(
            cmd,
            cwd=str(self._project_root),
            text=True,
            stdout=PIPE,
            stderr=STDOUT,
            env=proc_env,
            bufsize=1,
            universal_newlines=True,
        )
        with self._lock:
            self._running_procs[job_id] = proc

        collect_re = re.compile(r"collected\s+(\d+)\s+items?")
        cases_map: Dict[str, Dict[str, object]] = {}
        payload.update(
            {
                "stdout": "",
                "stderr": "",
                "cases": [],
                "summary": {
                    "status": "running",
                    "total": 0,
                    "passed": 0,
                    "failed": 0,
                    "skipped": 0,
                    "duration": 0.0,
                },
            }
        )
        payload["summary"]["status"] = "running"
        self._results.update(job_id, status="running", payload=payload)
        save_job(job_id, self._results)

        # ----------------- ВАЖНО: запускаем pytest с trap listener на время выполнения -----------------
        with trap_listener_context() as (trap_started_by_job, trap_start_result):
            payload["trap"] = {
                "enabled": True,
                "started_by_job": trap_started_by_job,
                "pid": trap_start_result.get("pid"),
                "start_result": trap_start_result,
            }
            self._results.update(job_id, payload=payload)
            save_job(job_id, self._results)
            try:
                if proc.stdout is not None:
                    for line in proc.stdout:
                        mcol = collect_re.search(line)
                        if mcol:
                            try:
                                payload["expected_total"] = int(mcol.group(1))
                            except Exception:
                                payload["expected_total"] = None
                        payload["stdout"] += line
                        match = _VERBOSE_LINE.match(line.strip())
                        if match:
                            nodeid = _norm_nodeid(match.group("nodeid").strip())
                            status = match.group("status")
                            case = cases_map.get(nodeid) or {
                                "name": nodeid.split("::")[-1],
                                "nodeid": nodeid,
                                "status": status,
                                "duration": None,
                                "message": None,
                            }
                            case["status"] = status
                            cases_map[nodeid] = case
                            payload["cases"] = list(cases_map.values())
                            payload["summary"] = _recalc_summary(payload["cases"], finished=False)
                            state = "running"
                            self._results.update(
                                job_id,
                                status=state,
                                payload=payload,
                            )
                            save_job(job_id, self._results)
                proc.wait()
                payload["returncode"] = proc.returncode
                payload["finished"] = time.time()
                self._results.update(job_id, payload=payload)
                save_job(job_id, self._results)

                try:
                    if os.path.exists(report_path):
                        final_cases, _ = _parse_junit_report(report_path)
                        final_map = {case["nodeid"]: case for case in final_cases}
                        for nodeid, live in list(cases_map.items()):
                            if nodeid in final_map:
                                merged = final_map[nodeid]
                                merged["status"] = live.get("status", merged["status"])
                                merged["duration"] = merged.get("duration") or live.get("duration")
                                merged["message"] = merged.get("message") or live.get("message")
                                final_map[nodeid] = merged
                        payload["cases"] = list(final_map.values())
                        payload["summary"] = _recalc_summary(payload["cases"], finished=True)
                        final_state = "completed" if payload["summary"].get("status") == "passed" else "failed"
                        self._results.update(
                            job_id,
                            status=final_state,
                            payload=payload,
                            finished_at=payload.get("finished"),
                        )
                        save_job(job_id, self._results)
                    elif not payload.get("cases"):
                        payload["summary"] = {
                            "status": "error",
                            "total": 0,
                            "passed": 0,
                            "failed": 1,
                            "skipped": 0,
                            "duration": 0.0,
                            "message": "pytest did not produce junit xml; check stdout/stderr",
                        }
                        self._results.update(
                            job_id,
                            status="failed",
                            payload=payload,
                            finished_at=payload.get("finished"),
                        )
                        save_job(job_id, self._results)
                except Exception as exc:
                    payload["summary"] = {
                        "status": "error",
                        "total": len(payload.get("cases") or []),
                        "passed": 0,
                        "failed": 1,
                        "skipped": 0,
                        "duration": 0.0,
                        "message": f"junit merge failed: {exc}",
                    }
                    self._results.update(
                        job_id,
                        status="failed",
                        payload=payload,
                        finished_at=payload.get("finished"),
                    )
                    save_job(job_id, self._results)
            finally:
                with self._lock:
                    self._running_procs.pop(job_id, None)
                self._tunnel_service.release(self._lease_key(job_id))
                if payload.get("finished") is None:
                    payload["finished"] = time.time()
                    self._results.update(
                        job_id,
                        payload=payload,
                        finished_at=payload["finished"],
                    )
                save_job(job_id, self._results)

    # Public accessors -------------------------------------------------

    @property
    def results(self) -> ResultRepository:
        return self._results


def _generate_job_id() -> str:
    import json
    with open(r"C:\Users\mikhailov_gs.SUPERTEL\PycharmProjects\STwebTestingNew\ui_state.json", 'r',
              encoding='utf-8') as js:
        data = json.load(js)
    return f"{datetime.datetime.now().strftime("%d-%m-%Y %H-%M")} - {data["test_type_radio"]} tests"


def _norm_nodeid(node_id: str) -> str:
    return node_id.replace(" ::", "::").replace(":: ", "::").replace(" / ", "/").strip()


def _extract_devices(request: TestsRunRequest, cfg: Dict[str, object]) -> List[Dict[str, str]]:
    devices: List[Dict[str, str]] = []
    raw_settings = request.settings or {}
    raw_devices = raw_settings.get("devices") if isinstance(raw_settings, dict) else None
    if isinstance(raw_devices, list):
        for idx, item in enumerate(raw_devices):
            if not isinstance(item, dict):
                continue
            ip = str(item.get("ipaddr") or "").strip()
            if not ip:
                continue
            devices.append(
                {
                    "name": str(item.get("name") or f"device-{idx + 1}").strip(),
                    "ipaddr": ip,
                    "password": str(item.get("password") or ""),
                }
            )
    if devices:
        return devices
    target_ip = ""
    if isinstance(raw_settings, dict):
        target_ip = str(raw_settings.get("target_device_ip") or "").strip()
    registry = (cfg.get("Devices") or {}) if isinstance(cfg, dict) else {}
    if target_ip and isinstance(registry, dict):
        reg_item = registry.get(target_ip)
        if isinstance(reg_item, dict) and str(reg_item.get("ipaddr") or "").strip():
            return [{
                "name": str(reg_item.get("name") or "target"),
                "ipaddr": str(reg_item.get("ipaddr") or "").strip(),
                "password": str(reg_item.get("pass") or reg_item.get("password") or ""),
            }]
    current = (cfg.get("CurrentEQ") or {}) if isinstance(cfg, dict) else {}
    ip = str(current.get("ipaddr") or "").strip()
    if not ip:
        return []
    return [{
        "name": str(current.get("name") or "current"),
        "ipaddr": ip,
        "password": str(current.get("pass") or ""),
    }]


def _recalc_summary(cases: Iterable[Dict[str, object]], finished: bool) -> Dict[str, object]:
    cases_list = list(cases)
    total = len(cases_list)
    passed = sum(1 for case in cases_list if case["status"] == "PASSED")
    failed = sum(1 for case in cases_list if case["status"] in ("FAILED", "ERROR"))
    skipped = sum(1 for case in cases_list if case["status"] == "SKIPPED")
    duration = sum(float(case.get("duration") or 0.0) for case in cases_list)
    status = "running" if not finished else ("passed" if failed == 0 else "failed")
    return {
        "status": status,
        "total": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "duration": duration,
    }


def _parse_junit_report(xml_path: str) -> tuple[List[Dict[str, object]], Dict[str, object]]:
    import xml.etree.ElementTree as ET

    cases: List[Dict[str, object]] = []
    passed = failed = skipped = errors = 0
    total_time = 0.0

    root = ET.parse(xml_path).getroot()
    for testsuite in root.findall(".//testsuite"):
        for testcase in testsuite.findall("testcase"):
            name = testcase.get("name") or ""
            classname = testcase.get("classname") or ""
            duration = float(testcase.get("time") or 0.0)
            nodeid = f"{classname}::{name}" if classname else name

            status = "PASSED"
            message = None
            failure = testcase.find("failure")
            error = testcase.find("error")
            skipped_el = testcase.find("skipped")
            if failure is not None:
                status, message = "FAILED", (failure.get("message") or "").strip()
                failed += 1
            elif error is not None:
                status, message = "ERROR", (error.get("message") or "").strip()
                errors += 1
            elif skipped_el is not None:
                status, message = "SKIPPED", (skipped_el.get("message") or "").strip()
                skipped += 1
            else:
                passed += 1

            total_time += duration
            cases.append({
                "name": name,
                "nodeid": nodeid,
                "status": status,
                "duration": duration,
                "message": message,
            })

    summary = {
        "status": ("failed" if (failed or errors) else "passed"),
        "total": len(cases),
        "passed": passed,
        "failed": failed + errors,
        "skipped": skipped,
        "duration": total_time,
    }
    return cases, summary


@lru_cache()
def get_test_service() -> TestExecutionService:
    return TestExecutionService(get_tunnel_service())


_VERBOSE_LINE = re.compile(
    r"^(?P<nodeid>[^ ]+::[^\s]+?)\s+(?P<status>PASSED|FAILED|ERROR|SKIPPED|XPASS|XFAIL)")

all = [
    "TestExecutionService",
    "get_test_service",
]
