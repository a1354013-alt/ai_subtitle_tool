import json
import os
import uuid
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class BatchTask(BaseModel):
    task_id: str
    filename: str
    status: str
    error: Optional[str] = None

class BatchMetadata(BaseModel):
    batch_id: str
    created_at: str
    tasks: List[BatchTask]

class BatchManager:
    def __init__(self, storage_dir: str):
        self.storage_dir = Path(storage_dir)
        self.batches_dir = self.storage_dir / "batches"
        self.batches_dir.mkdir(parents=True, exist_ok=True)

    def _get_batch_path(self, batch_id: str) -> Path:
        return self.batches_dir / f"{batch_id}.json"

    @staticmethod
    def _normalize_status(status: str | None) -> str:
        normalized = str(status or "").strip().upper()
        if normalized == "QUEUED":
            return "PENDING"
        if normalized == "ERROR":
            return "FAILURE"
        if normalized in {"PENDING", "PROCESSING", "SUCCESS", "FAILURE"}:
            return normalized
        return "PENDING"

    def create_batch(self, tasks: List[Dict[str, Any]]) -> str:
        batch_id = f"batch_{uuid.uuid4().hex[:8]}"
        created_at = datetime.now(timezone.utc).isoformat()
        
        batch_tasks = [
            BatchTask(
                task_id=t["task_id"],
                filename=t["filename"],
                status=self._normalize_status(t.get("status")),
                error=t.get("error"),
            )
            for t in tasks
        ]
        
        metadata = BatchMetadata(
            batch_id=batch_id,
            created_at=created_at,
            tasks=batch_tasks
        )
        
        self._save_batch(metadata)
        return batch_id

    def _save_batch(self, metadata: BatchMetadata):
        path = self._get_batch_path(metadata.batch_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            # Use model_dump_json for Pydantic V2, fallback to json() for V1 if needed
            if hasattr(metadata, "model_dump_json"):
                f.write(metadata.model_dump_json(indent=2))
            else:
                f.write(metadata.json(indent=2))

    def get_batch(self, batch_id: str) -> Optional[BatchMetadata]:
        path = self._get_batch_path(batch_id)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return BatchMetadata(**data)
        except Exception as e:
            logger.error(f"Failed to load batch {batch_id}: {e}")
            return None

    def update_task_status(self, batch_id: str, task_id: str, status: str, error: Optional[str] = None):
        metadata = self.get_batch(batch_id)
        if not metadata:
            return
        
        for task in metadata.tasks:
            if task.task_id == task_id:
                task.status = self._normalize_status(status)
                if error is not None:
                    task.error = error
                break
        
        self._save_batch(metadata)
