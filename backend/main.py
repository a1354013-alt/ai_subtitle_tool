import asyncio
import logging
import os
import re
import shutil
import subprocess
import uuid
import uuid as _uuid
from pathlib import Path
from typing import Any, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

app = FastAPI(title="AI Video Subtitle Tool")
logger = logging.getLogger(__name__)


def configure_cors() -> None:
    """Configure CORS with a predictable, safe policy."""
    allowed_origins_str = os.getenv("CORS_ALLOWED_ORIGINS", "*")
    allow_credentials = os.getenv("CORS_ALLOW_CREDENTIALS", "false").lower() == "true"

    origins = [o.strip() for o in allowed_origins_str.split(",") if o.strip()]

    # FastAPI/Starlette forbids '*' with credentials; keep this explicit and fail-fast.
    if "*" in origins and allow_credentials:
        raise ValueError(
            "Invalid CORS configuration: cannot use allow_origins=['*'] with allow_credentials=True. "
            "Either: (1) use explicit origin whitelist with credentials, or (2) use '*' without credentials."
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )


configure_cors()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.getenv("UPLOAD_DIR", os.path.join(BASE_DIR, "uploads"))
os.makedirs(UPLOAD_DIR, exist_ok=True)


def validate_task_id(task_id: str) -> str:
    try:
        uuid.UUID(task_id)
        return task_id
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid task_id format: {task_id}. Must be a valid UUID.")


def validate_lang(lang: str) -> str:
    """Validate lang and apply predictable normalization (trim + whitespace -> underscore)."""
    lang = (lang or "").strip()
    lang = re.sub(r"\s+", "_", lang)
    if not re.match(r"^[a-zA-Z0-9_-]+$", lang):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid lang format: '{lang}'. Only alphanumeric, underscore, and hyphen allowed.",
        )
    return lang


def normalize_target_langs(raw: str) -> List[str]:
    """
    Normalize multipart/form `target_langs`:
    - split by comma
    - trim
    - collapse internal whitespace
    - drop empty values (e.g. trailing comma)
    - de-duplicate while preserving original order (case-insensitive key)
    """
    raw = raw or ""
    parts = [re.sub(r"\s+", " ", p).strip() for p in raw.split(",")]
    parts = [p for p in parts if p]

    seen = set()
    out: List[str] = []
    for p in parts:
        k = p.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(p)
    return out


def validate_path_traversal(filepath: str, allowed_root: str) -> str:
    resolved_path = Path(filepath).resolve()
    resolved_root = Path(allowed_root).resolve()
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Path traversal detected: {filepath} is outside allowed directory.")
    return str(resolved_path)


def write_text_atomic(target_path: str, content: str) -> None:
    tmp_path = f"{target_path}.tmp.{_uuid.uuid4().hex}"
    try:
        with open(tmp_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, target_path)
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            logger.warning("Failed to remove temp file: %s", tmp_path, exc_info=True)


def _enqueue_process_video_task(file_path: str, options: dict, task_id: str) -> None:
    try:
        from .tasks import process_video_task
    except Exception:
        logger.error("Task module unavailable; cannot enqueue process_video_task", exc_info=True)
        raise HTTPException(status_code=503, detail="Task worker unavailable")

    process_video_task.apply_async(args=[file_path, options], task_id=task_id)


def _get_async_result(task_id: str):
    from celery.result import AsyncResult

    from .celery_app import celery_app

    return AsyncResult(task_id, app=celery_app)


class TaskStatus(BaseModel):
    task_id: str
    status: str
    progress: int
    message: Optional[str] = None
    result_url: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)


class SubtitleEditRequest(BaseModel):
    content: str
    format: str = Field(..., description="Target subtitle format: 'ass' or 'srt'")


class FileInfo(BaseModel):
    lang: str
    display_name: str
    ass: bool
    srt: bool


class TaskResultManifest(BaseModel):
    task_id: str
    task_status: str = Field(..., description="Task status at the time of manifest generation")
    has_video: bool
    subtitle_languages: List[str]
    available_files: List[FileInfo]
    warnings: List[str] = Field(default_factory=list)
    is_partial: bool = Field(False, description="True when task is SUCCESS but outputs are incomplete/missing")
    orphaned_files_detected: bool = Field(
        False, description="True when task is not SUCCESS but files with this task_id exist in uploads directory"
    )


@app.post("/upload", response_model=TaskStatus)
async def upload_video(
    file: UploadFile = File(...),
    target_langs: str = Form("Traditional Chinese", description="Comma separated languages"),
    burn_subtitles: bool = Form(True, description="Whether to burn subtitles into video"),
    subtitle_format: str = Form("ass", description="Subtitle format: ass or srt"),
    remove_silence: bool = Form(False, description="Remove silence from video"),
    parallel: bool = Form(True, description="Use parallel processing for long videos"),
):
    content_type = (file.content_type or "").lower()
    if content_type and (not content_type.startswith("video/")) and content_type != "application/octet-stream":
        raise HTTPException(status_code=400, detail=f"Invalid content type: {file.content_type}. Expected video/*")

    if not file.filename.lower().endswith((".mp4", ".mkv", ".avi", ".mov")):
        raise HTTPException(status_code=400, detail="Unsupported file format. Supported: mp4, mkv, avi, mov")

    if subtitle_format not in ("ass", "srt"):
        raise HTTPException(status_code=400, detail="subtitle_format must be 'ass' or 'srt'")

    task_id = str(uuid.uuid4())
    file_extension = os.path.splitext(file.filename)[1]
    file_path = os.path.join(UPLOAD_DIR, f"{task_id}{file_extension}")
    file_path = validate_path_traversal(file_path, UPLOAD_DIR)

    # size check (2GB)
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)
    max_file_size = 2 * 1024 * 1024 * 1024
    if file_size > max_file_size:
        raise HTTPException(status_code=413, detail="File too large. Maximum size: 2GB")

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except HTTPException:
        raise
    except Exception as e:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                logger.warning("Failed to remove partially uploaded file: %s", file_path, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
    finally:
        file.file.close()

    # ffprobe final validation
    try:
        ffprobe_result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_type",
                "-of",
                "csv=p=0",
                file_path,
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if ffprobe_result.returncode != 0 or "video" not in (ffprobe_result.stdout or ""):
            raise ValueError("Not a valid video file")
    except Exception as e:
        try:
            os.remove(file_path)
        except OSError:
            logger.warning("Failed to remove invalid uploaded file: %s", file_path, exc_info=True)
        raise HTTPException(status_code=400, detail=f"Invalid video file: {str(e)}")

    langs = normalize_target_langs(target_langs)
    if not langs:
        raise HTTPException(status_code=400, detail="target_langs must contain at least one non-empty language")

    options = {
        "business_id": task_id,
        "target_langs": langs,
        "burn_subtitles": burn_subtitles,
        "subtitle_format": subtitle_format,
        "remove_silence": remove_silence,
        "parallel": parallel,
        "hf_token": os.getenv("HF_TOKEN"),
    }

    try:
        _enqueue_process_video_task(file_path, options, task_id)
    except HTTPException:
        try:
            os.remove(file_path)
        except Exception:
            pass
        raise
    except Exception as e:
        try:
            os.remove(file_path)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Failed to enqueue task: {str(e)}")

    return TaskStatus(task_id=task_id, status="PENDING", progress=0)


@app.get("/status/{task_id}", response_model=TaskStatus)
async def get_status(task_id: str):
    task_id = validate_task_id(task_id)
    task_result = _get_async_result(task_id)

    status = task_result.status
    progress = 0
    message = ""
    result_url = None
    warnings: List[str] = []

    if status == "PROGRESS":
        info = task_result.info or {}
        if isinstance(info, dict):
            progress = int(info.get("progress", 0) or 0)
            message = str(info.get("status", "") or "")
            if "warnings" in info and isinstance(info["warnings"], list):
                warnings.extend(info["warnings"])
        status = "PROCESSING"
    elif status == "SUCCESS":
        progress = 100
        message = "Completed"
        result_url = f"/results/{task_id}"
        if isinstance(task_result.result, dict):
            warnings.extend(task_result.result.get("warnings", []) or [])
        status = "SUCCESS"
    elif status == "FAILURE":
        message = str(task_result.result)
        status = "FAILURE"
    elif status == "PENDING":
        message = "Waiting for worker..."
        status = "PENDING"

    return TaskStatus(
        task_id=task_id,
        status=status,
        progress=progress,
        message=message,
        result_url=result_url,
        warnings=warnings,
    )


@app.get("/results/{task_id}", response_model=TaskResultManifest)
async def get_results_manifest(task_id: str):
    task_id = validate_task_id(task_id)
    task_result = _get_async_result(task_id)

    warnings: List[str] = []
    if task_result.status == "SUCCESS" and isinstance(task_result.result, dict):
        warnings = task_result.result.get("warnings", []) or []
    elif task_result.status == "PROGRESS":
        info = task_result.info or {}
        if isinstance(info, dict) and "warnings" in info:
            warnings = list(info.get("warnings") or [])

    status = task_result.status
    task_status = "PROCESSING" if status == "PROGRESS" else status

    # Detect orphaned files without exposing them as valid outputs.
    orphaned_files_detected = False
    try:
        for f in os.listdir(UPLOAD_DIR):
            if f.startswith(f"{task_id}_"):
                orphaned_files_detected = True
                break
    except OSError:
        logger.warning("Failed to list upload dir for orphan detection", exc_info=True)

    if task_status != "SUCCESS":
        return TaskResultManifest(
            task_id=task_id,
            task_status=task_status,
            has_video=False,
            subtitle_languages=[],
            available_files=[],
            warnings=warnings,
            is_partial=False,
            orphaned_files_detected=orphaned_files_detected,
        )

    final_video_path = validate_path_traversal(os.path.join(UPLOAD_DIR, f"{task_id}_final.mp4"), UPLOAD_DIR)
    has_video = os.path.exists(final_video_path)

    files = sorted([f for f in os.listdir(UPLOAD_DIR) if f.startswith(f"{task_id}_")])
    lang_map: dict[str, dict[str, bool]] = {}
    for f in files:
        if not f.endswith((".ass", ".srt")):
            continue
        parts = f.replace(f"{task_id}_", "", 1).rsplit(".", 1)
        if len(parts) != 2:
            continue
        lang_suffix, ext = parts[0], parts[1]
        lang_map.setdefault(lang_suffix, {"ass": False, "srt": False})
        if ext in ("ass", "srt"):
            lang_map[lang_suffix][ext] = True

    available_files: List[FileInfo] = []
    for lang_suffix, exts in sorted(lang_map.items(), key=lambda kv: kv[0].lower()):
        display_name = lang_suffix.replace("_", " ")
        available_files.append(
            FileInfo(lang=lang_suffix, display_name=display_name, ass=exts["ass"], srt=exts["srt"])
        )

    return TaskResultManifest(
        task_id=task_id,
        task_status=task_status,
        has_video=has_video,
        subtitle_languages=[f.display_name for f in available_files],
        available_files=available_files,
        warnings=warnings,
        is_partial=(len(available_files) == 0),
        orphaned_files_detected=False,
    )


@app.get("/download/{task_id}")
async def download_result(
    task_id: str,
    lang: Optional[str] = Query(None, description="Language for subtitle (e.g. Traditional_Chinese)"),
    format: Optional[str] = Query(None, description="Subtitle format: 'ass' or 'srt'. Only used when lang is specified"),
):
    task_id = validate_task_id(task_id)

    if format and format not in ("ass", "srt"):
        raise HTTPException(status_code=400, detail="format must be 'ass' or 'srt'")

    if not lang:
        final_video = validate_path_traversal(os.path.join(UPLOAD_DIR, f"{task_id}_final.mp4"), UPLOAD_DIR)
        if os.path.exists(final_video):
            return FileResponse(final_video, filename=f"video_{task_id}.mp4")
        raise HTTPException(status_code=404, detail="Final video not found. Task may still be processing.")

    lang_suffix = validate_lang(lang)

    formats_to_try = [format] if format else ["ass", "srt"]
    for ext in formats_to_try:
        target_file = validate_path_traversal(os.path.join(UPLOAD_DIR, f"{task_id}_{lang_suffix}.{ext}"), UPLOAD_DIR)
        if os.path.exists(target_file):
            return FileResponse(target_file, filename=f"subtitle_{task_id}_{lang_suffix}.{ext}")

    if format:
        raise HTTPException(status_code=404, detail=f"Subtitle '{format}' for language '{lang}' not found")
    raise HTTPException(status_code=404, detail=f"Subtitle for language '{lang}' not found")


@app.websocket("/ws/status/{task_id}")
async def websocket_status(websocket: WebSocket, task_id: str):
    try:
        task_id = validate_task_id(task_id)
    except HTTPException:
        await websocket.close(code=4000, reason="Invalid task_id")
        return

    await websocket.accept()
    try:
        while True:
            res = await get_status(task_id)
            await websocket.send_json(res.dict())
            if res.status in ["SUCCESS", "FAILURE", "REVOKED"]:
                break
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass


@app.get("/subtitle/{task_id}")
async def get_subtitle(
    task_id: str,
    lang: str = Query(..., description="Language for subtitle"),
    format: Optional[str] = Query(
        None,
        description="Subtitle format: 'ass' or 'srt'. If not specified, tries ass first, then srt",
    ),
):
    task_id = validate_task_id(task_id)
    lang_suffix = validate_lang(lang)

    if format and format not in ("ass", "srt"):
        raise HTTPException(status_code=400, detail="format must be 'ass' or 'srt'")

    formats_to_try = [format] if format else ["ass", "srt"]
    for ext in formats_to_try:
        filename = f"{task_id}_{lang_suffix}.{ext}"
        path = validate_path_traversal(os.path.join(UPLOAD_DIR, filename), UPLOAD_DIR)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return {"content": f.read(), "format": ext, "filename": filename}

    if format:
        raise HTTPException(status_code=404, detail=f"Subtitle '{format}' for language '{lang}' not found")
    raise HTTPException(status_code=404, detail=f"Subtitle for language '{lang}' not found")


@app.put("/subtitle/{task_id}")
async def update_subtitle(task_id: str, edit: SubtitleEditRequest, lang: str = Query(..., description="Language for subtitle")):
    task_id = validate_task_id(task_id)
    lang_suffix = validate_lang(lang)
    target_format = (edit.format or "").lower()

    if target_format not in ("ass", "srt"):
        raise HTTPException(status_code=400, detail="Format must be 'ass' or 'srt'")

    filepath = validate_path_traversal(os.path.join(UPLOAD_DIR, f"{task_id}_{lang_suffix}.{target_format}"), UPLOAD_DIR)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail=f"Subtitle '{target_format}' for language '{lang}' not found")

    try:
        write_text_atomic(filepath, edit.content)
    except OSError:
        logger.error("Failed to write subtitle file: %s", filepath, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to write subtitle file")

    final_video_path = validate_path_traversal(os.path.join(UPLOAD_DIR, f"{task_id}_final.mp4"), UPLOAD_DIR)

    result = {
        "status": "updated",
        "format": target_format,
        "language": lang_suffix,
        "message": f"Successfully updated {target_format.upper()} subtitle for {lang_suffix}.",
        "warnings": [],
    }

    if os.path.exists(final_video_path):
        try:
            os.remove(final_video_path)
            result["warnings"].append(
                "Final video was deleted to prevent using old subtitles. "
                "Editing subtitles does not rebuild/burn the final video automatically."
            )
        except OSError:
            logger.warning("Failed to delete final video after subtitle update: %s", final_video_path, exc_info=True)
            result["warnings"].append("Subtitle updated but final video could not be deleted.")

    return result


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

