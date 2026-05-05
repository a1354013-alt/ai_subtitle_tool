from __future__ import annotations

import os
import re
from pathlib import Path
from typing import BinaryIO

from fastapi import HTTPException


SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov"}
SUPPORTED_SUBTITLE_FORMATS = {"ass", "srt"}


def sanitize_filename(filename: str | None) -> str:
    raw_name = Path(filename or "upload.bin").name.strip()
    if not raw_name:
        return "upload.bin"
    return re.sub(r"[\x00-\x1f]+", "_", raw_name)


def normalize_target_langs(raw: str) -> list[str]:
    parts = [re.sub(r"\s+", " ", p).strip() for p in (raw or "").split(",")]
    parts = [p for p in parts if p]

    seen: set[str] = set()
    normalized: list[str] = []
    for part in parts:
        key = part.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(part)
    return normalized


def validate_target_langs(raw: str) -> list[str]:
    langs = normalize_target_langs(raw)
    if not langs:
        raise HTTPException(status_code=400, detail="target_langs must contain at least one non-empty language")
    return langs


def validate_subtitle_format(subtitle_format: str) -> str:
    normalized = (subtitle_format or "").strip().lower()
    if normalized not in SUPPORTED_SUBTITLE_FORMATS:
        raise HTTPException(status_code=400, detail="subtitle_format must be 'ass' or 'srt'")
    return normalized


def validate_upload_metadata(filename: str | None, content_type: str | None) -> str:
    safe_name = sanitize_filename(filename)
    extension = Path(safe_name).suffix.lower()
    if extension not in SUPPORTED_VIDEO_EXTENSIONS:
        supported = ", ".join(ext.lstrip(".") for ext in sorted(SUPPORTED_VIDEO_EXTENSIONS))
        raise HTTPException(status_code=400, detail=f"Unsupported file format. Supported: {supported}")

    normalized_content_type = (content_type or "").lower()
    if normalized_content_type and not normalized_content_type.startswith("video/") and normalized_content_type != "application/octet-stream":
        raise HTTPException(status_code=400, detail=f"Invalid content type: {content_type}. Expected video/*")
    return safe_name


def validate_upload_size(file_obj: BinaryIO, max_upload_size_mb: int) -> int:
    file_obj.seek(0, os.SEEK_END)
    file_size = file_obj.tell()
    file_obj.seek(0)

    max_bytes = max_upload_size_mb * 1024 * 1024
    if file_size > max_bytes:
        raise HTTPException(status_code=413, detail=f"File too large. Maximum size: {max_upload_size_mb}MB")
    return file_size
