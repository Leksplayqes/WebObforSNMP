"""Miscellaneous small endpoints shared across the app."""
from __future__ import annotations

import subprocess
from typing import Any, Dict

from fastapi import APIRouter

from .api_errors import ApiException
from .config import CONFIG_FILE
from .logs import add_log

router = APIRouter(tags=["common"])


@router.get("/health")
async def health() -> Dict[str, Any]:
    return {"status": "success", "data": {"ok": True, "config_path": str(CONFIG_FILE)}}


@router.get("/")
async def root() -> Dict[str, Any]:
    return {"status": "success", "data": {"message": "OSM-K Tester API", "version": "5.0.0"}}


@router.post("/ping")
async def ping(req: Dict[str, Any]):
    ip = req.get("ip_address", "")
    add_log(f"Ping {ip}")
    try:
        cmd = ["ping", "-n", "2", ip]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True)
        except Exception:
            res = subprocess.run(["ping", "-c", "2", ip], capture_output=True, text=True)
        return {
            "status": "success",
            "data": {
                "success": res.returncode == 0,
                "output": res.stdout,
                "error": res.stderr,
            },
        }
    except Exception as exc:
        add_log(f"Ping error: {exc}", "ERROR")
        raise ApiException(str(exc), code="PING_ERROR", status_code=500)


__all__ = ["router"]
