from __future__ import annotations

import importlib
import os
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
import httpx


def _make_async_result(status: str, info: dict | None = None, result: dict | None = None):
    return SimpleNamespace(status=status, info=info, result=result)


@pytest.fixture()
async def app_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """
    FastAPI integration client with deterministic stubs:
    - isolated UPLOAD_DIR under tmp_path
    - ffprobe validation stubbed as "valid video"
    - Celery AsyncResult stubbed per-test via monkeypatch on backend.main._get_async_result
    """
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173")
    monkeypatch.setenv("CORS_ALLOW_CREDENTIALS", "true")

    # Import after env vars are set (UPLOAD_DIR and CORS are read at import time).
    import backend.main as main

    importlib.reload(main)

    # Stub ffprobe "video" validation to avoid needing real media bytes.
    def _fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout="video\n", stderr="")

    monkeypatch.setattr(main.subprocess, "run", _fake_run)

    # Stub enqueue to avoid requiring a running worker/redis.
    monkeypatch.setattr(main, "_enqueue_process_video_task", lambda *a, **k: None)

    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client, main, tmp_path


@pytest.mark.anyio
async def test_healthz(app_client):
    client, _main, _tmp = app_client
    r = await client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_app_config_contract(app_client):
    client, _main, _tmp = app_client
    r = await client.get("/api/config")
    assert r.status_code == 200
    body = r.json()
    assert body["maxUploadSizeMb"] == 2048
    assert ".mp4" in body["supportedExtensions"]
    assert body["batchUploadEnabled"] is True
    assert body["subtitleFormats"] == ["srt", "ass", "vtt"]


@pytest.mark.anyio
async def test_upload_contract_returns_uuid_and_pending(app_client):
    client, main, _tmp = app_client

    r = await client.post(
        "/upload",
        files={"file": ("demo.mp4", b"not-a-real-video", "video/mp4")},
        data={
            "target_langs": "Traditional Chinese, English",
            "burn_subtitles": "true",
            "subtitle_format": "srt",
            "remove_silence": "false",
            "parallel": "true",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "PENDING"
    assert body["progress"] == 0
    assert re.match(r"^[0-9a-fA-F-]{36}$", body["task_id"])

    # Upload should persist the file under UPLOAD_DIR.
    upload_dir = Path(main.UPLOAD_DIR)
    assert any(p.name.startswith(body["task_id"]) for p in upload_dir.iterdir())


@pytest.mark.anyio
async def test_status_contract_processing_and_success(app_client, monkeypatch: pytest.MonkeyPatch):
    client, main, _tmp = app_client

    task_id = "00000000-0000-0000-0000-000000000000"

    monkeypatch.setattr(
        main,
        "_get_async_result",
        lambda _tid: _make_async_result("PROGRESS", info={"progress": 12, "status": "Working...", "warnings": ["w1"]}),
    )
    r = await client.get(f"/status/{task_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["task_id"] == task_id
    assert body["status"] == "PROCESSING"
    assert body["progress"] == 12
    assert body["warnings"] == ["w1"]

    monkeypatch.setattr(
        main,
        "_get_async_result",
        lambda _tid: _make_async_result("SUCCESS", result={"warnings": ["w2"]}),
    )
    r2 = await client.get(f"/status/{task_id}")
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["status"] == "SUCCESS"
    assert body2["progress"] == 100
    assert body2["result_url"] == f"/results/{task_id}"
    assert body2["warnings"] == ["w2"]


@pytest.mark.anyio
async def test_status_contract_failure_exposes_error_code_and_suggestion(app_client, monkeypatch: pytest.MonkeyPatch):
    client, main, _tmp = app_client
    task_id = "99999999-9999-9999-9999-999999999999"

    monkeypatch.setattr(
        main,
        "_get_async_result",
        lambda _tid: _make_async_result(
            "FAILURE",
            result={
                "error_code": "ffmpeg_not_found",
                "message": "ffmpeg missing",
                "suggestion": "Install ffmpeg first",
            },
        ),
    )

    r = await client.get(f"/status/{task_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "FAILURE"
    assert body["error_code"] == "ffmpeg_not_found"
    assert body["suggestion"] == "Install ffmpeg first"


@pytest.mark.anyio
async def test_status_missing_task_returns_consistent_error_shape(app_client):
    client, _main, _tmp = app_client
    task_id = "12345678-1234-1234-1234-123456789012"

    r = await client.get(f"/status/{task_id}")
    assert r.status_code == 404
    body = r.json()
    assert body["error_code"] == "task_not_found"
    assert "message" in body
    assert "suggestion" in body


@pytest.mark.anyio
async def test_results_manifest_contract_and_orphan_detection(app_client, monkeypatch: pytest.MonkeyPatch):
    client, main, tmp_root = app_client

    task_id = "11111111-1111-1111-1111-111111111111"
    upload_dir = Path(main.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Orphaned file should be detected when task is not SUCCESS.
    (upload_dir / f"{task_id}_Traditional_Chinese.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
    monkeypatch.setattr(main, "_get_async_result", lambda _tid: _make_async_result("PENDING"))

    r = await client.get(f"/results/{task_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["task_status"] == "PENDING"
    assert body["available_files"] == []
    assert body["orphaned_files_detected"] is True

    # SUCCESS: enumerate available subtitle files.
    (upload_dir / f"{task_id}_Traditional_Chinese.ass").write_text("[Script Info]\n", encoding="utf-8")
    (upload_dir / f"{task_id}_final.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")
    monkeypatch.setattr(main, "_get_async_result", lambda _tid: _make_async_result("SUCCESS", result={"warnings": ["ok"]}))

    r2 = await client.get(f"/results/{task_id}")
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["task_status"] == "SUCCESS"
    assert body2["has_video"] is True
    assert body2["warnings"] == ["ok"]
    assert body2["available_files"] == [
        {"lang": "Traditional_Chinese", "display_name": "Traditional Chinese", "ass": True, "srt": True}
    ]


@pytest.mark.anyio
async def test_subtitle_get_put_and_download_vtt(app_client, monkeypatch: pytest.MonkeyPatch):
    client, main, _tmp = app_client

    task_id = "22222222-2222-2222-2222-222222222222"
    upload_dir = Path(main.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)

    srt_path = upload_dir / f"{task_id}_English.srt"
    srt_path.write_text("1\n00:00:00,000 --> 00:00:01,000\nhello\n", encoding="utf-8")
    final_path = upload_dir / f"{task_id}_final.mp4"
    final_path.write_bytes(b"fake")

    monkeypatch.setattr(main, "_get_async_result", lambda _tid: _make_async_result("SUCCESS"))

    r = await client.get(f"/subtitle/{task_id}", params={"lang": "English", "format": "srt"})
    assert r.status_code == 200
    assert r.json()["format"] == "srt"
    assert "hello" in r.json()["content"]

    r2 = await client.put(
        f"/subtitle/{task_id}",
        params={"lang": "English"},
        json={"format": "srt", "content": "UPDATED"},
    )
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["status"] == "updated"
    assert body2["format"] == "srt"
    assert body2["language"] == "English"
    assert srt_path.read_text(encoding="utf-8") == "UPDATED"
    # Updating subtitles deletes final video to avoid stale outputs.
    assert final_path.exists() is False
    assert body2["warnings"]

    r3 = await client.get(f"/download/{task_id}", params={"lang": "English", "format": "vtt"})
    assert r3.status_code == 200
    assert r3.headers["content-type"].startswith("text/vtt")
    assert "WEBVTT" in r3.text


@pytest.mark.anyio
async def test_rebuild_final_contract_enqueues(app_client, monkeypatch: pytest.MonkeyPatch):
    client, main, _tmp = app_client
    task_id = "44444444-4444-4444-4444-444444444444"
    called: dict[str, str] = {}

    def _fake_enqueue(task_id: str, lang_suffix: str, subtitle_format: str) -> None:
        called["task_id"] = task_id
        called["lang_suffix"] = lang_suffix
        called["subtitle_format"] = subtitle_format

    monkeypatch.setattr(main, "_enqueue_rebuild_final_task", _fake_enqueue)
    r = await client.post(f"/tasks/{task_id}/rebuild-final", params={"lang": "Traditional_Chinese", "format": "ass"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "queued"
    assert called == {"task_id": task_id, "lang_suffix": "Traditional_Chinese", "subtitle_format": "ass"}


@pytest.mark.anyio
async def test_cancel_contract_marks_task_canceled(app_client, monkeypatch: pytest.MonkeyPatch):
    client, main, _tmp = app_client
    task_id = "55555555-5555-5555-5555-555555555555"

    class _AR:
        def revoke(self, terminate: bool = False):
            return None

    monkeypatch.setattr(main, "_get_async_result", lambda _tid: _AR())

    r = await client.post(f"/tasks/{task_id}/cancel")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "canceled"

    r2 = await client.get(f"/status/{task_id}")
    assert r2.status_code == 200
    body = r2.json()
    assert body["status"] == "CANCELED"
    assert body["error_code"] == "task_canceled"
    assert body["suggestion"]
