"""In-memory repositories for storing execution results with eviction support."""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional


@dataclass
class ResultRecord:
    """Envelope describing execution results for tests and utilities."""

    id: str
    type: str
    status: str
    created_at: float = field(default_factory=lambda: time.time())
    updated_at: float = field(default_factory=lambda: time.time())
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "payload": self.payload,
            "summary": self.summary,
        }


class ResultRepository:
    """Thread-safe repository with FIFO eviction when a limit is reached."""

    def __init__(self, limit: int):
        self._limit = limit
        self._items: "OrderedDict[str, ResultRecord]" = OrderedDict()
        self._lock = threading.Lock()

    def _evict_if_needed(self) -> None:
        while len(self._items) > self._limit:
            self._items.popitem(last=False)

    @staticmethod
    def _extract_summary(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        summary = payload.get("summary")
        return summary if isinstance(summary, dict) else {}

    # ---------- чтение ----------

    def list(self) -> List[ResultRecord]:
        with self._lock:
            return list(reversed(list(self._items.values())))

    def get(self, record_id: str) -> Optional[ResultRecord]:
        with self._lock:
            return self._items.get(record_id)

    def values(self) -> Iterable[ResultRecord]:
        with self._lock:
            return tuple(self._items.values())

    @property
    def limit(self) -> int:
        return self._limit

    def count(self) -> int:
        with self._lock:
            return len(self._items)

    # ---------- запись ----------

    def create(
        self,
        *,
        record_id: str,
        type: str,
        status: str,
        payload: Optional[Dict[str, Any]] = None,
        started_at: Optional[float] = None,
        finished_at: Optional[float] = None,
        created_at: Optional[float] = None,
        updated_at: Optional[float] = None,
    ) -> ResultRecord:
        payload = payload or {}
        created = created_at or time.time()
        record = ResultRecord(
            id=record_id,
            type=type,
            status=status,
            created_at=created,
            updated_at=updated_at or created,
            started_at=started_at,
            finished_at=finished_at,
            payload=payload,
            summary=self._extract_summary(payload),
        )
        with self._lock:
            if record_id in self._items:
                self._items.pop(record_id)
            self._items[record_id] = record
            self._evict_if_needed()
        return record

    def update(
        self,
        record_id: str,
        *,
        status: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        started_at: Optional[float] = None,
        finished_at: Optional[float] = None,
        updated_at: Optional[float] = None,
    ) -> ResultRecord:
        with self._lock:
            record = self._items.get(record_id)
            if not record:
                raise KeyError(record_id)
            if status is not None:
                record.status = status
            if payload is not None:
                record.payload = payload
                record.summary = self._extract_summary(payload)
            if started_at is not None:
                record.started_at = started_at
            if finished_at is not None:
                record.finished_at = finished_at
            record.updated_at = updated_at or time.time()
            self._items.move_to_end(record_id)
            self._evict_if_needed()
            return record

    def upsert(self, record: ResultRecord) -> ResultRecord:
        """Добавить или заменить запись, как при загрузке из файлов."""
        with self._lock:
            if record.id in self._items:
                self._items.pop(record.id)
            self._items[record.id] = record
            self._evict_if_needed()
            return record

    def delete(self, record_id: str) -> bool:
        with self._lock:
            try:
                self._items.pop(record_id)
            except KeyError:
                return False
            return True


all = [
    "ResultRecord",
    "ResultRepository",
]