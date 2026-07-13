import json
import logging
import os
import shutil
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, Optional

from .. import settings

logger = logging.getLogger(__name__)
METADATA_ENTRY_NAMES = {
    "task_history.sqlite3",
    "task_history.sqlite3-wal",
    "task_history.sqlite3-shm",
    "batches",
}


@dataclass
class CleanupCounts:
    files_removed: int = 0
    dirs_removed: int = 0
    stale_locks_removed: int = 0
    batch_metadata_removed: int = 0
    task_history_records_removed: int = 0
    preserved_locked: int = 0
    errors: int = 0
    dry_run: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _default_upload_dir() -> str:
    return settings.get_upload_dir()


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
    output_dir: Optional[str] = None,
    temp_dir: Optional[str] = None,
    retention_seconds: Optional[int] = None,
    stale_lock_threshold_seconds: int = 3600,
    dry_run: bool = False,
) -> dict:
    """
    Delete old unlocked files/dirs under upload_dir and cleanup database records.

    - Keeps files associated with valid locks.
    - Removes stale locks (best-effort).
    - Deletes files/dirs older than retention_seconds.
    - Deletes database records older than retention_seconds.
    """
    upload_dir = upload_dir or _default_upload_dir()
    output_dir = output_dir or settings.get_output_dir()
    temp_dir = temp_dir or settings.get_temp_dir()
    if retention_seconds is None:
        retention_seconds = settings.TASK_CLEANUP_DAYS * 24 * 3600
    counts = CleanupCounts(dry_run=dry_run)
    if not os.path.exists(upload_dir):
        return counts.to_dict()

    # 0) Cleanup database records
    try:
        from ..storage.task_history import TaskHistoryStore
        db_path = Path(upload_dir) / "task_history.sqlite3"
        if db_path.exists():
            store = TaskHistoryStore(db_path)
            count = 0 if dry_run else store.cleanup_old_records(retention_seconds)
            counts.task_history_records_removed = count
            logger.info("Cleaned up %d old task history records", count)
    except Exception as e:
        counts.errors += 1
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
            if not dry_run:
                os.remove(lock_path)
            counts.stale_locks_removed += 1
        except OSError:
            counts.errors += 1
            logger.warning("Failed to remove stale lock: %s", lock_path, exc_info=True)

    def _remove_path(path: str, *, batch_metadata: bool = False) -> None:
        try:
            if not dry_run:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                elif os.path.isfile(path):
                    os.remove(path)
            if batch_metadata:
                counts.batch_metadata_removed += 1
            elif os.path.isdir(path):
                counts.dirs_removed += 1
            else:
                counts.files_removed += 1
        except OSError:
            counts.errors += 1
            logger.warning("Cleanup failed for: %s", path, exc_info=True)

    def _cleanup_dir(root_dir: str, *, preserve_metadata: bool = False, batch_metadata: bool = False) -> None:
        if not os.path.exists(root_dir):
            return
        for filename in _iter_upload_entries(root_dir):
            if preserve_metadata and filename in METADATA_ENTRY_NAMES:
                continue
            if filename.endswith(".lock"):
                continue

            locked = False
            for bid in valid_locked_ids:
                if filename.startswith(f"{bid}_") or filename.startswith(bid + "."):
                    locked = True
                    break
            if locked:
                counts.preserved_locked += 1
                continue

            file_path = os.path.join(root_dir, filename)
            try:
                mtime = os.path.getmtime(file_path)
            except OSError:
                counts.errors += 1
                logger.warning("Failed to read mtime; skipping: %s", file_path, exc_info=True)
                continue

            if now - mtime <= retention_seconds:
                continue

            _remove_path(file_path, batch_metadata=batch_metadata)

    # 3) cleanup old entries
    _cleanup_dir(upload_dir, preserve_metadata=True)
    _cleanup_dir(output_dir)
    _cleanup_dir(temp_dir)

    batches_dir = os.path.join(upload_dir, "batches")
    if os.path.exists(batches_dir):
        for filename in _iter_upload_entries(batches_dir):
            if not filename.endswith(".json"):
                continue
            file_path = os.path.join(batches_dir, filename)
            try:
                mtime = os.path.getmtime(file_path)
            except OSError:
                counts.errors += 1
                continue
            if now - mtime > retention_seconds:
                _remove_path(file_path, batch_metadata=True)

    return counts.to_dict()

