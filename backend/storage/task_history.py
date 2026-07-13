from __future__ import annotations

import sqlite3
import time
import json
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _connect(db_path: Path) -> sqlite3.Connection:
    _ensure_parent_dir(db_path)
    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS task_history (
          task_id TEXT PRIMARY KEY,
          filename TEXT NOT NULL,
          status TEXT NOT NULL,
          progress INTEGER NOT NULL DEFAULT 0,
          message TEXT NOT NULL DEFAULT '',
          warnings TEXT NOT NULL DEFAULT '[]',
          error_code TEXT,
          suggestion TEXT,
          result_task_id TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL DEFAULT '',
          completed_at TEXT,
          duration_seconds REAL
        );
        """
    )
    existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(task_history);").fetchall()}
    migrations = {
        "progress": "ALTER TABLE task_history ADD COLUMN progress INTEGER NOT NULL DEFAULT 0;",
        "message": "ALTER TABLE task_history ADD COLUMN message TEXT NOT NULL DEFAULT '';",
        "warnings": "ALTER TABLE task_history ADD COLUMN warnings TEXT NOT NULL DEFAULT '[]';",
        "error_code": "ALTER TABLE task_history ADD COLUMN error_code TEXT;",
        "suggestion": "ALTER TABLE task_history ADD COLUMN suggestion TEXT;",
        "result_task_id": "ALTER TABLE task_history ADD COLUMN result_task_id TEXT;",
        "updated_at": "ALTER TABLE task_history ADD COLUMN updated_at TEXT NOT NULL DEFAULT '';",
        "completed_at": "ALTER TABLE task_history ADD COLUMN completed_at TEXT;",
    }
    for column, ddl in migrations.items():
        if column not in existing_columns:
            conn.execute(ddl)
    conn.execute("UPDATE task_history SET updated_at = created_at WHERE updated_at = '';")
    # Create indexes for performance
    conn.execute("CREATE INDEX IF NOT EXISTS idx_task_history_created_at ON task_history(created_at);")
    return conn


@contextmanager
def _connection(db_path: Path):
    conn = _connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@dataclass(frozen=True)
class TaskHistoryEntry:
    task_id: str
    filename: str
    status: str
    progress: int
    message: str
    warnings: list[str]
    error_code: Optional[str]
    suggestion: Optional[str]
    result_task_id: Optional[str]
    created_at: str
    updated_at: str
    completed_at: Optional[str]
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
        with _connection(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO task_history(
                  task_id, filename, status, progress, message, warnings,
                  created_at, updated_at, duration_seconds
                )
                VALUES(?, ?, ?, 0, '', '[]', ?, ?, NULL)
                ON CONFLICT(task_id) DO UPDATE SET
                  filename=excluded.filename,
                  status=excluded.status,
                  created_at=excluded.created_at,
                  updated_at=excluded.updated_at;
                """,
                (task_id, filename, status, created_at, created_at),
            )

    def update_status(
        self,
        task_id: str,
        status: str,
        duration_seconds: Optional[float] = None,
        *,
        progress: Optional[int] = None,
        message: Optional[str] = None,
        warnings: Optional[list[str]] = None,
        error_code: Optional[str] = None,
        suggestion: Optional[str] = None,
        result_task_id: Optional[str] = None,
        completed_at: Optional[str] = None,
    ) -> None:
        now = _utc_now_iso()
        terminal_completed_at = completed_at
        if terminal_completed_at is None and status in {"SUCCESS", "FAILURE", "CANCELED"}:
            terminal_completed_at = now
        warnings_json = json.dumps(warnings or [], ensure_ascii=False)
        with _connection(self._db_path) as conn:
            # Ensure the row exists (older tasks may not have been recorded).
            conn.execute(
                """
                INSERT OR IGNORE INTO task_history(
                  task_id, filename, status, progress, message, warnings,
                  created_at, updated_at, duration_seconds
                )
                VALUES(?, ?, ?, 0, '', '[]', ?, ?, NULL);
                """,
                (task_id, "", status, now, now),
            )
            conn.execute(
                """
                UPDATE task_history
                SET status = ?,
                    progress = COALESCE(?, progress),
                    message = COALESCE(?, message),
                    warnings = CASE WHEN ? THEN ? ELSE warnings END,
                    error_code = COALESCE(?, error_code),
                    suggestion = COALESCE(?, suggestion),
                    result_task_id = COALESCE(?, result_task_id),
                    updated_at = ?,
                    completed_at = COALESCE(?, completed_at),
                    duration_seconds = COALESCE(?, duration_seconds)
                WHERE task_id = ?;
                """,
                (
                    status,
                    progress,
                    message,
                    warnings is not None,
                    warnings_json,
                    error_code,
                    suggestion,
                    result_task_id,
                    now,
                    terminal_completed_at,
                    duration_seconds,
                    task_id,
                ),
            )

    def list_recent(self, limit: int = 20) -> List[TaskHistoryEntry]:
        limit = max(1, min(int(limit), 100))
        with _connection(self._db_path) as conn:
            rows = conn.execute(
                """
                SELECT task_id, filename, status, progress, message, warnings, error_code,
                       suggestion, result_task_id, created_at, updated_at, completed_at, duration_seconds
                FROM task_history
                ORDER BY created_at DESC
                LIMIT ?;
                """,
                (limit,),
            ).fetchall()
        return [self._entry_from_row(row) for row in rows]

    def get(self, task_id: str) -> Optional[TaskHistoryEntry]:
        with _connection(self._db_path) as conn:
            row = conn.execute(
                """
                SELECT task_id, filename, status, progress, message, warnings, error_code,
                       suggestion, result_task_id, created_at, updated_at, completed_at, duration_seconds
                FROM task_history
                WHERE task_id = ?;
                """,
                (task_id,),
            ).fetchone()
        return self._entry_from_row(row) if row else None

    @staticmethod
    def _entry_from_row(row) -> TaskHistoryEntry:
        values = list(row)
        try:
            values[5] = json.loads(values[5] or "[]")
            if not isinstance(values[5], list):
                values[5] = []
        except json.JSONDecodeError:
            values[5] = []
        return TaskHistoryEntry(*values)

    def get_created_at(self, task_id: str) -> Optional[str]:
        with _connection(self._db_path) as conn:
            row = conn.execute(
                "SELECT created_at FROM task_history WHERE task_id = ?;",
                (task_id,),
            ).fetchone()
        return row[0] if row else None

    def cleanup_old_records(self, retention_seconds: int) -> int:
        """Delete records older than retention_seconds."""
        cutoff_time = datetime.fromtimestamp(time.time() - retention_seconds, tz=timezone.utc).isoformat()
        with _connection(self._db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM task_history WHERE created_at < ?;",
                (cutoff_time,),
            )
            return cursor.rowcount


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
