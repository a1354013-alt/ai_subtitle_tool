from typing import Optional

from pydantic import BaseModel, Field

from backend.models.status import TaskStatus as TaskStatusEnum


class FileInfo(BaseModel):
    lang: str
    display_name: str
    ass: bool
    srt: bool
    vtt: bool = False
    translated: Optional[bool] = None
    fallback_reason: Optional[str] = None


class TranslationInfo(BaseModel):
    language: str
    translated: bool
    fallback_reason: Optional[str] = None


class TaskResultManifest(BaseModel):
    task_id: str
    task_status: TaskStatusEnum = Field(..., description="Task status at the time of manifest generation")
    has_video: bool
    subtitle_languages: list[str]
    available_files: list[FileInfo]
    warnings: list[str] = Field(default_factory=list)
    translations: list[TranslationInfo] = Field(default_factory=list)
    is_partial: bool = Field(False, description="True when task is SUCCESS but outputs are incomplete/missing")
    orphaned_files_detected: bool = Field(
        False, description="True when task is not SUCCESS but files with this task_id exist in uploads directory"
    )

