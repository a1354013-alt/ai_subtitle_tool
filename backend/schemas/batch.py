from typing import Optional

from pydantic import BaseModel, Field


class SubtitleDownloadUrls(BaseModel):
    srt: Optional[str] = None
    ass: Optional[str] = None
    vtt: Optional[str] = None


class BatchTaskDownloadUrls(BaseModel):
    video: Optional[str] = None
    subtitles: dict[str, SubtitleDownloadUrls] = Field(default_factory=dict)


class BatchTaskResponse(BaseModel):
    task_id: str
    filename: str
    status: str
    progress: int = 0
    message: Optional[str] = None
    error: Optional[str] = None
    download_urls: Optional[BatchTaskDownloadUrls] = None


class BatchUploadResponse(BaseModel):
    batch_id: str
    tasks: list[BatchTaskResponse]


class BatchStatusResponse(BaseModel):
    batch_id: str
    total: int
    completed: int
    failed: int
    processing: int
    pending: int
    tasks: list[BatchTaskResponse]

