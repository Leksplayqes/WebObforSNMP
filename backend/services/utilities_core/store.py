"""Result storage: in-memory + JSON history files."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from ...result_repository import ResultRecord, ResultRepository


class ResultStore:
    def __init__(self, *, repo: ResultRepository, history_dir: Path) -> None:
        self.repo = repo
        self.history_dir = history_dir
        self.history_dir.mkdir(parents=True, exist_ok=True)

    def create(self, *, record_id: str, type: str, status: str, payload: Dict[str, Any], started_at: float) -> None:
        self.repo.create(record_id=record_id, type=type, status=status, payload=payload, started_at=started_at)

    def update(
            self,
            record_id: str,
            *,
            status: Optional[str] = None,
            payload: Optional[Dict[str, Any]] = None,
            finished_at: Optional[float] = None,
    ) -> ResultRecord:
        return self.repo.update(record_id, status=status, payload=payload, finished_at=finished_at)

    def get(self, record_id: str) -> Optional[ResultRecord]:
        return self.repo.get(record_id)

    def list(self):
        return self.repo.list()

    def dump_final(self, record: ResultRecord) -> None:
        try:
            data = record.to_dict()
            util_type = data.get("type", "utility")
            filename = f"{record.id}_{util_type}.json"
            path = self.history_dir / filename
            with path.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            # Intentionally swallow to avoid breaking job finalization
            pass

    def json_path(self, record_id: str) -> Optional[Path]:
        record = self.get(record_id)
        if not record:
            return None
        util_type = record.type or "utility"
        path = self.history_dir / f"{record.id}_{util_type}.json"
        return path if path.exists() else None

    def load_from_disk(self, *, limit: Optional[int] = None) -> int:
        if not self.history_dir.exists():
            return 0

        files = sorted(self.history_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if limit is None:
            limit = self.repo.limit

        loaded = 0
        for p in files[:limit]:
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue

            record_id = data.get("id")
            rtype = data.get("type") or "utilities"
            status = data.get("status") or "completed"
            payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}

            created_at = data.get("created_at")
            started_at = data.get("started_at")
            finished_at = data.get("finished_at")

            if not record_id:
                continue
            self.create(
                record_id=record_id,
                type=rtype,
                status=status,
                payload=payload,
                started_at=started_at,
            )
            extra = {}
            if extra:
                self.update(record_id, status=status, payload=payload, **extra)

            loaded += 1

        return loaded
