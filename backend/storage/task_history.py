from __future__ import annotations

import sqlite3
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _connect(db_path: Path) -> sqlite3.Connection:
    _ensure_parent_dir(db_path)
    conn = sqlite3.connect(str(db_path), timeout=10, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS task_history (
          task_id TEXT PRIMARY KEY,
          filename TEXT NOT NULL,
          status TEXT NOT NULL,
          created_at TEXT NOT NULL,
          duration_seconds REAL
        );
        """
    )
    return conn


@dataclass(frozen=True)
class TaskHistoryEntry:
    task_id: str
    filename: str
    status: str
    created_at: str
    duration_seconds: Optional[float]

    def to_dict(self) -> dict:
        return asdict(self)


class TaskHistoryStore:
    def __init__(self, db_path: Path):
        self._db_path = db_path

    @property
    def db_path(self) -> Path:
        return self._db_path

    def upsert_created(self, task_id: str, filename: str, status: str = "PENDING", created_at: Optional[str] = None) -> None:
        created_at = created_at or _utc_now_iso()
        with _connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO task_history(task_id, filename, status, created_at, duration_seconds)
                VALUES(?, ?, ?, ?, NULL)
                ON CONFLICT(task_id) DO UPDATE SET
                  filename=excluded.filename,
                  status=excluded.status,
                  created_at=excluded.created_at;
                """,
                (task_id, filename, status, created_at),
            )

    def update_status(self, task_id: str, status: str, duration_seconds: Optional[float] = None) -> None:
        with _connect(self._db_path) as conn:
            # Ensure the row exists (older tasks may not have been recorded).
            conn.execute(
                """
                INSERT OR IGNORE INTO task_history(task_id, filename, status, created_at, duration_seconds)
                VALUES(?, ?, ?, ?, NULL);
                """,
                (task_id, "", status, _utc_now_iso()),
            )
            conn.execute(
                """
                UPDATE task_history
                SET status = ?, duration_seconds = COALESCE(?, duration_seconds)
                WHERE task_id = ?;
                """,
                (status, duration_seconds, task_id),
            )

    def list_recent(self, limit: int = 20) -> List[TaskHistoryEntry]:
        limit = max(1, min(int(limit), 100))
        with _connect(self._db_path) as conn:
            rows = conn.execute(
                """
                SELECT task_id, filename, status, created_at, duration_seconds
                FROM task_history
                ORDER BY created_at DESC
                LIMIT ?;
                """,
                (limit,),
            ).fetchall()
        return [TaskHistoryEntry(*row) for row in rows]

    def get_created_at(self, task_id: str) -> Optional[str]:
        with _connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT created_at FROM task_history WHERE task_id = ?;",
                (task_id,),
            ).fetchone()
        return row[0] if row else None


def duration_seconds_since(created_at_iso: Optional[str]) -> Optional[float]:
    if not created_at_iso:
        return None
    try:
        created = datetime.fromisoformat(created_at_iso)
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return max(0.0, time.time() - created.timestamp())
    except Exception:
        return None

