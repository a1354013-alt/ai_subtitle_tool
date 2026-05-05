import importlib
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def batch_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173")
    monkeypatch.setenv("CORS_ALLOW_CREDENTIALS", "true")

    import backend.main as main

    importlib.reload(main)
    monkeypatch.setattr(main.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="video\n", stderr=""))
    client = TestClient(main.app)
    return client, main


def test_batch_upload_basic(batch_app, monkeypatch: pytest.MonkeyPatch):
    client, main = batch_app
    upload_dir = Path(main.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(main, "_enqueue_process_video_task", lambda *args, **kwargs: None)

    video1 = upload_dir / "test1.mp4"
    video2 = upload_dir / "test2.mp4"
    video1.write_bytes(b"dummy video 1 content")
    video2.write_bytes(b"dummy video 2 content")

    with video1.open("rb") as f1, video2.open("rb") as f2:
        files = [
            ("files", ("test1.mp4", f1, "video/mp4")),
            ("files", ("test2.mp4", f2, "video/mp4")),
        ]
        response = client.post(
            "/batch/upload",
            files=files,
            data={"target_langs": "English", "burn_subtitles": "false"},
        )

    assert response.status_code == 200
    data = response.json()
    assert "batch_id" in data
    assert len(data["tasks"]) == 2
    assert all(task["status"] == "PENDING" for task in data["tasks"])

    batch_id = data["batch_id"]
    batch_file = Path(main.UPLOAD_DIR) / "batches" / f"{batch_id}.json"
    assert batch_file.exists()


def test_batch_status_returns_new_download_urls(batch_app, monkeypatch: pytest.MonkeyPatch):
    client, main = batch_app
    tasks = [
        {"task_id": str(uuid4()), "filename": "v1.mp4", "status": "PENDING"},
    ]
    batch_id = main.BATCH_MANAGER.create_batch(tasks)
    task_id = tasks[0]["task_id"]

    upload_dir = Path(main.UPLOAD_DIR)
    (upload_dir / f"{task_id}_English.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nhello\n", encoding="utf-8")
    (upload_dir / f"{task_id}_English.ass").write_text("[Script Info]\n", encoding="utf-8")
    (upload_dir / f"{task_id}_final.mp4").write_bytes(b"video")

    monkeypatch.setattr(
        main,
        "_get_async_result",
        lambda _task_id: main._TestingAsyncResult(status="SUCCESS", result={"warnings": []}),
    )

    response = client.get(f"/batch/{batch_id}/status")
    assert response.status_code == 200
    data = response.json()
    assert data["batch_id"] == batch_id
    assert data["total"] == 1
    assert data["completed"] == 1
    assert data["pending"] == 0
    assert len(data["tasks"]) == 1
    task = data["tasks"][0]
    assert task["download_urls"]["video"] == f"/download/{task_id}"
    assert task["download_urls"]["subtitles"]["English"]["srt"] == f"/download/{task_id}?lang=English&format=srt"
    assert task["download_urls"]["subtitles"]["English"]["ass"] == f"/download/{task_id}?lang=English&format=ass"
    assert task["download_urls"]["subtitles"]["English"]["vtt"] == f"/download/{task_id}?lang=English&format=vtt"


def test_batch_manager_preserves_failed_task_status(batch_app):
    client, main = batch_app
    task_id = str(uuid4())
    batch_id = main.BATCH_MANAGER.create_batch(
        [{"task_id": task_id, "filename": "bad.txt", "status": "FAILURE", "error": "Unsupported format"}]
    )

    batch = main.BATCH_MANAGER.get_batch(batch_id)
    assert batch is not None
    assert batch.tasks[0].status == "FAILURE"
    assert batch.tasks[0].error == "Unsupported format"

    response = client.get(f"/batch/{batch_id}/status")
    assert response.status_code == 200
    data = response.json()
    assert data["failed"] == 1
    assert data["tasks"][0]["status"] == "FAILURE"
    assert data["tasks"][0]["error"] == "Unsupported format"


def test_batch_upload_partial_failure_keeps_valid_tasks(batch_app, monkeypatch: pytest.MonkeyPatch):
    client, main = batch_app
    monkeypatch.setattr(main, "_enqueue_process_video_task", lambda *args, **kwargs: None)

    good = Path(main.UPLOAD_DIR) / "good.mp4"
    good.write_bytes(b"video")

    with good.open("rb") as good_file:
        response = client.post(
            "/batch/upload",
            files=[
                ("files", ("good.mp4", good_file, "video/mp4")),
                ("files", ("bad.mp4", b"hello", "text/plain")),
            ],
            data={"target_langs": "English", "burn_subtitles": "false", "subtitle_format": "srt"},
        )

    assert response.status_code == 200
    data = response.json()
    assert [task["status"] for task in data["tasks"]] == ["PENDING", "FAILURE"]
    assert "Invalid content type" in data["tasks"][1]["error"]


def test_batch_download_zip(batch_app, monkeypatch: pytest.MonkeyPatch):
    client, main = batch_app
    task_id = str(uuid4())
    tasks = [{"task_id": task_id, "filename": "fake.mp4", "status": "PENDING"}]
    batch_id = main.BATCH_MANAGER.create_batch(tasks)

    subtitle_path = Path(main.UPLOAD_DIR) / f"{task_id}_English.srt"
    subtitle_path.write_text("1\n00:00:00,000 --> 00:00:01,000\nhello\n", encoding="utf-8")

    monkeypatch.setattr(
        main,
        "_get_async_result",
        lambda _task_id: main._TestingAsyncResult(status="SUCCESS", result={"warnings": []}),
    )

    response = client.get(f"/batch/{batch_id}/download")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"

    zip_path = Path(main.UPLOAD_DIR) / f"subtitle_batch_{batch_id}.zip"
    assert zip_path.exists()


def test_upload_and_batch_share_option_validation(batch_app):
    client, _main = batch_app

    upload_response = client.post(
        "/upload",
        files={"file": ("demo.mp4", b"video", "video/mp4")},
        data={"target_langs": " , ", "subtitle_format": "ass"},
    )
    assert upload_response.status_code == 400
    assert upload_response.json()["detail"] == "target_langs must contain at least one non-empty language"

    batch_response = client.post(
        "/batch/upload",
        files=[("files", ("demo.mp4", b"video", "video/mp4"))],
        data={"target_langs": " , ", "subtitle_format": "ass"},
    )
    assert batch_response.status_code == 400
    assert batch_response.json()["detail"] == "target_langs must contain at least one non-empty language"
