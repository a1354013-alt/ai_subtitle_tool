import json
import logging
import os
import shutil
import time
from typing import Iterable, Optional

logger = logging.getLogger(__name__)


def _default_upload_dir() -> str:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.getenv("UPLOAD_DIR", os.path.join(base_dir, "uploads"))


def create_task_lock(business_id: str, upload_dir: Optional[str] = None) -> str:
    """
    Create a lock file for a given business_id.
    This is used by cleanup logic to avoid deleting files for in-flight tasks.
    """
    upload_dir = upload_dir or _default_upload_dir()
    os.makedirs(upload_dir, exist_ok=True)

    lock_path = os.path.join(upload_dir, f"{business_id}.lock")
    lock_info = {"business_id": business_id, "pid": os.getpid(), "timestamp": time.time()}
    with open(lock_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(lock_info, f)
    return lock_path


def remove_task_lock(business_id: str, upload_dir: Optional[str] = None) -> None:
    upload_dir = upload_dir or _default_upload_dir()
    lock_path = os.path.join(upload_dir, f"{business_id}.lock")
    if os.path.exists(lock_path):
        os.remove(lock_path)


def is_lock_stale(lock_path: str, stale_threshold_seconds: int = 3600) -> bool:
    """
    Determine whether a lock is stale.

    Rules (keep simple + predictable):
    - If lock age > threshold -> stale
    - Else, if pid is missing/dead -> stale (best-effort, optional psutil)
    - Any parse/read errors -> treat as stale (so cleanup can recover)
    """
    if not os.path.exists(lock_path):
        return False

    try:
        with open(lock_path, "r", encoding="utf-8") as f:
            lock_info = json.load(f)

        lock_age = time.time() - float(lock_info.get("timestamp", 0) or 0)
        if lock_age > stale_threshold_seconds:
            return True

        pid = lock_info.get("pid")
        if pid:
            try:
                import psutil  # optional

                if not psutil.pid_exists(int(pid)):
                    return True
            except (ImportError, ValueError, OSError):
                # If we cannot check PID, don't mark stale solely due to this.
                pass

        return False
    except (OSError, ValueError, json.JSONDecodeError):
        logger.warning("Lock file invalid; treating as stale: %s", lock_path, exc_info=True)
        return True


def _iter_upload_entries(upload_dir: str) -> Iterable[str]:
    try:
        return os.listdir(upload_dir)
    except FileNotFoundError:
        return []


def cleanup_old_files(
    upload_dir: Optional[str] = None,
    retention_seconds: int = 24 * 3600,
    stale_lock_threshold_seconds: int = 3600,
) -> None:
    """
    Delete old unlocked files/dirs under upload_dir and cleanup database records.

    - Keeps files associated with valid locks.
    - Removes stale locks (best-effort).
    - Deletes files/dirs older than retention_seconds.
    - Deletes database records older than retention_seconds.
    """
    upload_dir = upload_dir or _default_upload_dir()
    if not os.path.exists(upload_dir):
        return

    # 0) Cleanup database records
    try:
        from pathlib import Path
        from ..storage.task_history import TaskHistoryStore
        db_path = Path(upload_dir) / "task_history.sqlite3"
        if db_path.exists():
            store = TaskHistoryStore(db_path)
            count = store.cleanup_old_records(retention_seconds)
            logger.info("Cleaned up %d old task history records", count)
    except Exception as e:
        logger.warning("Failed to cleanup task history records: %s", e, exc_info=True)

    now = time.time()

    valid_locked_ids: set[str] = set()
    stale_locks: list[str] = []

    # 1) classify locks
    for filename in _iter_upload_entries(upload_dir):
        if not filename.endswith(".lock"):
            continue
        lock_path = os.path.join(upload_dir, filename)
        business_id = filename[: -len(".lock")]
        if is_lock_stale(lock_path, stale_lock_threshold_seconds):
            stale_locks.append(lock_path)
        else:
            valid_locked_ids.add(business_id)

    # 2) remove stale locks (best-effort)
    for lock_path in stale_locks:
        try:
            os.remove(lock_path)
        except OSError:
            logger.warning("Failed to remove stale lock: %s", lock_path, exc_info=True)

    # 3) cleanup old entries
    for filename in _iter_upload_entries(upload_dir):
        if filename.endswith(".lock"):
            continue

        # Skip anything associated with a valid lock (prefix match).
        locked = False
        for bid in valid_locked_ids:
            if filename.startswith(f"{bid}_") or filename.startswith(bid + "."):
                locked = True
                break
        if locked:
            continue

        file_path = os.path.join(upload_dir, filename)
        try:
            mtime = os.path.getmtime(file_path)
        except OSError:
            logger.warning("Failed to read mtime; skipping: %s", file_path, exc_info=True)
            continue

        if now - mtime <= retention_seconds:
            continue

        try:
            if os.path.isdir(file_path):
                shutil.rmtree(file_path)
            elif os.path.isfile(file_path):
                os.remove(file_path)
        except OSError:
            logger.warning("Cleanup failed for: %s", file_path, exc_info=True)

