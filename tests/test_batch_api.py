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
    monkeypatch.setattr(
        main.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="video\n", stderr=""),
    )
    client = TestClient(main.app)
    return client, main


def test_batch_upload_basic(batch_app, monkeypatch: pytest.MonkeyPatch):
    client, main = batch_app
    upload_dir = Path(main.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(main, "_enqueue_process_video_task", lambda *args, **kwargs: None)

    with (
        (upload_dir / "test1.mp4").open("wb+") as f1,
        (upload_dir / "test2.mp4").open("wb+") as f2,
    ):
        f1.write(b"dummy video 1 content")
        f1.seek(0)
        f2.write(b"dummy video 2 content")
        f2.seek(0)
        response = client.post(
            "/batch/upload",
            files=[
                ("files", ("test1.mp4", f1, "video/mp4")),
                ("files", ("test2.mp4", f2, "video/mp4")),
            ],
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


def test_batch_upload_invalid_format_is_rejected_without_enqueue(batch_app, monkeypatch: pytest.MonkeyPatch):
    client, main = batch_app
    enqueue_calls: list[str] = []
    monkeypatch.setattr(main, "_enqueue_process_video_task", lambda *_args, **_kwargs: enqueue_calls.append("queued"))

    response = client.post(
        "/batch/upload",
        files=[("files", ("bad.txt", b"not-video", "text/plain"))],
        data={"target_langs": "English", "burn_subtitles": "false"},
    )

    assert response.status_code == 200
    task = response.json()["tasks"][0]
    assert task["status"] == "FAILURE"
    assert "Invalid content type" in task["error"]
    assert enqueue_calls == []


def test_batch_manager_preserves_failed_status_and_error(tmp_path: Path):
    from backend.batch_manager import BatchManager

    manager = BatchManager(str(tmp_path / "uploads"))
    batch_id = manager.create_batch(
        [
            {
                "task_id": str(uuid4()),
                "filename": "bad.mp4",
                "status": "FAILURE",
                "error": "ffprobe rejected file",
                "download_urls": None,
                "target_langs": ["English"],
            }
        ]
    )

    metadata = manager.get_batch(batch_id)
    assert metadata is not None
    task = metadata.tasks[0]
    assert task.status == "FAILURE"
    assert task.error == "ffprobe rejected file"


def test_batch_status_uses_download_endpoint_urls(batch_app, monkeypatch: pytest.MonkeyPatch):
    client, main = batch_app
    task_id = str(uuid4())
    batch_id = main.BATCH_MANAGER.create_batch(
        [
            {
                "task_id": task_id,
                "filename": "v1.mp4",
                "status": "PENDING",
                "error": None,
                "download_urls": None,
                "target_langs": ["Traditional Chinese"],
            }
        ]
    )

    monkeypatch.setattr(
        main,
        "_get_async_result",
        lambda _task_id: main._TestingAsyncResult(status="SUCCESS", result={"warnings": []}),
    )

    response = client.get(f"/batch/{batch_id}/status")
    assert response.status_code == 200
    data = response.json()
    task = data["tasks"][0]
    assert task["status"] == "SUCCESS"
    assert task["download_urls"]["srt"] == f"/download/{task_id}?lang=Traditional+Chinese&format=srt"
    assert task["download_urls"]["ass"] == f"/download/{task_id}?lang=Traditional+Chinese&format=ass"
    assert task["download_urls"]["video"] == f"/download/{task_id}?format=video"


def test_batch_status_preserves_failed_metadata_without_overwriting(batch_app):
    client, main = batch_app
    task_id = str(uuid4())
    batch_id = main.BATCH_MANAGER.create_batch(
        [
            {
                "task_id": task_id,
                "filename": "broken.mp4",
                "status": "FAILURE",
                "error": "Unsupported format",
                "download_urls": None,
                "target_langs": ["English"],
            }
        ]
    )

    response = client.get(f"/batch/{batch_id}/status")
    assert response.status_code == 200
    task = response.json()["tasks"][0]
    assert task["status"] == "FAILURE"
    assert task["error"] == "Unsupported format"


def test_batch_download_zip(batch_app, monkeypatch: pytest.MonkeyPatch):
    client, main = batch_app
    task_id = str(uuid4())
    batch_id = main.BATCH_MANAGER.create_batch(
        [
            {
                "task_id": task_id,
                "filename": "fake.mp4",
                "status": "PENDING",
                "error": None,
                "download_urls": None,
                "target_langs": ["English"],
            }
        ]
    )

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
