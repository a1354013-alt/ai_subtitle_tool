from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def cancel_marker_path(upload_dir: str, task_id: str) -> str:
    return str(Path(upload_dir) / f"{task_id}.cancel")


def mark_task_canceled(upload_dir: str, task_id: str) -> str:
    path = cancel_marker_path(upload_dir, task_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Atomic enough for our usage: write a small marker file.
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("canceled\n")
    return path


def is_task_canceled(upload_dir: str, task_id: str) -> bool:
    return os.path.exists(cancel_marker_path(upload_dir, task_id))


def build_task_failure_payload(error_code: str, message: str, suggestion: str) -> dict[str, str]:
    """Build a stable failure payload for task errors.
    
    This ensures consistent error response structure regardless of how the task fails.
    """
    return {
        "error_code": error_code,
        "message": message,
        "suggestion": suggestion,
    }


def write_task_error_artifact(task_id: str, upload_dir: str, error_payload: dict[str, str]) -> None:
    """Write error payload to a stable artifact file for later retrieval.
    
    This provides a fallback mechanism if Celery overrides the update_state meta.
    """
    error_path = Path(upload_dir) / f"{task_id}_error.json"
    import json
    try:
        with open(error_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(error_payload, f, ensure_ascii=False, indent=2)
    except Exception:
        pass  # Best effort - don't fail on error logging


def read_task_error_artifact(task_id: str, upload_dir: str) -> Optional[dict[str, str]]:
    """Read error payload from artifact file if available."""
    import json
    error_path = Path(upload_dir) / f"{task_id}_error.json"
    try:
        if error_path.exists():
            with open(error_path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return None

