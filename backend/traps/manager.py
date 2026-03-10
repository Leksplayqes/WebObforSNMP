from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from threading import Lock

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = PROJECT_ROOT / "TRAP_analyze" / "trap_listener_entrypoint.py"

_lock = Lock()
_proc: subprocess.Popen | None = None


def start_trap_listener() -> dict:
    global _proc
    with _lock:
        if _proc and _proc.poll() is None:
            return {"started": False, "reason": "already_running", "pid": _proc.pid}

        _proc = subprocess.Popen(
            [sys.executable, str(ENTRYPOINT)],
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return {"started": True, "pid": _proc.pid}


def stop_trap_listener() -> dict:
    global _proc
    with _lock:
        if not _proc or _proc.poll() is not None:
            return {"stopped": False, "reason": "not_running"}

        _proc.terminate()
        try:
            _proc.wait(timeout=5)
        except Exception:
            _proc.kill()

        pid = _proc.pid
        _proc = None
        return {"stopped": True, "pid": pid}


def trap_listener_status() -> dict:
    with _lock:
        running = _proc is not None and _proc.poll() is None
        return {"running": running, "pid": (_proc.pid if running else None)}
