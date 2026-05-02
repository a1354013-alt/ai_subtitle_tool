import logging
import os
import re
import shutil
import subprocess
import uuid
import uuid as _uuid
import json
from pathlib import Path
from typing import Any, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from .models.status import TaskStatus as TaskStatusEnum
from .storage.task_history import TaskHistoryStore, duration_seconds_since
from .utils.task_control_utils import is_task_canceled, mark_task_canceled
from .utils.error_handler import handle_known_error, get_error_response
from .batch_manager import BatchManager, BatchTask, BatchMetadata
import zipfile

app = FastAPI(
    title="AI Video Subtitle Tool",
    version="1.0.0",
    description="Automated video subtitle generation with translation and editing capabilities.",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)
logger = logging.getLogger(__name__)


class _TestingAsyncResult:
    def __init__(self, status: str = "PENDING", info: Optional[dict] = None, result: Any = None):
        self.status = status
        self.info = info
        self.result = result

    def revoke(self, terminate: bool = False):
        return None


def _is_test_environment() -> bool:
    return os.getenv("PYTEST_CURRENT_TEST") is not None or os.getenv("TESTING", "").lower() == "true"


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
TASK_HISTORY = TaskHistoryStore(Path(UPLOAD_DIR) / "task_history.sqlite3")
BATCH_MANAGER = BatchManager(UPLOAD_DIR)


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
    if _is_test_environment():
        logger.info("Skipping Celery enqueue in test environment for task_id=%s", task_id)
        return

    try:
        from .tasks import process_video_task
    except Exception:
        logger.error("Task module unavailable; cannot enqueue process_video_task", exc_info=True)
        raise HTTPException(status_code=503, detail="Task worker unavailable")

    if hasattr(process_video_task, "apply_async"):
        process_video_task.apply_async(args=[file_path, options], task_id=task_id)
        return

    # Lightweight test environments may import undecorated task functions when Celery
    # is unavailable. Treat this as a no-op enqueue so API contract tests can still run.
    logger.warning("process_video_task has no apply_async; skipping enqueue for task_id=%s", task_id)


def _enqueue_rebuild_final_task(task_id: str, lang_suffix: str, subtitle_format: str) -> None:
    if _is_test_environment():
        logger.info("Skipping Celery rebuild enqueue in test environment for task_id=%s", task_id)
        return

    try:
        from .tasks import rebuild_final_video_task
    except Exception:
        logger.error("Task module unavailable; cannot enqueue rebuild_final_video_task", exc_info=True)
        raise HTTPException(status_code=503, detail="Task worker unavailable")

    if hasattr(rebuild_final_video_task, "apply_async"):
        rebuild_final_video_task.apply_async(args=[task_id, lang_suffix, subtitle_format], task_id=task_id)
        return

    logger.warning("rebuild_final_video_task has no apply_async; skipping enqueue for task_id=%s", task_id)


def _get_async_result(task_id: str):
    if _is_test_environment():
        return _TestingAsyncResult()

    from celery.result import AsyncResult

    from .celery_app import celery_app

    return AsyncResult(task_id, app=celery_app)


class TaskStatusResponse(BaseModel):
    task_id: str
    status: TaskStatusEnum
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
    task_status: TaskStatusEnum = Field(..., description="Task status at the time of manifest generation")
    has_video: bool
    subtitle_languages: List[str]
    available_files: List[FileInfo]
    warnings: List[str] = Field(default_factory=list)
    is_partial: bool = Field(False, description="True when task is SUCCESS but outputs are incomplete/missing")
    orphaned_files_detected: bool = Field(
        False, description="True when task is not SUCCESS but files with this task_id exist in uploads directory"
    )


class RecentTask(BaseModel):
    task_id: str
    filename: str
    status: str
    created_at: str
    duration_seconds: Optional[float] = None


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


def check_system_dependencies():
    """Check critical dependencies on startup."""
    from .utils.error_messages import ERROR_MESSAGES
    
    # 1. Check ffmpeg
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.error("CRITICAL: %s. Suggestion: %s", 
                     ERROR_MESSAGES["ffmpeg_not_found"]["message"], 
                     ERROR_MESSAGES["ffmpeg_not_found"]["suggestion"])

    # 2. Check OpenAI API Key
    if not os.getenv("OPENAI_API_KEY"):
        logger.error("CRITICAL: %s. Suggestion: %s", 
                     ERROR_MESSAGES["openai_api_key_missing"]["message"], 
                     ERROR_MESSAGES["openai_api_key_missing"]["suggestion"])

    # 3. Check Redis (best effort on startup)
    try:
        import redis as _redis
        r = _redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"), socket_connect_timeout=2)
        r.ping()
    except Exception:
        logger.error("CRITICAL: %s. Suggestion: %s", 
                     ERROR_MESSAGES["redis_not_running"]["message"], 
                     ERROR_MESSAGES["redis_not_running"]["suggestion"])

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    check_system_dependencies()
    yield

app.router.lifespan_context = lifespan

@app.get("/readyz")
async def readyz():
    from .utils.error_messages import ERROR_MESSAGES
    errors: list[dict] = []

    # Upload dir check
    try:
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        test_path = os.path.join(UPLOAD_DIR, ".readyz_write_test")
        with open(test_path, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(test_path)
    except Exception as e:
        errors.append({"code": "upload_dir_error", "message": f"UPLOAD_DIR not writable: {e}"})

    # Redis check
    try:
        import redis as _redis
        r = _redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"), socket_connect_timeout=2)
        r.ping()
    except Exception:
        errors.append({
            "code": "redis_not_running",
            "message": ERROR_MESSAGES["redis_not_running"]["message"],
            "suggestion": ERROR_MESSAGES["redis_not_running"]["suggestion"]
        })
        
    # ffmpeg check
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except Exception:
        errors.append({
            "code": "ffmpeg_not_found",
            "message": ERROR_MESSAGES["ffmpeg_not_found"]["message"],
            "suggestion": ERROR_MESSAGES["ffmpeg_not_found"]["suggestion"]
        })

    if errors:
        return JSONResponse(status_code=503, content={"status": "error", "errors": errors})
    return {"status": "ok"}


@app.post("/upload", response_model=TaskStatusResponse)
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
        
        error_code = handle_known_error(e)
        error_info = get_error_response(error_code)
        return JSONResponse(
            status_code=500 if error_code == "unknown_error" else 400,
            content={
                "success": False,
                "error_code": error_code,
                "message": error_info["message"],
                "suggestion": error_info["suggestion"]
            }
        )
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
        
        error_code = handle_known_error(e)
        error_info = get_error_response(error_code)
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error_code": error_code,
                "message": error_info["message"],
                "suggestion": error_info["suggestion"]
            }
        )

    # Store recent task history for product continuity.
    try:
        TASK_HISTORY.upsert_created(task_id=task_id, filename=file.filename, status=TaskStatusEnum.PENDING.value)
    except Exception:
        logger.warning("Failed to record task history (non-fatal)", exc_info=True)

    return TaskStatusResponse(task_id=task_id, status=TaskStatusEnum.PENDING, progress=0)


@app.get("/status/{task_id}", response_model=TaskStatusResponse)
async def get_status(task_id: str):
    task_id = validate_task_id(task_id)

    # Cancellation is an explicit user action; treat it as a terminal FAILURE from the API perspective.
    if is_task_canceled(UPLOAD_DIR, task_id):
        return TaskStatusResponse(
            task_id=task_id,
            status=TaskStatusEnum.FAILURE,
            progress=0,
            message="Canceled",
            result_url=None,
            warnings=[],
        )

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
        status = TaskStatusEnum.PROCESSING
    elif status == "SUCCESS":
        progress = 100
        message = "Completed"
        result_url = f"/results/{task_id}"
        if isinstance(task_result.result, dict):
            warnings.extend(task_result.result.get("warnings", []) or [])
        status = TaskStatusEnum.SUCCESS
    elif status == "FAILURE":
        # Extract structured error info if available
        result = task_result.result
        error_code = "unknown_error"
        suggestion = ""
        if isinstance(result, dict) and "error_code" in result:
            error_code = result["error_code"]
            message = result.get("message", str(result))
            suggestion = result.get("suggestion", "")
        else:
            error_code = handle_known_error(Exception(str(result)))
            error_info = get_error_response(error_code)
            message = error_info["message"]
            suggestion = error_info["suggestion"]
            
        status = TaskStatusEnum.FAILURE
        # Add suggestion to warnings or a separate field if needed, 
        # but for now we'll rely on the frontend to handle message/suggestion.
    elif status == "PENDING":
        message = "Waiting for worker..."
        status = TaskStatusEnum.PENDING
    else:
        # Any other Celery states are surfaced as PROCESSING for stability.
        status = TaskStatusEnum.PROCESSING

    # Best-effort status tracking for "Recent Tasks"
    try:
        duration = None
        if status in (TaskStatusEnum.SUCCESS, TaskStatusEnum.FAILURE):
            duration = duration_seconds_since(TASK_HISTORY.get_created_at(task_id))
        TASK_HISTORY.update_status(task_id=task_id, status=status.value, duration_seconds=duration)
    except Exception:
        logger.warning("Failed to update task history (non-fatal)", exc_info=True)

    return TaskStatusResponse(
        task_id=task_id,
        status=status,
        progress=progress,
        message=message,
        result_url=result_url,
        warnings=warnings,
    )


@app.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    task_id = validate_task_id(task_id)

    # Mark as canceled first so any polling becomes deterministic immediately.
    mark_task_canceled(UPLOAD_DIR, task_id)

    # Best-effort revoke; may not terminate a running task depending on worker settings.
    try:
        task_result = _get_async_result(task_id)
        task_result.revoke(terminate=False)
    except Exception:
        logger.warning("Failed to revoke task (non-fatal): %s", task_id, exc_info=True)

    return {"status": "canceled", "task_id": task_id}


@app.post("/tasks/{task_id}/rebuild-final")
async def rebuild_final(task_id: str, lang: str = Query(..., description="Language for subtitle"), format: str = Query("ass")):
    task_id = validate_task_id(task_id)
    lang_suffix = validate_lang(lang)
    subtitle_format = (format or "ass").lower()

    if subtitle_format not in ("ass", "srt"):
        raise HTTPException(status_code=400, detail="format must be 'ass' or 'srt'")

    _enqueue_rebuild_final_task(task_id=task_id, lang_suffix=lang_suffix, subtitle_format=subtitle_format)
    return {"status": "queued", "task_id": task_id}


@app.get("/tasks/recent", response_model=list[RecentTask])
async def get_recent_tasks():
    try:
        entries = TASK_HISTORY.list_recent(limit=20)
        return [RecentTask(**e.to_dict()) for e in entries]
    except Exception:
        logger.error("Failed to read task history", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to read task history")


class BatchUploadResponse(BaseModel):
    batch_id: str
    tasks: List[dict]

@app.post("/batch/upload", response_model=BatchUploadResponse)
async def batch_upload_videos(
    files: List[UploadFile] = File(...),
    target_langs: str = Form("Traditional Chinese", description="Comma separated languages"),
    burn_subtitles: bool = Form(True, description="Whether to burn subtitles into video"),
    subtitle_format: str = Form("ass", description="Subtitle format: ass or srt"),
    remove_silence: bool = Form(False, description="Remove silence from video"),
    parallel: bool = Form(True, description="Use parallel processing for long videos"),
):
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    tasks_info = []
    enqueue_jobs: List[dict[str, Any]] = []
    langs = normalize_target_langs(target_langs)
    
    for file in files:
        task_id = str(uuid.uuid4())
        file_extension = os.path.splitext(file.filename)[1]
        file_path = os.path.join(UPLOAD_DIR, f"{task_id}{file_extension}")
        
        # Basic validation similar to single upload
        if not file.filename.lower().endswith((".mp4", ".mkv", ".avi", ".mov")):
            tasks_info.append({"task_id": task_id, "filename": file.filename, "status": "failed", "error": "Unsupported format"})
            continue

        try:
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            options = {
                "business_id": task_id,
                "target_langs": langs,
                "burn_subtitles": burn_subtitles,
                "subtitle_format": subtitle_format,
                "remove_silence": remove_silence,
                "parallel": parallel,
                "hf_token": os.getenv("HF_TOKEN"),
            }

            enqueue_jobs.append(
                {
                    "task_id": task_id,
                    "file_path": file_path,
                    "filename": file.filename,
                    "options": options,
                }
            )
            tasks_info.append({"task_id": task_id, "filename": file.filename, "status": "queued"})
        except Exception as e:
            logger.error(f"Failed to process batch file {file.filename}: {e}")
            tasks_info.append({"task_id": task_id, "filename": file.filename, "status": "failed", "error": str(e)})
        finally:
            file.file.close()

    batch_id = BATCH_MANAGER.create_batch(tasks_info)

    for job in enqueue_jobs:
        try:
            _enqueue_process_video_task(job["file_path"], job["options"], job["task_id"])
            TASK_HISTORY.upsert_created(
                task_id=job["task_id"],
                filename=job["filename"],
                status=TaskStatusEnum.PENDING.value,
            )
        except Exception as e:
            logger.error("Failed to enqueue batch file %s: %s", job["filename"], e)
            for task in tasks_info:
                if task["task_id"] == job["task_id"]:
                    task["status"] = "failed"
                    task["error"] = str(e)
                    break
            BATCH_MANAGER.update_task_status(batch_id, job["task_id"], "failed", str(e))

    return BatchUploadResponse(batch_id=batch_id, tasks=tasks_info)

class BatchStatusResponse(BaseModel):
    batch_id: str
    total: int
    completed: int
    failed: int
    processing: int
    tasks: List[dict]

@app.get("/batch/{batch_id}/status", response_model=BatchStatusResponse)
async def get_batch_status(batch_id: str):
    batch = BATCH_MANAGER.get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    tasks_details = []
    completed = 0
    failed = 0
    processing = 0
    
    for task in batch.tasks:
        # Reuse existing get_status logic conceptually but more efficiently
        try:
            status_resp = await get_status(task.task_id)
            task_info = {
                "task_id": task.task_id,
                "filename": task.filename,
                "status": status_resp.status,
                "progress": status_resp.progress,
                "message": status_resp.message,
                "error": status_resp.message if status_resp.status == TaskStatusEnum.FAILURE else None,
                "download_urls": {
                    "srt": f"/results/{task.task_id}/download?format=srt",
                    "ass": f"/results/{task.task_id}/download?format=ass",
                    "video": f"/results/{task.task_id}/download?format=video"
                } if status_resp.status == TaskStatusEnum.SUCCESS else None
            }
            
            if status_resp.status == TaskStatusEnum.SUCCESS:
                completed += 1
            elif status_resp.status == TaskStatusEnum.FAILURE:
                failed += 1
            else:
                processing += 1
                
            tasks_details.append(task_info)
        except Exception:
            tasks_details.append({
                "task_id": task.task_id,
                "filename": task.filename,
                "status": "error",
                "progress": 0
            })
            failed += 1

    return BatchStatusResponse(
        batch_id=batch_id,
        total=len(batch.tasks),
        completed=completed,
        failed=failed,
        processing=processing,
        tasks=tasks_details
    )

@app.get("/batch/{batch_id}/download")
async def download_batch_zip(batch_id: str):
    batch = BATCH_MANAGER.get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    zip_filename = f"subtitle_batch_{batch_id}.zip"
    zip_path = os.path.join(UPLOAD_DIR, zip_filename)
    
    failed_tasks = []
    
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for task in batch.tasks:
            try:
                status_resp = await get_status(task.task_id)
            except Exception as e:
                failed_tasks.append({"task_id": task.task_id, "filename": task.filename, "error": str(e)})
                continue

            if status_resp.status == TaskStatusEnum.SUCCESS:
                # Add SRT, ASS, and final video
                for ext in ["srt", "ass"]:
                    # We need to find the actual file on disk. 
                    # Usually it's {task_id}_{lang}.{ext} or {task_id}.{ext}
                    # For simplicity, we'll look for any file starting with task_id and ending with ext
                    for f in os.listdir(UPLOAD_DIR):
                        if f.startswith(task.task_id) and f.endswith(f".{ext}"):
                            zipf.write(os.path.join(UPLOAD_DIR, f), arcname=f"{task.filename}_{f}")
                
                video_file = f"{task.task_id}_final.mp4"
                video_path = os.path.join(UPLOAD_DIR, video_file)
                if os.path.exists(video_path):
                    zipf.write(video_path, arcname=f"{task.filename}_final.mp4")
            elif status_resp.status == TaskStatusEnum.FAILURE:
                failed_tasks.append({
                    "task_id": task.task_id,
                    "filename": task.filename,
                    "error": status_resp.message
                })
        
        if failed_tasks:
            zipf.writestr("failed_tasks.json", json.dumps(failed_tasks, indent=2))
            
    return FileResponse(zip_path, media_type="application/zip", filename=zip_filename)

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
    if is_task_canceled(UPLOAD_DIR, task_id):
        task_status = TaskStatusEnum.FAILURE
    else:
        task_status = TaskStatusEnum.PROCESSING if status == "PROGRESS" else TaskStatusEnum(status) if status in TaskStatusEnum._value2member_map_ else TaskStatusEnum.PROCESSING

    # Detect orphaned files without exposing them as valid outputs.
    orphaned_files_detected = False
    try:
        for f in os.listdir(UPLOAD_DIR):
            if f.startswith(f"{task_id}_"):
                orphaned_files_detected = True
                break
    except OSError:
        logger.warning("Failed to list upload dir for orphan detection", exc_info=True)

    if task_status != TaskStatusEnum.SUCCESS:
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
    format: Optional[str] = Query(
        None, description="Subtitle format: 'ass', 'srt', or 'vtt'. Only used when lang is specified"
    ),
):
    task_id = validate_task_id(task_id)

    if format and format not in ("ass", "srt", "vtt"):
        raise HTTPException(status_code=400, detail="format must be 'ass', 'srt', or 'vtt'")

    if not lang:
        final_video = validate_path_traversal(os.path.join(UPLOAD_DIR, f"{task_id}_final.mp4"), UPLOAD_DIR)
        if os.path.exists(final_video):
            return FileResponse(final_video, filename=f"video_{task_id}.mp4")
        raise HTTPException(status_code=404, detail="Final video not found. Task may still be processing.")

    lang_suffix = validate_lang(lang)

    if format == "vtt":
        srt_path = validate_path_traversal(os.path.join(UPLOAD_DIR, f"{task_id}_{lang_suffix}.srt"), UPLOAD_DIR)
        if not os.path.exists(srt_path):
            raise HTTPException(status_code=404, detail=f"Subtitle 'srt' for language '{lang}' not found (required for vtt)")

        from .utils.subtitle_text_utils import srt_to_vtt

        with open(srt_path, "r", encoding="utf-8") as f:
            vtt = srt_to_vtt(f.read())

        filename = f"subtitle_{task_id}_{lang_suffix}.vtt"
        return Response(
            content=vtt,
            media_type="text/vtt; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    formats_to_try = [format] if format else ["ass", "srt"]
    for ext in formats_to_try:
        target_file = validate_path_traversal(os.path.join(UPLOAD_DIR, f"{task_id}_{lang_suffix}.{ext}"), UPLOAD_DIR)
        if os.path.exists(target_file):
            return FileResponse(target_file, filename=f"subtitle_{task_id}_{lang_suffix}.{ext}")

    if format:
        raise HTTPException(status_code=404, detail=f"Subtitle '{format}' for language '{lang}' not found")
    raise HTTPException(status_code=404, detail=f"Subtitle for language '{lang}' not found")


# Note: WebSocket status endpoint was removed as it was experimental and unused.
# The frontend uses polling for task status updates.
# If you need real-time updates, consider implementing a proper WebSocket solution with tests.


@app.get("/subtitle/{task_id}")
async def get_subtitle(
    task_id: str,
    lang: str = Query(..., description="Language for subtitle"),
    format: Optional[str] = Query(
        None,
        description="Subtitle format: 'ass', 'srt', or 'vtt'. If not specified, tries ass first, then srt",
    ),
):
    task_id = validate_task_id(task_id)
    lang_suffix = validate_lang(lang)

    if format and format not in ("ass", "srt", "vtt"):
        raise HTTPException(status_code=400, detail="format must be 'ass', 'srt', or 'vtt'")

    if format == "vtt":
        srt_path = validate_path_traversal(os.path.join(UPLOAD_DIR, f"{task_id}_{lang_suffix}.srt"), UPLOAD_DIR)
        if not os.path.exists(srt_path):
            raise HTTPException(status_code=404, detail=f"Subtitle 'srt' for language '{lang}' not found (required for vtt)")

        from .utils.subtitle_text_utils import srt_to_vtt

        with open(srt_path, "r", encoding="utf-8") as f:
            vtt = srt_to_vtt(f.read())
        filename = f"{task_id}_{lang_suffix}.vtt"
        return {"content": vtt, "format": "vtt", "filename": filename}

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
