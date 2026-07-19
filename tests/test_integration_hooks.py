from __future__ import annotations

import importlib
import json
import logging

import pytest


def _reload_tasks():
    import backend.settings as settings
    import backend.tasks as tasks

    importlib.reload(settings)
    return importlib.reload(tasks)


def _reload_main(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("TESTING", "true")

    import backend.settings as settings
    import backend.main as main

    importlib.reload(settings)
    return importlib.reload(main)


def test_integration_hooks_disabled_by_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("INTEGRATION_TEST_MODE", raising=False)
    tasks = _reload_tasks()

    assert tasks._integration_mode_enabled() is False


def test_special_filenames_do_not_trigger_when_integration_mode_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("INTEGRATION_TEST_MODE", raising=False)
    tasks = _reload_tasks()

    tasks._integration_block_task("task-1", "clip__integration_block_20s.mp4")
    tasks._integration_maybe_fail_segment({"source_filename": "clip__integration_fail_segment_1.mp4", "segment_idx": 1})


def test_normal_filenames_never_trigger_integration_behavior(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("INTEGRATION_TEST_MODE", "true")
    tasks = _reload_tasks()

    assert tasks._integration_block_seconds("normal-video.mp4") == 0
    assert tasks._integration_fail_segment_index("normal-video.mp4") is None


def test_integration_block_duration_rejects_malformed_or_oversized_values(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("INTEGRATION_TEST_MODE", "true")
    tasks = _reload_tasks()

    with pytest.raises(ValueError, match="Invalid integration test configuration"):
        tasks._integration_block_seconds("clip__integration_block_notanumber.mp4")

    with pytest.raises(ValueError, match="block duration must be 1-60 seconds"):
        tasks._integration_block_seconds("clip__integration_block_61s.mp4")


def test_deterministic_block_responds_to_task_cancellation(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("INTEGRATION_TEST_MODE", "true")
    tasks = _reload_tasks()
    current_time = {"value": 100.0}
    sleep_calls = {"count": 0}

    monkeypatch.setattr(tasks.settings, "get_upload_dir", lambda: "unused")
    monkeypatch.setattr(tasks.time, "time", lambda: current_time["value"])

    def fake_sleep(seconds: float) -> None:
        sleep_calls["count"] += 1
        current_time["value"] += seconds

    monkeypatch.setattr(tasks.time, "sleep", fake_sleep)

    cancel_checks = {"count": 0}

    def fake_is_canceled(_upload_dir: str, _task_id: str) -> bool:
        cancel_checks["count"] += 1
        return cancel_checks["count"] >= 2

    import backend.utils.task_control_utils as task_control_utils

    monkeypatch.setattr(task_control_utils, "is_task_canceled", fake_is_canceled)

    with pytest.raises(RuntimeError, match="Task canceled"):
        tasks._integration_block_task("task-1", "clip__integration_block_3s.mp4")

    assert sleep_calls["count"] == 1


def test_deterministic_segment_failure_affects_only_requested_segment(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("INTEGRATION_TEST_MODE", "true")
    tasks = _reload_tasks()

    tasks._integration_maybe_fail_segment(
        {"source_filename": "clip__integration_fail_segment_1.mp4", "segment_idx": 0}
    )

    with pytest.raises(RuntimeError, match="deterministic failure for segment 1"):
        tasks._integration_maybe_fail_segment(
            {"source_filename": "clip__integration_fail_segment_1.mp4", "segment_idx": 1}
        )


def test_integration_failure_does_not_log_user_filename(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture):
    monkeypatch.setenv("INTEGRATION_TEST_MODE", "true")
    tasks = _reload_tasks()
    monkeypatch.setattr(tasks.settings, "get_upload_dir", lambda: "unused")
    monkeypatch.setattr(tasks.time, "time", lambda: 100.0)
    monkeypatch.setattr(tasks.time, "sleep", lambda _seconds: None)

    import backend.utils.task_control_utils as task_control_utils

    monkeypatch.setattr(task_control_utils, "is_task_canceled", lambda *_args: True)

    with caplog.at_level(logging.INFO):
        with pytest.raises(RuntimeError, match="Task canceled"):
            tasks._integration_block_task("task-1", "secret-name__integration_block_1s.mp4")

    assert "secret-name" not in caplog.text


def test_production_refuses_to_start_with_integration_mode_enabled(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("INTEGRATION_TEST_MODE", "true")
    main = _reload_main(monkeypatch, tmp_path)

    with pytest.raises(RuntimeError, match="INTEGRATION_TEST_MODE=true is not allowed"):
        main.check_system_dependencies()


@pytest.mark.anyio
async def test_readyz_reports_invalid_production_integration_configuration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("INTEGRATION_TEST_MODE", "true")
    main = _reload_main(monkeypatch, tmp_path)
    monkeypatch.setattr(main, "_check_upload_dir_writable", lambda: None)
    monkeypatch.setattr(main, "_check_redis_ready", lambda: None)
    monkeypatch.setattr(main, "_check_ffmpeg_ready", lambda: None)
    monkeypatch.setattr(main, "_check_subtitle_font", lambda: {"available": True, "detail": "ok"})

    response = await main.readyz()
    payload = json.loads(response.body)

    assert payload["status"] == "error"
    assert any(
        error["code"] == "invalid_configuration" and "INTEGRATION_TEST_MODE=true is not allowed" in error["message"]
        for error in payload["errors"]
    )
