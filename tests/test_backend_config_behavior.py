from __future__ import annotations

import importlib
import logging
import os
import sys
from pathlib import Path
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
        SimpleNamespace(returncode=0, stdout="audio\n", stderr=""),
        SimpleNamespace(returncode=0, stdout="599", stderr=""),
    ]
    monkeypatch.setattr(main, "run_media_command", lambda *a, **k: calls.pop(0))

    main._validate_saved_video_file(str(tmp_path / "video.mp4"))


def test_demo_duration_equal_limit_passes(monkeypatch: pytest.MonkeyPatch, tmp_path):
    main = _reload_main(monkeypatch, tmp_path)
    monkeypatch.setattr(main.settings, "DEMO_MODE", True)
    monkeypatch.setattr(main.settings, "MAX_VIDEO_DURATION_MINUTES", 10)

    calls = [
        SimpleNamespace(returncode=0, stdout="video\n", stderr=""),
        SimpleNamespace(returncode=0, stdout="audio\n", stderr=""),
        SimpleNamespace(returncode=0, stdout="600", stderr=""),
    ]
    monkeypatch.setattr(main, "run_media_command", lambda *a, **k: calls.pop(0))

    main._validate_saved_video_file(str(tmp_path / "video.mp4"))


def test_demo_duration_over_limit_raises(monkeypatch: pytest.MonkeyPatch, tmp_path):
    main = _reload_main(monkeypatch, tmp_path)
    monkeypatch.setattr(main.settings, "DEMO_MODE", True)
    monkeypatch.setattr(main.settings, "MAX_VIDEO_DURATION_MINUTES", 10)

    calls = [
        SimpleNamespace(returncode=0, stdout="video\n", stderr=""),
        SimpleNamespace(returncode=0, stdout="audio\n", stderr=""),
        SimpleNamespace(returncode=0, stdout="601", stderr=""),
    ]
    monkeypatch.setattr(main, "run_media_command", lambda *a, **k: calls.pop(0))

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
        SimpleNamespace(returncode=0, stdout="audio\n", stderr=""),
        SimpleNamespace(returncode=0, stdout="not-a-number", stderr=""),
    ]
    monkeypatch.setattr(main, "run_media_command", lambda *a, **k: calls.pop(0))

    with caplog.at_level(logging.WARNING):
        main._validate_saved_video_file(str(tmp_path / "video.mp4"))

    assert "Could not parse video duration" in caplog.text


def test_upload_validation_rejects_video_without_audio(monkeypatch: pytest.MonkeyPatch, tmp_path):
    main = _reload_main(monkeypatch, tmp_path)
    monkeypatch.setattr(main.settings, "DEMO_MODE", False)
    calls = [
        SimpleNamespace(returncode=0, stdout="video\n", stderr=""),
        SimpleNamespace(returncode=0, stdout="", stderr=""),
    ]
    monkeypatch.setattr(main, "run_media_command", lambda *a, **k: calls.pop(0))

    with pytest.raises(ValueError, match="audio stream"):
        main._validate_saved_video_file(str(tmp_path / "video.mp4"))


def test_import_model_loader_does_not_require_heavy_modules(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setitem(sys.modules, "torch", None)
    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    module = importlib.reload(importlib.import_module("backend.utils.model_loader"))
    assert module.resolve_model_size(30, requested_model_size="tiny") == "tiny"


def test_import_translate_policy_does_not_require_openai_or_tenacity(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setitem(sys.modules, "openai", None)
    monkeypatch.setitem(sys.modules, "tenacity", None)
    module = importlib.reload(importlib.import_module("backend.utils.translate_policy"))
    assert module.translation_targets_requested(["Original"]) is False
    assert module.translation_targets_requested(["Japanese"]) is True


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


def test_task_history_pending_upsert_does_not_reset_terminal_state(tmp_path):
    from backend.storage.task_history import TaskHistoryStore

    store = TaskHistoryStore(tmp_path / "history.sqlite3")
    store.upsert_created("task-1", "demo.mp4")
    store.update_status("task-1", "SUCCESS", duration_seconds=1.5, progress=100, message="Completed")
    store.upsert_created("task-1", "demo.mp4", status="PENDING")

    entry = store.get("task-1")
    assert entry is not None
    assert entry.status == "SUCCESS"
    assert entry.progress == 100


def test_task_history_success_clears_stale_failure_metadata(tmp_path):
    from backend.storage.task_history import TaskHistoryStore

    store = TaskHistoryStore(tmp_path / "history.sqlite3")
    store.upsert_created("task-1", "demo.mp4")
    store.update_status("task-1", "FAILURE", error_code="old_error", suggestion="old suggestion")
    store.update_status("task-1", "SUCCESS", duration_seconds=1.0, progress=100, message="Completed")

    entry = store.get("task-1")
    assert entry is not None
    assert entry.status == "SUCCESS"
    assert entry.error_code is None
    assert entry.suggestion is None


def test_expected_segment_count_boundaries(monkeypatch: pytest.MonkeyPatch):
    from backend.utils.split_utils import expected_segment_count

    assert expected_segment_count(30, segment_length=30, overlap=2) == 1
    assert expected_segment_count(58, segment_length=30, overlap=2) == 2
    assert expected_segment_count(59, segment_length=30, overlap=2) == 2
    assert expected_segment_count(60, segment_length=30, overlap=2) == 2
    assert expected_segment_count(64, segment_length=30, overlap=2) == 3


def test_cjk_font_check_requires_exact_family(monkeypatch: pytest.MonkeyPatch):
    import subprocess
    from types import SimpleNamespace
    import backend.main as main

    monkeypatch.setattr(main.settings, "SUBTITLE_FONT_NAME", "Definitely Missing Font")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout="DejaVu Sans\n/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf\n",
            stderr="",
        ),
    )

    status = main._check_subtitle_font()

    assert status["requested_family"] == "Definitely Missing Font"
    assert status["resolved_family"] == "DejaVu Sans"
    assert status["exact_match"] is False
    assert status["available"] is False


def test_cjk_font_check_accepts_exact_family(monkeypatch: pytest.MonkeyPatch):
    import subprocess
    from types import SimpleNamespace
    import backend.main as main

    monkeypatch.setattr(main.settings, "SUBTITLE_FONT_NAME", "Noto Sans CJK TC")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout="Noto Sans CJK TC,Noto Sans CJK JP\n/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc\n",
            stderr="",
        ),
    )

    status = main._check_subtitle_font()

    assert status["resolved_family"].startswith("Noto Sans CJK TC")
    assert status["exact_match"] is True
    assert status["available"] is True


def test_parallel_failure_persists_terminal_state_and_cleans_lock_and_segments(monkeypatch: pytest.MonkeyPatch, tmp_path):
    import backend.tasks as tasks
    from backend.utils.cleanup_utils import create_task_lock

    upload_dir = tmp_path / "uploads"
    segments_dir = tmp_path / "segments"
    upload_dir.mkdir()
    segments_dir.mkdir()
    (segments_dir / "seg_000.mp4").write_bytes(b"partial")
    monkeypatch.setenv("UPLOAD_DIR", str(upload_dir))
    lock_path = Path(create_task_lock("task-1", str(upload_dir)))
    tasks._task_history().upsert_created("task-1", "demo.mp4")

    tasks._persist_parallel_failure("task-1", RuntimeError("segment failed"), str(segments_dir))

    entry = tasks._task_history().get("task-1")
    assert entry is not None
    assert entry.status == "FAILURE"
    assert entry.duration_seconds is not None
    assert (upload_dir / "task-1_error.json").exists()
    assert not lock_path.exists()
    assert not segments_dir.exists()


def test_cleanup_honors_retention_and_structured_counts(monkeypatch: pytest.MonkeyPatch, tmp_path):
    from backend.utils.cleanup_utils import cleanup_old_files, create_task_lock

    upload_dir = tmp_path / "uploads"
    output_dir = tmp_path / "outputs"
    temp_dir = tmp_path / "tmp"
    batches_dir = upload_dir / "batches"
    for path in (upload_dir, output_dir, temp_dir, batches_dir):
        path.mkdir(parents=True)

    old = 10_000
    now = 20_000
    old_artifact = upload_dir / "old_final.mp4"
    recent_artifact = upload_dir / "recent_final.mp4"
    active_artifact = upload_dir / "active_final.mp4"
    stale_lock = upload_dir / "stale.lock"
    old_zip = output_dir / "subtitle_batch_old.zip"
    old_tmp = temp_dir / "leftover.tmp"
    old_batch = batches_dir / "batch_12345678.json"
    for path in (old_artifact, recent_artifact, active_artifact, stale_lock, old_zip, old_tmp, old_batch):
        path.write_text("x", encoding="utf-8")

    lock_path = Path(create_task_lock("active", str(upload_dir)))
    for path in (old_artifact, active_artifact, stale_lock, old_zip, old_tmp, old_batch):
        os.utime(path, (old, old))
    os.utime(lock_path, (now, now))
    os.utime(recent_artifact, (now, now))

    monkeypatch.setattr("backend.utils.cleanup_utils.time.time", lambda: now)
    monkeypatch.setattr("backend.utils.cleanup_utils.is_lock_stale", lambda path, threshold: str(path).endswith("stale.lock"))

    counts = cleanup_old_files(
        upload_dir=str(upload_dir),
        output_dir=str(output_dir),
        temp_dir=str(temp_dir),
        retention_seconds=3600,
    )

    assert old_artifact.exists() is False
    assert stale_lock.exists() is False
    assert old_zip.exists() is False
    assert old_tmp.exists() is False
    assert old_batch.exists() is False
    assert active_artifact.exists() is True
    assert recent_artifact.exists() is True
    assert counts["stale_locks_removed"] == 1
    assert counts["batch_metadata_removed"] == 1
    assert counts["preserved_locked"] >= 1


def test_cleanup_dry_run_preserves_files(monkeypatch: pytest.MonkeyPatch, tmp_path):
    from backend.utils.cleanup_utils import cleanup_old_files

    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    old_file = upload_dir / "old_error.json"
    old_file.write_text("{}", encoding="utf-8")
    os.utime(old_file, (1, 1))
    monkeypatch.setattr("backend.utils.cleanup_utils.time.time", lambda: 10_000)

    counts = cleanup_old_files(upload_dir=str(upload_dir), output_dir=str(tmp_path / "out"), temp_dir=str(tmp_path / "tmp"), retention_seconds=60, dry_run=True)

    assert old_file.exists() is True
    assert counts["dry_run"] is True
    assert counts["files_removed"] == 1


@pytest.mark.anyio
async def test_readyz_does_not_require_openai_key(monkeypatch: pytest.MonkeyPatch, tmp_path):
    main = _reload_main(monkeypatch, tmp_path)
    monkeypatch.setattr(main.settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(main, "run_media_command", lambda *a, **k: SimpleNamespace(returncode=0))
    monkeypatch.setattr(main, "_check_subtitle_font", lambda: {"available": True, "detail": "fake"})

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


def test_api_capabilities_reports_ollama_status(monkeypatch: pytest.MonkeyPatch, tmp_path):
    main = _reload_main(monkeypatch, tmp_path)
    monkeypatch.setattr(
        main,
        "get_llm_capability_status",
        lambda: SimpleNamespace(
            provider="ollama",
            model="gemma3:12b",
            translation_enabled=True,
            reason=None,
            message=None,
            default_target_language="Traditional Chinese",
            available_modes=["transcribe", "translate"],
            openai_configured=False,
        ),
    )

    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    response = client.get("/api/capabilities")

    assert response.status_code == 200
    assert response.json() == {
        "provider": "ollama",
        "model": "gemma3:12b",
        "translationEnabled": True,
        "reason": None,
        "message": None,
        "defaultTargetLanguage": "Traditional Chinese",
        "availableModes": ["transcribe", "translate"],
        "openaiConfigured": False,
    }


def test_ollama_capability_cache_expires_and_recovers(monkeypatch: pytest.MonkeyPatch):
    import backend.services.llm_capabilities as caps

    calls: list[bool] = []
    current_time = 1_000.0

    monkeypatch.setattr(caps.settings, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(caps.settings, "OLLAMA_BASE_URL", "http://ollama")
    monkeypatch.setattr(caps.settings, "OLLAMA_MODEL", "model")
    monkeypatch.setattr(caps.settings, "OLLAMA_CAPABILITY_CACHE_TTL_SECONDS", 10)
    monkeypatch.setattr(caps.time, "time", lambda: current_time)
    caps._OLLAMA_CACHE.clear()

    def probe():
        calls.append(True)
        return len(calls) > 1, None

    monkeypatch.setattr(caps, "_probe_ollama_tags", probe)

    first = caps.get_llm_capability_status()
    second = caps.get_llm_capability_status()
    assert first.translation_enabled is False
    assert second.translation_enabled is False
    assert len(calls) == 1

    current_time = 1_011.0
    third = caps.get_llm_capability_status()
    assert third.translation_enabled is True
    assert len(calls) == 2


def test_api_config_uses_capability_status_instead_of_openai_key(monkeypatch: pytest.MonkeyPatch, tmp_path):
    main = _reload_main(monkeypatch, tmp_path)
    monkeypatch.setattr(main.settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(
        main,
        "get_llm_capability_status",
        lambda: SimpleNamespace(
            provider="ollama",
            model="gemma3:12b",
            translation_enabled=True,
            reason=None,
            message=None,
            default_target_language="Traditional Chinese",
            available_modes=["transcribe", "translate"],
            openai_configured=False,
        ),
    )

    from fastapi.testclient import TestClient

    client = TestClient(main.app)
    response = client.get("/api/config")

    assert response.status_code == 200
    data = response.json()
    assert data["translationEnabled"] is True
    assert data["provider"] == "ollama"
    assert data["model"] == "gemma3:12b"
