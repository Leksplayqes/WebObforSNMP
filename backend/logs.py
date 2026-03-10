"""Simple in-memory logging used by the API for UI feedback."""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List

api_logs: List[Dict[str, str]] = []


def add_log(message: str, level: str = "INFO") -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    api_logs.append({"timestamp": ts, "level": level, "message": message})
    if len(api_logs) > 4000:
        del api_logs[:2000]


__all__ = ["add_log", "api_logs"]
