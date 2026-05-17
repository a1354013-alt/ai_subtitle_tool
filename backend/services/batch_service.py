import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from backend.schemas.batch import BatchTaskDownloadUrls, BatchTaskResponse, SubtitleDownloadUrls
from backend.schemas.results import TaskResultManifest
from backend.services.upload_validation import sanitize_filename


def build_batch_task_response(task_id: str, filename: str, status: str, **kwargs: Any) -> BatchTaskResponse:
    return BatchTaskResponse(
        task_id=task_id,
        filename=filename,
        status=str(status).upper(),
        **kwargs,
    )


def model_dump(model: BaseModel, **kwargs: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(**kwargs)
    return model.dict(**kwargs)


def build_batch_download_urls(task_id: str, manifest: TaskResultManifest) -> BatchTaskDownloadUrls:
    subtitles: dict[str, SubtitleDownloadUrls] = {}
    for file_info in manifest.available_files:
        subtitle_urls = SubtitleDownloadUrls()
        display_name = file_info.display_name
        if file_info.srt:
            subtitle_urls.srt = f"/download/{task_id}?lang={display_name}&format=srt"
            subtitle_urls.vtt = f"/download/{task_id}?lang={display_name}&format=vtt"
        if file_info.ass:
            subtitle_urls.ass = f"/download/{task_id}?lang={display_name}&format=ass"
        if model_dump(subtitle_urls, exclude_none=True):
            subtitles[display_name] = subtitle_urls

    return BatchTaskDownloadUrls(
        video=f"/download/{task_id}" if manifest.has_video else None,
        subtitles=subtitles,
    )


def sanitize_archive_stem(filename: str) -> str:
    stem = Path(sanitize_filename(filename)).stem
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._")
    return normalized or "file"


def build_batch_archive_name(filename: str, task_id: str, extension: str, lang_suffix: str | None = None) -> str:
    ext = extension if extension.startswith(".") else f".{extension}"
    suffix = f"_{lang_suffix}" if lang_suffix else ""
    return f"{sanitize_archive_stem(filename)}_{task_id}{suffix}{ext}"

