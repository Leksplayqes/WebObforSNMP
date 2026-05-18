import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Iterable, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent
TRAP_DIR = BASE_DIR
TEXT_LOG = TRAP_DIR / "received_traps.log"
JSONL_LOG = TRAP_DIR / "received_traps.jsonl"

_CURSOR_LOCK = Lock()
_CURSOR_TS: Optional[datetime] = None


def _parse_ts(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        return None


def _now_cursor() -> datetime:
    # Listener writes naive local ISO timestamps, so keep the cursor naive too.
    return datetime.now()


def _get_cursor() -> Optional[datetime]:
    with _CURSOR_LOCK:
        return _CURSOR_TS


def _set_cursor(value: Optional[datetime]) -> None:
    global _CURSOR_TS
    with _CURSOR_LOCK:
        _CURSOR_TS = value


def _iter_trap_records(path: Path = JSONL_LOG) -> Iterable[Dict[str, Any]]:
    if not path.exists():
        return

    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                # The listener may be appending the current line while the test is reading.
                # Ignore incomplete/corrupt tail lines and retry on the next poll.
                continue
            if isinstance(obj, dict):
                yield obj


def _record_is_after_cursor(record: Dict[str, Any], since: Optional[datetime]) -> bool:
    if since is None:
        return True
    record_ts = _parse_ts(record.get("ts"))
    if record_ts is None:
        return False
    return record_ts >= since


def parse_snmp_log(target_oid, target_value, *, since: Optional[datetime] = None):
    """Find a matching trap without mutating the shared trap log.

    The trap listener appends events to received_traps.jsonl. Older tests called
    clear_trap_log() before each check; truncating a shared file breaks parallel
    pytest jobs. clear_trap_log() now records a per-process cursor timestamp, and
    this function only scans records written after that cursor.
    """
    effective_since = since if since is not None else _get_cursor()

    for trap_data in _iter_trap_records():
        if not _record_is_after_cursor(trap_data, effective_since):
            continue

        var_binds = trap_data.get("var_binds", [])
        if not isinstance(var_binds, list):
            continue

        for bind in var_binds:
            if not isinstance(bind, dict):
                continue
            if bind.get("oid") == target_oid and str(bind.get("value")) == str(target_value):
                return (bind.get("oid"), str(bind.get("value")))
    return False


def clear_trap_log():
    """Start a new logical trap-check window for the current pytest process.

    Do not truncate received_traps.log/received_traps.jsonl here: those files are
    shared by all running tests and by the backend trap UI. Truncating them makes
    parallel tests erase each other's trap events.
    """
    TRAP_DIR.mkdir(parents=True, exist_ok=True)
    _set_cursor(_now_cursor())
    os.environ["TRAP_LOG_CURSOR_TS"] = _get_cursor().isoformat(timespec="microseconds")


def wait_trap(oid: str, code: int, timeout_s: float = 3.0, poll_s: float = 0.5):
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        last = parse_snmp_log(oid, code)
        if last != False:
            return last
        time.sleep(poll_s)
    return last
