import os
import json
import pytest
from fastapi.testclient import TestClient
from backend.main import app, UPLOAD_DIR, BATCH_MANAGER
import shutil
from pathlib import Path

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_teardown():
    # Setup
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    yield
    # Teardown
    # shutil.rmtree(UPLOAD_DIR) # Be careful not to delete important files in dev

def test_batch_upload_basic():
    # Create dummy video files
    video1 = Path(UPLOAD_DIR) / "test1.mp4"
    video2 = Path(UPLOAD_DIR) / "test2.mp4"
    video1.write_bytes(b"dummy video 1 content")
    video2.write_bytes(b"dummy video 2 content")

    files = [
        ("files", ("test1.mp4", open(video1, "rb"), "video/mp4")),
        ("files", ("test2.mp4", open(video2, "rb"), "video/mp4")),
    ]
    
    response = client.post(
        "/batch/upload",
        files=files,
        data={"target_langs": "English", "burn_subtitles": "false"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "batch_id" in data
    assert len(data["tasks"]) == 2
    
    batch_id = data["batch_id"]
    batch_file = Path(UPLOAD_DIR) / "batches" / f"{batch_id}.json"
    assert batch_file.exists()

def test_batch_status():
    # Mock a batch
    tasks = [
        {"task_id": "task1", "filename": "v1.mp4", "status": "queued"},
        {"task_id": "task2", "filename": "v2.mp4", "status": "queued"}
    ]
    batch_id = BATCH_MANAGER.create_batch(tasks)
    
    response = client.get(f"/batch/{batch_id}/status")
    assert response.status_code == 200
    data = response.json()
    assert data["batch_id"] == batch_id
    assert data["total"] == 2
    assert len(data["tasks"]) == 2

def test_batch_download_zip():
    # This test is tricky because it depends on real task success
    # But we can test if it generates a ZIP even if empty/failed
    tasks = [{"task_id": "fake_task", "filename": "fake.mp4", "status": "queued"}]
    batch_id = BATCH_MANAGER.create_batch(tasks)
    
    response = client.get(f"/batch/{batch_id}/download")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    
    zip_path = Path(UPLOAD_DIR) / f"subtitle_batch_{batch_id}.zip"
    assert zip_path.exists()
