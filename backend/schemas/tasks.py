from typing import Optional

from pydantic import BaseModel, Field

from backend.models.status import TaskStatus as TaskStatusEnum


class TaskStatusResponse(BaseModel):
    task_id: str
    status: TaskStatusEnum
    progress: int
    message: Optional[str] = None
    result_url: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
    error_code: Optional[str] = None
    suggestion: Optional[str] = None


class RecentTask(BaseModel):
    task_id: str
    filename: str
    status: str
    created_at: str
    duration_seconds: Optional[float] = None

