from __future__ import annotations

from unittest.mock import MagicMock

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
    assert data["translate_provider"] in {"openai", "none"}
    assert "Test warning 1" in data["warnings"]

    markdown = report_service.render_markdown(data)
    assert "# Subtitle Processing Report" in markdown
    assert "test_video.mp4" in markdown
    assert "SUCCESS" in markdown
    assert "123.45s" in markdown
    assert "Test warning 1" in markdown
