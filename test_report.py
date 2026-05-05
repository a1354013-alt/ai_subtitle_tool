import os
import sys
from unittest.mock import MagicMock, patch

# 加入 backend 到 path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

from backend.services import report_service

def test_report_generation():
    print("Testing report data generation...")
    task_id = "test-task-id"
    task_status_info = {
        "status": "SUCCESS",
        "warnings": ["Test warning 1", "Test warning 2"],
        "message": "Completed"
    }
    
    # 模擬歷史記錄物件
    history_entry = MagicMock()
    history_entry.filename = "test_video.mp4"
    history_entry.duration_seconds = 123.45
    
    data = report_service.generate_report_data(task_id, task_status_info, history_entry)
    
    assert data["task_id"] == task_id
    assert data["filename"] == "test_video.mp4"
    assert data["status"] == "SUCCESS"
    assert data["elapsed_seconds"] == 123.45
    assert "Test warning 1" in data["warnings"]
    print("✓ Report data generation works")
    
    print("Testing markdown rendering...")
    md = report_service.render_markdown(data)
    assert "# Subtitle Processing Report" in md
    assert "test_video.mp4" in md
    assert "SUCCESS" in md
    assert "123.45s" in md
    assert "Test warning 1" in md
    print("✓ Markdown rendering works")
    print("\nRendered Markdown Example:\n")
    print(md)

if __name__ == "__main__":
    try:
        test_report_generation()
        print("\nAll report tests passed!")
    except Exception as e:
        print(f"\nTest failed: {e}")
        sys.exit(1)
