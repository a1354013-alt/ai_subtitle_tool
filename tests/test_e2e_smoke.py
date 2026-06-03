"""
E2E minimal smoke test: ensure core upload-to-result flow works.
Mocks heavy ML models but tests API contracts and file I/O.
"""
import json
import os
import re
import subprocess
from pathlib import Path

import httpx
import pytest


@pytest.fixture
def sample_video_file(tmp_path: Path) -> Path:
    """
    Generate a minimal valid MP4 file (< 1 sec) using ffmpeg.
    Falls back to raw bytes if ffmpeg unavailable.
    """
    output = tmp_path / "sample.mp4"
    
    # Try ffmpeg first
    try:
        subprocess.run(
            [
                "ffmpeg", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=1",
                "-f", "lavfi", "-i", "sine=f=440:d=1",
                "-pix_fmt", "yuv420p", "-y", str(output)
            ],
            capture_output=True,
            timeout=10
        )
        if output.exists() and output.stat().st_size > 0:
            return output
    except Exception:
        pass
    
    # Fallback: return a minimal valid MP4 structure (can be validated by ffprobe)
    # This is an actual minimal MP4 file (ftypisom + mdat atoms)
    minimal_mp4 = bytes.fromhex(
        "0000002066747970697370206f0000020000697370" +
        "6f6d6973cf004200000000000000000000000000" +
        "0000002c6d646174000000000000000000000000" +
        "0000000000000000000000000000000000000000"
    )
    output.write_bytes(minimal_mp4)
    return output


@pytest.mark.anyio
async def test_e2e_upload_config_translation_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sample_video_file: Path
):
    """
    Test that /api/config reports translation state and upload respects it.
    """
    import importlib
    from types import SimpleNamespace
    
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("OPENAI_API_KEY", "")  # Explicitly disabled
    monkeypatch.setenv("TESTING", "true")
    
    import backend.main as main
    importlib.reload(main)
    
    # Stub subprocess for ffprobe
    def _fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout="video\naudio\n", stderr="")
    monkeypatch.setattr(main.subprocess, "run", _fake_run)
    monkeypatch.setattr(main, "_enqueue_process_video_task", lambda *a, **k: None)
    
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Verify config reports translation disabled
        r_config = await client.get("/api/config")
        assert r_config.status_code == 200
        config = r_config.json()
        assert config["translationEnabled"] is False
        assert config["openaiConfigured"] is False
        assert "transcribe" in config["availableModes"]
        assert "translate" not in config["availableModes"]
        
        # 2. Try to upload with multiple target languages (implicitly requesting translation)
        with open(sample_video_file, "rb") as f:
            r_upload = await client.post(
                "/upload",
                files={"file": ("test.mp4", f, "video/mp4")},
                data={
                    "target_langs": "Traditional Chinese, English",  # Multiple langs = translation needed
                    "burn_subtitles": "true",
                    "subtitle_format": "srt",
                    "remove_silence": "false",
                    "parallel": "false",
                },
            )
        
        # 3. Should fail with clear error
        assert r_upload.status_code == 400, r_upload.text
        error_body = r_upload.json()
        assert error_body["error_code"] == "openai_not_configured"
        assert "OpenAI" in error_body["message"] or "translation" in error_body["message"].lower()


@pytest.mark.anyio
async def test_e2e_single_language_works_without_openai(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sample_video_file: Path
):
    """
    Test that transcribe-only mode (single language) works without OpenAI.
    """
    import importlib
    from types import SimpleNamespace
    import re as re_module
    
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("OPENAI_API_KEY", "")  # Explicitly disabled
    monkeypatch.setenv("TESTING", "true")
    
    import backend.main as main
    importlib.reload(main)
    
    def _fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout="video\naudio\n", stderr="")
    monkeypatch.setattr(main.subprocess, "run", _fake_run)
    monkeypatch.setattr(main, "_enqueue_process_video_task", lambda *a, **k: None)
    
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Single language upload should succeed
        with open(sample_video_file, "rb") as f:
            r_upload = await client.post(
                "/upload",
                files={"file": ("test.mp4", f, "video/mp4")},
                data={
                    "target_langs": "Original",  # Single language = no translation needed
                    "burn_subtitles": "true",
                    "subtitle_format": "srt",
                    "remove_silence": "false",
                    "parallel": "false",
                },
            )
        
        assert r_upload.status_code == 200, r_upload.text
        body = r_upload.json()
        assert body["status"] == "PENDING"
        assert re_module.match(r"^[0-9a-fA-F-]{36}$", body["task_id"])


@pytest.mark.anyio
async def test_e2e_batch_upload_respects_translation_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sample_video_file: Path
):
    """
    Test that batch upload also enforces translation config check.
    """
    import importlib
    from types import SimpleNamespace
    
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("TESTING", "true")
    
    import backend.main as main
    importlib.reload(main)
    
    def _fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout="video\naudio\n", stderr="")
    monkeypatch.setattr(main.subprocess, "run", _fake_run)
    monkeypatch.setattr(main, "_enqueue_process_video_task", lambda *a, **k: None)
    
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Batch upload with translation request should fail
        with open(sample_video_file, "rb") as f:
            r_batch = await client.post(
                "/batch/upload",
                files=[("files", ("test.mp4", f, "video/mp4"))],
                data={
                    "target_langs": "Traditional Chinese, English",
                    "burn_subtitles": "true",
                    "subtitle_format": "srt",
                    "remove_silence": "false",
                    "parallel": "false",
                },
            )
        
        assert r_batch.status_code == 400, r_batch.text
        error_body = r_batch.json()
        assert error_body["error_code"] == "openai_not_configured"


@pytest.mark.anyio
async def test_e2e_upload_invalid_video_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """
    Test that invalid video files are rejected at upload time.
    """
    import importlib
    from types import SimpleNamespace
    
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("TESTING", "true")
    
    import backend.main as main
    importlib.reload(main)
    
    def _fake_run(*args, **kwargs):
        # Simulate ffprobe saying "not a video"
        return SimpleNamespace(returncode=1, stdout="", stderr="not a video")
    monkeypatch.setattr(main.subprocess, "run", _fake_run)
    
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Upload invalid bytes
        r = await client.post(
            "/upload",
            files={"file": ("bad.mp4", b"not a video", "video/mp4")},
            data={
                "target_langs": "Original",
                "burn_subtitles": "true",
                "subtitle_format": "srt",
                "remove_silence": "false",
                "parallel": "false",
            },
        )
        
        assert r.status_code == 400
        body = r.json()
        assert body.get("error_code") or "Invalid" in body.get("detail", "")
