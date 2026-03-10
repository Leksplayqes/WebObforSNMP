from __future__ import annotations
import json
from pathlib import Path
from collections import deque
from datetime import datetime
from fastapi import APIRouter, Query
from typing import Any, Dict, List, Optional
from ..traps.manager import start_trap_listener, stop_trap_listener, trap_listener_status

router = APIRouter(prefix="/traps", tags=["traps"])

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRAP_LOG = PROJECT_ROOT / "TRAP_analyze" / "received_traps.log"
TRAP_JSONL = PROJECT_ROOT / "TRAP_analyze" / "received_traps.jsonl"


def _tail_lines(path: Path, limit: int) -> List[str]:
    if limit <= 0 or not path.exists():
        return []
    dq: deque[str] = deque(maxlen=limit)
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            if line:
                dq.append(line)
    return list(dq)


def _parse_dt(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(ts)
    except Exception:
        return None


@router.post("/start")
def start():
    return {"status": "success", "data": start_trap_listener()}


@router.post("/stop")
def stop():
    return {"status": "success", "data": stop_trap_listener()}


@router.get("/status")
def status():
    return {"status": "success", "data": trap_listener_status()}


@router.get("/events")
def event(
    limit: int = Query(200, ge=1, le=5000),
    order: str = Query("desc", pattern="^(asc|desc)$"),
):
    if not TRAP_JSONL.exists():
        return {"status": "success", "data": {"items": []}}

    items = []

    with TRAP_JSONL.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                obj = json.loads(line)
            except Exception:
                continue

            if not isinstance(obj, dict):
                continue

            processed_lines = obj.get("processed_lines")
            var_binds = obj.get("var_binds")

            items.append({
                "ts": obj.get("ts"),
                "src_ip": obj.get("src_ip"),
                "snmp_trap_oid": obj.get("snmp_trap_oid"),
                "processed_lines": processed_lines if isinstance(processed_lines, list) else [],
                "var_binds": var_binds if isinstance(var_binds, list) else [],
            })

    def key(it):
        try:
            return datetime.fromisoformat(str(it.get("ts") or ""))
        except Exception:
            return datetime.min

    items.sort(key=key, reverse=(order == "desc"))
    items = items[:limit]

    return {"status": "success", "data": {"items": items}}
