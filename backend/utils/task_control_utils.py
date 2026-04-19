from __future__ import annotations

import os
from pathlib import Path


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

