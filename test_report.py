from __future__ import annotations

import subprocess
from unittest.mock import MagicMock

from backend import settings
from backend.services import report_service


def test_report_generation_and_markdown_rendering():
    task_id = "test-task-id"
    task_status_info = {
        "status": "SUCCESS",
        "warnings": ["Test warning 1", "Test warning 2"],
        "message": "Completed",
    }

    history_entry = MagicMock()
    history_entry.filename = "test_video.mp4"
    history_entry.duration_seconds = 123.45

    data = report_service.generate_report_data(task_id, task_status_info, history_entry)

    assert data["task_id"] == task_id
    assert data["filename"] == "test_video.mp4"
    assert data["status"] == "SUCCESS"
    assert data["elapsed_seconds"] == 123.45
    assert data["translate_provider"] in {"openai", "ollama", "none"}
    assert "Test warning 1" in data["warnings"]

    markdown = report_service.render_markdown(data)
    assert "# Subtitle Processing Report" in markdown
    assert "test_video.mp4" in markdown
    assert "SUCCESS" in markdown
    assert "123.45s" in markdown
    assert "Test warning 1" in markdown


def test_render_pdf_applies_timeout_and_preserves_stderr(monkeypatch):
    calls = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))
        raise subprocess.TimeoutExpired(
            cmd=args[0],
            timeout=kwargs["timeout"],
            stderr="converter stalled",
    )

    monkeypatch.setattr(report_service.subprocess, "run", fake_run)
    monkeypatch.setattr(settings, "REPORT_EXPORT_TIMEOUT_SECONDS", 3)

    try:
        report_service.render_pdf("# Demo")
    except RuntimeError as exc:
        assert "PDF conversion timed out after 3s" in str(exc)
        assert "converter stalled" in str(exc)
    else:
        raise AssertionError("render_pdf should raise when conversion times out")

    assert calls[0][1]["timeout"] == 3
