from __future__ import annotations

import importlib
import logging
import sys
from types import ModuleType, SimpleNamespace

import pytest


def _reload_main(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("TESTING", "true")

    import backend.main as main

    return importlib.reload(main)


def test_demo_duration_below_limit_passes(monkeypatch: pytest.MonkeyPatch, tmp_path):
    main = _reload_main(monkeypatch, tmp_path)
    monkeypatch.setattr(main.settings, "DEMO_MODE", True)
    monkeypatch.setattr(main.settings, "MAX_VIDEO_DURATION_MINUTES", 10)

    calls = [
        SimpleNamespace(returncode=0, stdout="video\n", stderr=""),
        SimpleNamespace(returncode=0, stdout="599", stderr=""),
    ]
    monkeypatch.setattr(main.subprocess, "run", lambda *a, **k: calls.pop(0))

    main._validate_saved_video_file(str(tmp_path / "video.mp4"))


def test_demo_duration_equal_limit_passes(monkeypatch: pytest.MonkeyPatch, tmp_path):
    main = _reload_main(monkeypatch, tmp_path)
    monkeypatch.setattr(main.settings, "DEMO_MODE", True)
    monkeypatch.setattr(main.settings, "MAX_VIDEO_DURATION_MINUTES", 10)

    calls = [
        SimpleNamespace(returncode=0, stdout="video\n", stderr=""),
        SimpleNamespace(returncode=0, stdout="600", stderr=""),
    ]
    monkeypatch.setattr(main.subprocess, "run", lambda *a, **k: calls.pop(0))

    main._validate_saved_video_file(str(tmp_path / "video.mp4"))


def test_demo_duration_over_limit_raises(monkeypatch: pytest.MonkeyPatch, tmp_path):
    main = _reload_main(monkeypatch, tmp_path)
    monkeypatch.setattr(main.settings, "DEMO_MODE", True)
    monkeypatch.setattr(main.settings, "MAX_VIDEO_DURATION_MINUTES", 10)

    calls = [
        SimpleNamespace(returncode=0, stdout="video\n", stderr=""),
        SimpleNamespace(returncode=0, stdout="601", stderr=""),
    ]
    monkeypatch.setattr(main.subprocess, "run", lambda *a, **k: calls.pop(0))

    with pytest.raises(ValueError, match="exceeds demo limit"):
        main._validate_saved_video_file(str(tmp_path / "video.mp4"))


def test_demo_duration_parse_failure_warns_without_blocking(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    caplog: pytest.LogCaptureFixture,
):
    main = _reload_main(monkeypatch, tmp_path)
    monkeypatch.setattr(main.settings, "DEMO_MODE", True)
    monkeypatch.setattr(main.settings, "MAX_VIDEO_DURATION_MINUTES", 10)

    calls = [
        SimpleNamespace(returncode=0, stdout="video\n", stderr=""),
        SimpleNamespace(returncode=0, stdout="not-a-number", stderr=""),
    ]
    monkeypatch.setattr(main.subprocess, "run", lambda *a, **k: calls.pop(0))

    with caplog.at_level(logging.WARNING):
        main._validate_saved_video_file(str(tmp_path / "video.mp4"))

    assert "Could not parse video duration" in caplog.text


def test_model_size_priority_options_then_env_then_duration(monkeypatch: pytest.MonkeyPatch):
    from backend import settings
    from backend.utils.model_loader import resolve_model_size

    monkeypatch.setattr(settings, "WHISPER_MODEL", "small")
    assert resolve_model_size(3600, requested_model_size="tiny") == "tiny"
    assert resolve_model_size(3600) == "small"

    monkeypatch.setattr(settings, "WHISPER_MODEL", "")
    assert resolve_model_size(30) == "base"
    assert resolve_model_size(300) == "small"
    assert resolve_model_size(1200) == "medium"


def test_local_storage_backend_selected_even_when_s3_bucket_exists(monkeypatch: pytest.MonkeyPatch):
    from backend.utils import storage_utils

    monkeypatch.setattr(storage_utils.settings, "STORAGE_BACKEND", "local")
    monkeypatch.setenv("S3_BUCKET", "configured-but-disabled")

    assert isinstance(storage_utils.get_storage_backend(), storage_utils.LocalStorageBackend)


def test_s3_storage_backend_selected_when_configured(monkeypatch: pytest.MonkeyPatch):
    from backend.utils import storage_utils

    class FakeConfig:
        def __init__(self, **_kwargs):
            pass

    fake_boto3 = ModuleType("boto3")
    fake_boto3.client = lambda *a, **k: SimpleNamespace()
    fake_botocore = ModuleType("botocore")
    fake_config_mod = ModuleType("botocore.config")
    fake_config_mod.Config = FakeConfig

    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    monkeypatch.setitem(sys.modules, "botocore", fake_botocore)
    monkeypatch.setitem(sys.modules, "botocore.config", fake_config_mod)
    monkeypatch.setattr(storage_utils.settings, "STORAGE_BACKEND", "s3")
    monkeypatch.setenv("S3_BUCKET", "bucket")

    assert isinstance(storage_utils.get_storage_backend(), storage_utils.S3StorageBackend)


def test_s3_storage_backend_requires_bucket(monkeypatch: pytest.MonkeyPatch):
    from backend.utils import storage_utils

    monkeypatch.setattr(storage_utils.settings, "STORAGE_BACKEND", "s3")
    monkeypatch.delenv("S3_BUCKET", raising=False)

    with pytest.raises(ValueError, match="S3_BUCKET"):
        storage_utils.get_storage_backend()


def test_invalid_storage_backend_raises(monkeypatch: pytest.MonkeyPatch):
    from backend.utils import storage_utils

    monkeypatch.setattr(storage_utils.settings, "STORAGE_BACKEND", "xxx")

    with pytest.raises(ValueError, match="Invalid STORAGE_BACKEND"):
        storage_utils.get_storage_backend()


def test_local_download_copies_file_and_creates_parent(tmp_path):
    from backend.utils.storage_utils import LocalStorageBackend

    source = tmp_path / "source.txt"
    destination = tmp_path / "nested" / "out.txt"
    source.write_text("hello", encoding="utf-8")

    assert LocalStorageBackend().download_file(str(source), str(destination)) is True
    assert destination.read_text(encoding="utf-8") == "hello"


def test_local_download_missing_source_returns_false(tmp_path):
    from backend.utils.storage_utils import LocalStorageBackend

    destination = tmp_path / "out.txt"

    assert LocalStorageBackend().download_file(str(tmp_path / "missing.txt"), str(destination)) is False
    assert not destination.exists()


def test_task_history_store_closes_connections(tmp_path):
    from backend.storage.task_history import TaskHistoryStore

    store = TaskHistoryStore(tmp_path / "history.sqlite3")
    store.upsert_created("task-1", "demo.mp4")
    store.update_status("task-1", "SUCCESS", duration_seconds=1.5)

    rows = store.list_recent()
    assert rows[0].task_id == "task-1"
    assert rows[0].status == "SUCCESS"
    assert store.get_created_at("task-1") is not None
    assert store.cleanup_old_records(retention_seconds=0) >= 0


@pytest.mark.anyio
async def test_readyz_does_not_require_openai_key(monkeypatch: pytest.MonkeyPatch, tmp_path):
    main = _reload_main(monkeypatch, tmp_path)
    monkeypatch.setattr(main.settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(main.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0))

    class FakeRedisClient:
        def ping(self):
            return True

    class FakeRedis:
        @staticmethod
        def from_url(*_args, **_kwargs):
            return FakeRedisClient()

    fake_redis_mod = ModuleType("redis")
    fake_redis_mod.Redis = FakeRedis
    monkeypatch.setitem(sys.modules, "redis", fake_redis_mod)

    response = await main.readyz()
    assert response == {"status": "ok"}
