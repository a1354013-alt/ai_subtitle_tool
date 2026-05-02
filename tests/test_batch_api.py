import importlib
from pathlib import Path
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

    batch_id = data["batch_id"]
    batch_file = Path(main.UPLOAD_DIR) / "batches" / f"{batch_id}.json"
    assert batch_file.exists()


def test_batch_status(batch_app):
    client, main = batch_app
    tasks = [
        {"task_id": str(uuid4()), "filename": "v1.mp4", "status": "queued"},
        {"task_id": str(uuid4()), "filename": "v2.mp4", "status": "queued"},
    ]
    batch_id = main.BATCH_MANAGER.create_batch(tasks)

    response = client.get(f"/batch/{batch_id}/status")
    assert response.status_code == 200
    data = response.json()
    assert data["batch_id"] == batch_id
    assert data["total"] == 2
    assert len(data["tasks"]) == 2


def test_batch_download_zip(batch_app, monkeypatch: pytest.MonkeyPatch):
    client, main = batch_app
    task_id = str(uuid4())
    tasks = [{"task_id": task_id, "filename": "fake.mp4", "status": "queued"}]
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
