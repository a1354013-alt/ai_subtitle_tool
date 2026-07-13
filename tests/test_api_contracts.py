from __future__ import annotations

import importlib
import os
import re
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
import httpx


def _make_async_result(status: str, info: dict | None = None, result: dict | None = None):
    return SimpleNamespace(status=status, info=info, result=result)


VALID_SRT = "1\n00:00:00,000 --> 00:00:01,000\nhello\n"
VALID_ASS = """[Script Info]
Title: Test

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,hello
"""


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
        return SimpleNamespace(returncode=0, stdout="video\naudio\n", stderr="")

    monkeypatch.setattr(main, "run_media_command", _fake_run)

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
async def test_auth_token_middleware_enforces_non_health_routes(app_client, monkeypatch: pytest.MonkeyPatch):
    client, main, _tmp = app_client
    monkeypatch.setattr(main.settings, "REQUIRE_AUTH_TOKEN", True)
    monkeypatch.setattr(main.settings, "AUTH_TOKEN", "secret")

    assert (await client.get("/healthz")).status_code == 200
    unauthorized = await client.get("/api/config")
    assert unauthorized.status_code == 401

    authorized = await client.get("/api/config", headers={"X-API-Token": "secret"})
    assert authorized.status_code == 200


@pytest.mark.anyio
async def test_rate_limit_middleware_returns_429(app_client, monkeypatch: pytest.MonkeyPatch):
    client, main, _tmp = app_client
    main._RATE_LIMIT_BUCKETS.clear()
    monkeypatch.setattr(main.settings, "RATE_LIMIT_PER_IP", 2)

    first = await client.get("/api/config")
    second = await client.get("/api/config")
    third = await client.get("/api/config")

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    main._RATE_LIMIT_BUCKETS.clear()


@pytest.mark.anyio
async def test_rate_limit_middleware_exempts_safe_status_polling(app_client, monkeypatch: pytest.MonkeyPatch):
    client, main, _tmp = app_client
    main._RATE_LIMIT_BUCKETS.clear()
    monkeypatch.setattr(main.settings, "RATE_LIMIT_PER_IP", 1)

    monkeypatch.setattr(main, "_get_async_result", lambda _tid: _make_async_result("PENDING"))
    task_id = "00000000-0000-0000-0000-000000000001"
    main.TASK_HISTORY.upsert_created(task_id=task_id, filename="demo.mp4", status="PENDING")
    batch_id = main.BATCH_MANAGER.create_batch([
        {"task_id": task_id, "filename": "demo.mp4", "status": "PENDING", "error": None}
    ])

    first = await client.get("/api/config")
    limited = await client.get("/api/config")
    status_responses = [await client.get(f"/status/{task_id}") for _ in range(3)]
    batch_responses = [await client.get(f"/batch/{batch_id}/status") for _ in range(2)]

    assert first.status_code == 200
    assert limited.status_code == 429
    assert [response.status_code for response in status_responses] == [200, 200, 200]
    assert [response.status_code for response in batch_responses] == [200, 200]
    main._RATE_LIMIT_BUCKETS.clear()


@pytest.mark.anyio
async def test_rate_limit_middleware_disabled_at_zero(app_client, monkeypatch: pytest.MonkeyPatch):
    client, main, _tmp = app_client
    main._RATE_LIMIT_BUCKETS.clear()
    monkeypatch.setattr(main.settings, "RATE_LIMIT_PER_IP", 0)

    responses = [await client.get("/api/config") for _ in range(5)]

    assert [response.status_code for response in responses] == [200, 200, 200, 200, 200]
    main._RATE_LIMIT_BUCKETS.clear()


@pytest.mark.anyio
async def test_openapi_exposes_stable_contract_fields(app_client):
    client, _main, _tmp = app_client
    r = await client.get("/openapi.json")
    assert r.status_code == 200
    schemas = r.json()["components"]["schemas"]
    assert "AppConfigResponse" in schemas
    assert "TaskResultManifest" in schemas
    assert "BatchStatusResponse" in schemas
    assert "maxUploadSizeMb" in schemas["AppConfigResponse"]["properties"]
    assert "translations" in schemas["TaskResultManifest"]["properties"]


@pytest.mark.anyio
async def test_development_docs_are_available(app_client):
    client, _main, _tmp = app_client

    docs = await client.get("/docs")
    openapi = await client.get("/openapi.json")

    assert docs.status_code != 404
    assert docs.status_code == 200
    assert openapi.status_code != 404
    assert openapi.status_code == 200


@pytest.mark.anyio
async def test_upload_contract_returns_uuid_and_pending(app_client):
    client, main, _tmp = app_client

    r = await client.post(
        "/upload",
        files={"file": ("demo.mp4", b"not-a-real-video", "video/mp4")},
        data={
            "target_langs": "Original",
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
async def test_status_uses_durable_success_when_redis_returns_pending(app_client, monkeypatch: pytest.MonkeyPatch):
    client, main, _tmp = app_client
    task_id = "11111111-1111-1111-1111-111111111111"

    main.TASK_HISTORY.upsert_created(task_id=task_id, filename="demo.mp4", status="PENDING")
    main.TASK_HISTORY.update_status(
        task_id,
        "SUCCESS",
        progress=100,
        message="Completed without polling",
        warnings=["persisted warning"],
    )
    monkeypatch.setattr(main, "_get_async_result", lambda _tid: _make_async_result("PENDING"))

    response = await client.get(f"/status/{task_id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "SUCCESS"
    assert body["progress"] == 100
    assert body["message"] == "Completed without polling"
    assert body["warnings"] == ["persisted warning"]


@pytest.mark.anyio
async def test_status_uses_durable_failure_when_redis_returns_pending(app_client, monkeypatch: pytest.MonkeyPatch):
    client, main, _tmp = app_client
    task_id = "22222222-2222-2222-2222-222222222222"

    main.TASK_HISTORY.upsert_created(task_id=task_id, filename="demo.mp4", status="PENDING")
    main.TASK_HISTORY.update_status(
        task_id,
        "FAILURE",
        progress=0,
        message="ffmpeg missing",
        error_code="ffmpeg_not_found",
        suggestion="Install ffmpeg",
    )
    monkeypatch.setattr(main, "_get_async_result", lambda _tid: _make_async_result("PENDING"))

    response = await client.get(f"/status/{task_id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "FAILURE"
    assert body["error_code"] == "ffmpeg_not_found"
    assert body["suggestion"] == "Install ffmpeg"


@pytest.mark.anyio
async def test_status_uses_local_artifacts_when_redis_state_is_lost(app_client, monkeypatch: pytest.MonkeyPatch):
    client, main, _tmp = app_client
    task_id = "33333333-3333-3333-3333-333333333333"
    Path(main.UPLOAD_DIR, f"{task_id}_English.srt").write_text(VALID_SRT, encoding="utf-8")
    monkeypatch.setattr(main, "_get_async_result", lambda _tid: _make_async_result("PENDING"))

    response = await client.get(f"/status/{task_id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "SUCCESS"
    assert body["result_url"] == f"/results/{task_id}"


@pytest.mark.anyio
async def test_worker_completion_persists_without_status_polling(app_client, monkeypatch: pytest.MonkeyPatch):
    client, main, _tmp = app_client
    import backend.tasks as tasks

    task_id = "33333333-3333-3333-3333-333333333334"
    main.TASK_HISTORY.upsert_created(task_id=task_id, filename="demo.mp4", status="PENDING")
    tasks._record_task_state(task_id, "SUCCESS", progress=100, message="Completed", warnings=["from worker"])
    monkeypatch.setattr(main, "_get_async_result", lambda _tid: _make_async_result("PENDING"))

    response = await client.get(f"/status/{task_id}")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "SUCCESS"
    assert response.json()["warnings"] == ["from worker"]


@pytest.mark.anyio
async def test_status_contract_failure_prefers_info_payload(app_client, monkeypatch: pytest.MonkeyPatch):
    client, main, _tmp = app_client
    task_id = "99999999-9999-9999-9999-999999999998"

    monkeypatch.setattr(
        main,
        "_get_async_result",
        lambda _tid: _make_async_result(
            "FAILURE",
            info={
                "error_code": "upload_failed",
                "message": "info payload wins",
                "suggestion": "Retry upload",
            },
            result={
                "error_code": "ffmpeg_not_found",
                "message": "result payload should be ignored here",
                "suggestion": "Install ffmpeg first",
            },
        ),
    )

    r = await client.get(f"/status/{task_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "FAILURE"
    assert body["error_code"] == "upload_failed"
    assert body["message"] == "info payload wins"
    assert body["suggestion"] == "Retry upload"


@pytest.mark.anyio
async def test_status_contract_failure_handles_exception_result_without_500(app_client, monkeypatch: pytest.MonkeyPatch):
    client, main, _tmp = app_client
    task_id = "99999999-9999-9999-9999-999999999997"

    monkeypatch.setattr(
        main,
        "_get_async_result",
        lambda _tid: _make_async_result("FAILURE", result=RuntimeError("boom")),
    )

    r = await client.get(f"/status/{task_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "FAILURE"
    assert isinstance(body["message"], str)
    assert isinstance(body["error_code"], str)


@pytest.mark.anyio
async def test_status_contract_failure_handles_non_dict_info_and_result_without_500(app_client, monkeypatch: pytest.MonkeyPatch):
    client, main, _tmp = app_client
    task_id = "99999999-9999-9999-9999-999999999996"

    monkeypatch.setattr(
        main,
        "_get_async_result",
        lambda _tid: _make_async_result("FAILURE", info="bad-info", result="bad-result"),
    )

    r = await client.get(f"/status/{task_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "FAILURE"
    assert isinstance(body["message"], str)
    assert isinstance(body["error_code"], str)


@pytest.mark.anyio
async def test_status_failure_falls_back_to_error_artifact(app_client, monkeypatch: pytest.MonkeyPatch):
    client, main, _tmp = app_client
    task_id = "99999999-9999-9999-9999-999999999995"
    upload_dir = Path(main.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    (upload_dir / f"{task_id}_error.json").write_text(
        '{"error_code":"ffmpeg_not_found","message":"artifact wins","suggestion":"Install ffmpeg"}',
        encoding="utf-8",
    )

    monkeypatch.setattr(main, "_get_async_result", lambda _tid: _make_async_result("FAILURE", info=None, result=None))

    r = await client.get(f"/status/{task_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "FAILURE"
    assert body["message"] == "artifact wins"


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
    assert body["available_files"][0]["lang"] == "Traditional_Chinese"
    assert body["orphaned_files_detected"] is True

    # SUCCESS: enumerate available subtitle files.
    (upload_dir / f"{task_id}_Traditional_Chinese.ass").write_text("[Script Info]\n", encoding="utf-8")
    (upload_dir / f"{task_id}_final.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")
    monkeypatch.setattr(
        main,
        "_get_async_result",
        lambda _tid: _make_async_result(
            "SUCCESS",
            result={
                "warnings": ["ok"],
                "translations": [
                    {"language": "Traditional Chinese", "translated": False, "fallback_reason": "provider unavailable"}
                ],
            },
        ),
    )

    r2 = await client.get(f"/results/{task_id}")
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["task_status"] == "SUCCESS"
    assert body2["has_video"] is True
    assert body2["warnings"] == ["ok"]
    assert body2["available_files"] == [
        {
            "lang": "Traditional_Chinese",
            "display_name": "Traditional Chinese",
            "ass": True,
            "srt": True,
            "vtt": True,
            "translated": False,
            "fallback_reason": "provider unavailable",
        }
    ]
    assert body2["translations"] == [
        {"language": "Traditional Chinese", "translated": False, "fallback_reason": "provider unavailable"}
    ]


@pytest.mark.anyio
async def test_subtitle_get_put_and_download_vtt(app_client, monkeypatch: pytest.MonkeyPatch):
    client, main, _tmp = app_client

    task_id = "22222222-2222-2222-2222-222222222222"
    upload_dir = Path(main.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)

    srt_path = upload_dir / f"{task_id}_English.srt"
    srt_path.write_text(VALID_SRT, encoding="utf-8")
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
        json={"format": "srt", "content": "1\n00:00:00,000 --> 00:00:01,500\nupdated\n"},
    )
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["status"] == "updated"
    assert body2["format"] == "srt"
    assert body2["language"] == "English"
    assert srt_path.read_text(encoding="utf-8") == "1\n00:00:00,000 --> 00:00:01,500\nupdated\n"
    # Updating subtitles deletes final video to avoid stale outputs.
    assert final_path.exists() is False
    assert body2["warnings"]

    r3 = await client.get(f"/download/{task_id}", params={"lang": "English", "format": "vtt"})
    assert r3.status_code == 200
    assert r3.headers["content-type"].startswith("text/vtt")
    assert "WEBVTT" in r3.text


@pytest.mark.anyio
async def test_protected_download_rejects_without_header_or_ticket(app_client, monkeypatch: pytest.MonkeyPatch):
    client, main, _tmp = app_client
    task_id = "12345678-1234-1234-1234-123456789abc"
    Path(main.UPLOAD_DIR, f"{task_id}_final.mp4").write_bytes(b"video")
    monkeypatch.setattr(main.settings, "REQUIRE_AUTH_TOKEN", True)
    monkeypatch.setattr(main.settings, "AUTH_TOKEN", "secret")

    response = await client.get(f"/download/{task_id}")

    assert response.status_code == 401


@pytest.mark.anyio
async def test_protected_download_accepts_short_lived_ticket(app_client, monkeypatch: pytest.MonkeyPatch):
    client, main, _tmp = app_client
    task_id = "12345678-1234-1234-1234-123456789abd"
    Path(main.UPLOAD_DIR, f"{task_id}_final.mp4").write_bytes(b"video")
    monkeypatch.setattr(main.settings, "REQUIRE_AUTH_TOKEN", True)
    monkeypatch.setattr(main.settings, "AUTH_TOKEN", "secret")
    monkeypatch.setattr(main.settings, "DOWNLOAD_TICKET_TTL_SECONDS", 60)

    ticket_response = await client.get(
        "/download-ticket",
        params={"path": f"/download/{task_id}"},
        headers={"X-API-Token": "secret"},
    )
    assert ticket_response.status_code == 200, ticket_response.text

    download_response = await client.get(ticket_response.json()["url"])

    assert download_response.status_code == 200
    assert download_response.content == b"video"


@pytest.mark.anyio
async def test_protected_batch_download_accepts_short_lived_ticket(app_client, monkeypatch: pytest.MonkeyPatch):
    client, main, _tmp = app_client
    task_id = "12345678-1234-1234-1234-123456789abe"
    Path(main.UPLOAD_DIR, f"{task_id}_English.srt").write_text(VALID_SRT, encoding="utf-8")
    batch_id = main.BATCH_MANAGER.create_batch([{"task_id": task_id, "filename": "demo.mp4", "status": "SUCCESS"}])
    monkeypatch.setattr(main, "_get_async_result", lambda _tid: _make_async_result("SUCCESS"))
    monkeypatch.setattr(main.settings, "REQUIRE_AUTH_TOKEN", True)
    monkeypatch.setattr(main.settings, "AUTH_TOKEN", "secret")

    denied = await client.get(f"/batch/{batch_id}/download")
    assert denied.status_code == 401

    ticket_response = await client.get(
        "/download-ticket",
        params={"path": f"/batch/{batch_id}/download"},
        headers={"X-API-Token": "secret"},
    )
    assert ticket_response.status_code == 200, ticket_response.text

    download_response = await client.get(ticket_response.json()["url"])
    assert download_response.status_code == 200
    assert download_response.headers["content-type"].startswith("application/zip")


@pytest.mark.anyio
async def test_protected_subtitle_download_accepts_short_lived_ticket(app_client, monkeypatch: pytest.MonkeyPatch):
    client, main, _tmp = app_client
    task_id = "12345678-1234-1234-1234-123456789abf"
    Path(main.UPLOAD_DIR, f"{task_id}_English.srt").write_text(VALID_SRT, encoding="utf-8")
    monkeypatch.setattr(main.settings, "REQUIRE_AUTH_TOKEN", True)
    monkeypatch.setattr(main.settings, "AUTH_TOKEN", "secret")
    path = f"/download/{task_id}?lang=English&format=srt"

    ticket_response = await client.get("/download-ticket", params={"path": path}, headers={"X-API-Token": "secret"})
    assert ticket_response.status_code == 200, ticket_response.text

    download_response = await client.get(ticket_response.json()["url"])
    assert download_response.status_code == 200
    assert download_response.text.replace("\r\n", "\n") == VALID_SRT


@pytest.mark.anyio
async def test_update_subtitle_deletes_stale_s3_final_video(app_client, monkeypatch: pytest.MonkeyPatch):
    client, main, _tmp = app_client
    task_id = "22222222-2222-2222-2222-222222222222"
    upload_dir = Path(main.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    (upload_dir / f"{task_id}_English.srt").write_text(VALID_SRT, encoding="utf-8")

    deleted: list[str] = []

    class RecordingStorage:
        def delete_file(self, remote_path: str) -> bool:
            deleted.append(remote_path)
            return True

    monkeypatch.setattr(main.settings, "STORAGE_BACKEND", "s3")
    monkeypatch.setattr(main, "get_storage_backend", lambda: RecordingStorage())

    response = await client.put(
        f"/subtitle/{task_id}",
        params={"lang": "English"},
        json={"format": "srt", "content": "1\n00:00:00,000 --> 00:00:01,500\nupdated\n"},
    )

    assert response.status_code == 200, response.text
    assert deleted == [f"{task_id}_final.mp4"]
    assert any("Stored final video was deleted" in warning for warning in response.json()["warnings"])


@pytest.mark.anyio
async def test_update_subtitle_accepts_valid_ass(app_client):
    client, main, _tmp = app_client
    task_id = "22222222-2222-2222-2222-222222222223"
    upload_dir = Path(main.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    ass_path = upload_dir / f"{task_id}_English.ass"
    ass_path.write_text(VALID_ASS, encoding="utf-8")

    response = await client.put(
        f"/subtitle/{task_id}",
        params={"lang": "English"},
        json={"format": "ass", "content": VALID_ASS.replace("hello", "updated")},
    )

    assert response.status_code == 200, response.text
    assert "updated" in ass_path.read_text(encoding="utf-8")


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("content", "expected_message"),
    [
        ("", "must not be empty"),
        ("1\n00:00:00,000 -> 00:00:01,000\nhello\n", "at least one cue"),
        ("1\n00:00:02,000 --> 00:00:01,000\nhello\n", "start time must be before"),
        (
            "1\n00:00:02,000 --> 00:00:03,000\nhello\n\n2\n00:00:01,000 --> 00:00:02,000\nback\n",
            "must not go backwards",
        ),
    ],
)
async def test_update_subtitle_rejects_invalid_srt(app_client, content: str, expected_message: str):
    client, main, _tmp = app_client
    task_id = "22222222-2222-2222-2222-222222222224"
    upload_dir = Path(main.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    (upload_dir / f"{task_id}_English.srt").write_text(VALID_SRT, encoding="utf-8")

    response = await client.put(
        f"/subtitle/{task_id}",
        params={"lang": "English"},
        json={"format": "srt", "content": content},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["error_code"] == "invalid_subtitle_format"
    assert expected_message in body["message"]
    assert body["suggestion"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("content", "expected_message"),
    [
        ("[V4+ Styles]\n[Events]\nDialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,hello\n", "[Script Info]"),
        ("[Script Info]\n[V4+ Styles]\n[Events]\n", "Dialogue"),
    ],
)
async def test_update_subtitle_rejects_invalid_ass(app_client, content: str, expected_message: str):
    client, main, _tmp = app_client
    task_id = "22222222-2222-2222-2222-222222222225"
    upload_dir = Path(main.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    (upload_dir / f"{task_id}_English.ass").write_text(VALID_ASS, encoding="utf-8")

    response = await client.put(
        f"/subtitle/{task_id}",
        params={"lang": "English"},
        json={"format": "ass", "content": content},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["error_code"] == "invalid_subtitle_format"
    assert expected_message in body["message"]
    assert body["suggestion"]


@pytest.mark.anyio
async def test_update_subtitle_rejects_oversized_content(app_client):
    client, main, _tmp = app_client
    task_id = "22222222-2222-2222-2222-222222222226"
    upload_dir = Path(main.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    (upload_dir / f"{task_id}_English.srt").write_text(VALID_SRT, encoding="utf-8")

    response = await client.put(
        f"/subtitle/{task_id}",
        params={"lang": "English"},
        json={"format": "srt", "content": "x" * (5 * 1024 * 1024 + 1)},
    )

    assert response.status_code == 400
    assert response.json()["error_code"] == "invalid_subtitle_format"
    assert "5 MB limit" in response.json()["message"]


@pytest.mark.anyio
async def test_invalid_subtitle_does_not_overwrite_existing_file(app_client):
    client, main, _tmp = app_client
    task_id = "22222222-2222-2222-2222-222222222227"
    upload_dir = Path(main.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    srt_path = upload_dir / f"{task_id}_English.srt"
    srt_path.write_text(VALID_SRT, encoding="utf-8")

    response = await client.put(
        f"/subtitle/{task_id}",
        params={"lang": "English"},
        json={"format": "srt", "content": "not a subtitle"},
    )

    assert response.status_code == 400
    assert srt_path.read_text(encoding="utf-8") == VALID_SRT


@pytest.mark.anyio
async def test_results_manifest_marks_vtt_available_only_when_srt_exists(app_client, monkeypatch: pytest.MonkeyPatch):
    client, main, _tmp = app_client
    task_id = "33333333-3333-3333-3333-333333333333"
    upload_dir = Path(main.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    (upload_dir / f"{task_id}_English.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nhello\n", encoding="utf-8")
    (upload_dir / f"{task_id}_Japanese.ass").write_text("[Script Info]\n", encoding="utf-8")

    monkeypatch.setattr(main, "_get_async_result", lambda _tid: _make_async_result("SUCCESS"))

    response = await client.get(f"/results/{task_id}")
    assert response.status_code == 200
    by_lang = {item["lang"]: item for item in response.json()["available_files"]}

    assert by_lang["English"]["srt"] is True
    assert by_lang["English"]["vtt"] is True
    assert by_lang["Japanese"]["srt"] is False
    assert by_lang["Japanese"]["vtt"] is False


@pytest.mark.anyio
async def test_rebuild_final_contract_enqueues(app_client, monkeypatch: pytest.MonkeyPatch):
    client, main, _tmp = app_client
    task_id = "44444444-4444-4444-4444-444444444444"

    r = await client.post(f"/tasks/{task_id}/rebuild-final", params={"lang": "Traditional_Chinese", "format": "ass"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "queued"
    assert body["task_id"] == task_id
    rebuild_task_id = body["rebuild_task_id"]
    assert str(uuid.UUID(rebuild_task_id)) == rebuild_task_id

    status_response = await client.get(f"/status/{rebuild_task_id}")
    assert status_response.status_code == 200, status_response.text
    assert status_response.json()["task_id"] == rebuild_task_id
    assert status_response.json()["status"] == "PENDING"


@pytest.mark.anyio
async def test_rebuild_final_history_failure_does_not_return_queued(app_client, monkeypatch: pytest.MonkeyPatch):
    client, main, _tmp = app_client
    task_id = "44444444-4444-4444-4444-444444444444"

    class FailingHistory:
        def upsert_created(self, *_args, **_kwargs):
            raise RuntimeError("sqlite unavailable")

    monkeypatch.setattr(main, "TASK_HISTORY", FailingHistory())

    response = await client.post(f"/tasks/{task_id}/rebuild-final", params={"lang": "Traditional_Chinese", "format": "ass"})
    assert response.status_code == 500, response.text
    body = response.json()
    assert body["detail"] == "Failed to record rebuild task history"
    assert body.get("status") != "queued"


@pytest.mark.anyio
async def test_rebuild_final_enqueue_failure_marks_history_failure(app_client, monkeypatch: pytest.MonkeyPatch):
    client, main, _tmp = app_client
    task_id = "44444444-4444-4444-4444-444444444444"

    def _fail_enqueue(*_args, **_kwargs):
        raise RuntimeError("broker unavailable")

    monkeypatch.setattr(main, "_enqueue_rebuild_final_task", _fail_enqueue)

    response = await client.post(f"/tasks/{task_id}/rebuild-final", params={"lang": "Traditional_Chinese", "format": "ass"})
    assert response.status_code == 503, response.text

    entries = main.TASK_HISTORY.list_recent(limit=1)
    assert len(entries) == 1
    assert entries[0].status == "FAILURE"


@pytest.mark.anyio
async def test_rebuild_success_status_points_to_original_result_task(app_client, monkeypatch: pytest.MonkeyPatch):
    client, main, _tmp = app_client
    original_task_id = "44444444-4444-4444-4444-444444444444"
    rebuild_task_id = "66666666-6666-6666-6666-666666666666"

    monkeypatch.setattr(
        main,
        "_get_async_result",
        lambda _tid: _make_async_result(
            "SUCCESS",
            result={"warnings": [], "result_task_id": original_task_id},
        ),
    )

    response = await client.get(f"/status/{rebuild_task_id}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["task_id"] == rebuild_task_id
    assert body["status"] == "SUCCESS"
    assert body["result_task_id"] == original_task_id
    assert body["result_url"] == f"/results/{original_task_id}"


@pytest.mark.anyio
async def test_successful_rebuild_updates_final_video_manifest(app_client, monkeypatch: pytest.MonkeyPatch):
    client, main, _tmp = app_client
    import backend.tasks as tasks
    import backend.utils.subtitle_video_utils as subtitle_video_utils

    task_id = "44444444-4444-4444-4444-444444444445"
    upload_dir = Path(main.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    (upload_dir / f"{task_id}.mp4").write_bytes(b"video")
    (upload_dir / f"{task_id}_English.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nhello\n", encoding="utf-8")

    class RecordingStorage:
        def upload_file(self, *_args, **_kwargs):
            return True

    def fake_burn(_video_path, _subtitle_path, output_path):
        Path(output_path).write_bytes(b"rebuilt")

    monkeypatch.setenv("UPLOAD_DIR", str(upload_dir))
    monkeypatch.setattr(tasks, "get_storage_backend", lambda: RecordingStorage())
    monkeypatch.setattr(subtitle_video_utils, "burn_subtitles", fake_burn)
    monkeypatch.setattr(tasks.rebuild_final_video_task, "update_state", lambda *args, **kwargs: None)

    result = tasks.rebuild_final_video_task.run(task_id, "English", "srt")
    monkeypatch.setattr(main, "_get_async_result", lambda _tid: _make_async_result("SUCCESS", result=result))

    response = await client.get(f"/results/{task_id}")

    assert response.status_code == 200, response.text
    assert response.json()["has_video"] is True


@pytest.mark.anyio
async def test_cancel_contract_marks_task_canceled(app_client, monkeypatch: pytest.MonkeyPatch):
    client, main, _tmp = app_client
    task_id = "55555555-5555-5555-5555-555555555555"

    class _AR:
        def revoke(self, terminate: bool = False):
            return None

    main.TASK_HISTORY.upsert_created(task_id=task_id, filename="demo.mp4", status="PENDING")
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


@pytest.mark.anyio
async def test_cancel_unknown_task_rejects_without_creating_history(app_client):
    client, main, _tmp = app_client
    task_id = "55555555-5555-5555-5555-555555555556"

    response = await client.post(f"/tasks/{task_id}/cancel")

    assert response.status_code == 404
    assert main.TASK_HISTORY.get(task_id) is None
