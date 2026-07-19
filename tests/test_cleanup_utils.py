from __future__ import annotations

import json
import os
import sys
import time
from types import ModuleType

import pytest


def test_fresh_lock_without_pid_is_preserved(monkeypatch: pytest.MonkeyPatch, tmp_path):
    from backend.utils.cleanup_utils import cleanup_old_files

    upload_dir = tmp_path / "uploads"
    output_dir = tmp_path / "outputs"
    temp_dir = tmp_path / "tmp"
    for path in (upload_dir, output_dir, temp_dir):
        path.mkdir()

    lock_path = upload_dir / "task-1.lock"
    artifact_path = upload_dir / "task-1_final.mp4"
    now = 1_000.0
    lock_path.write_text(json.dumps({"business_id": "task-1", "timestamp": now}), encoding="utf-8")
    artifact_path.write_bytes(b"video")
    old_mtime = now - 7_200
    os.utime(lock_path, (now, now))
    os.utime(artifact_path, (old_mtime, old_mtime))
    monkeypatch.setattr("backend.utils.cleanup_utils.time.time", lambda: now)

    counts = cleanup_old_files(
        upload_dir=str(upload_dir),
        output_dir=str(output_dir),
        temp_dir=str(temp_dir),
        retention_seconds=3_600,
    )

    assert lock_path.exists() is True
    assert artifact_path.exists() is True
    assert counts["preserved_locked"] >= 1


def test_stale_timestamp_lock_is_removed(monkeypatch: pytest.MonkeyPatch, tmp_path):
    from backend.utils.cleanup_utils import is_lock_stale

    lock_path = tmp_path / "stale.lock"
    lock_path.write_text(json.dumps({"business_id": "task-1", "timestamp": 1.0}), encoding="utf-8")
    monkeypatch.setattr("backend.utils.cleanup_utils.time.time", lambda: 10_000.0)

    assert is_lock_stale(str(lock_path), stale_threshold_seconds=60) is True


def test_dead_local_pid_lock_is_removed_when_pid_check_is_reliable(monkeypatch: pytest.MonkeyPatch, tmp_path):
    from backend.utils.cleanup_utils import is_lock_stale

    lock_path = tmp_path / "dead.lock"
    lock_path.write_text(json.dumps({"business_id": "task-1", "pid": 424242, "timestamp": time.time()}), encoding="utf-8")

    fake_psutil = ModuleType("psutil")
    fake_psutil.pid_exists = lambda pid: False
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil)

    assert is_lock_stale(str(lock_path), stale_threshold_seconds=3_600) is True


def test_active_production_task_artifacts_are_preserved(monkeypatch: pytest.MonkeyPatch, tmp_path):
    from backend.utils.cleanup_utils import cleanup_old_files

    upload_dir = tmp_path / "uploads"
    output_dir = tmp_path / "outputs"
    temp_dir = tmp_path / "tmp"
    for path in (upload_dir, output_dir, temp_dir):
        path.mkdir()

    business_id = "prod-task"
    now = 10_000.0
    lock_path = upload_dir / f"{business_id}.lock"
    artifact_path = upload_dir / f"{business_id}_final.mp4"
    lock_path.write_text(json.dumps({"business_id": business_id, "timestamp": now, "pid": 1234}), encoding="utf-8")
    artifact_path.write_bytes(b"video")
    old_mtime = now - 7_200
    os.utime(lock_path, (now, now))
    os.utime(artifact_path, (old_mtime, old_mtime))
    monkeypatch.setattr("backend.utils.cleanup_utils.time.time", lambda: now)

    fake_psutil = ModuleType("psutil")
    fake_psutil.pid_exists = lambda pid: True
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil)

    counts = cleanup_old_files(
        upload_dir=str(upload_dir),
        output_dir=str(output_dir),
        temp_dir=str(temp_dir),
        retention_seconds=3_600,
    )

    assert lock_path.exists() is True
    assert artifact_path.exists() is True
    assert counts["preserved_locked"] >= 1
