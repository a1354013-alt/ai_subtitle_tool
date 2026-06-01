import logging
import os
import shutil
import subprocess
import uuid
import json
from pathlib import Path
from typing import Any, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse, Response

from .models.status import TaskStatus as TaskStatusEnum
from .storage.task_history import TaskHistoryStore, duration_seconds_since
from .utils.task_control_utils import is_task_canceled, mark_task_canceled
from .utils.error_handler import handle_known_error, get_error_response
from .utils.storage_utils import get_storage_backend
from .services.upload_validation import (
    normalize_lang_suffix,
    validate_batch_files,
    normalize_target_langs,
    sanitize_filename,
    validate_subtitle_format,
    validate_target_langs,
    validate_upload_metadata,
    validate_upload_size,
)
from . import settings
from .batch_manager import BatchManager
from .core.paths import validate_path_traversal
from .schemas.batch import BatchStatusResponse, BatchTaskResponse, BatchUploadResponse
from .schemas.config import AppConfigResponse
from .schemas.results import FileInfo, TaskResultManifest, TranslationInfo
from .schemas.subtitles import SubtitleEditRequest
from .schemas.tasks import RecentTask, TaskStatusResponse
from .services.batch_service import (
    build_batch_archive_name as _build_batch_archive_name,
    build_batch_download_urls as _build_batch_download_urls,
    build_batch_task_response as _build_batch_task_response,
    model_dump as _model_dump,
)
from .services.file_service import write_text_atomic
from .services.subtitle_service import load_vtt_from_srt, write_vtt_for_srt_to_zip
import zipfile

app = FastAPI(
    title="AI Video Subtitle Tool",
    version="1.0.0",
    description="Automated video subtitle generation with translation and editing capabilities.",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)
logger = logging.getLogger(__name__)


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException):
    if isinstance(exc.detail, dict):
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


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
    origins = settings.get_cors_origins()
    allow_credentials = settings.CORS_ALLOW_CREDENTIALS

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

UPLOAD_DIR = settings.get_upload_dir()
OUTPUT_DIR = settings.get_output_dir()
TEMP_DIR = settings.get_temp_dir()
TASK_HISTORY = TaskHistoryStore(Path(UPLOAD_DIR) / "task_history.sqlite3")
BATCH_MANAGER = BatchManager(UPLOAD_DIR)
MAX_UPLOAD_SIZE_MB = settings.MAX_UPLOAD_SIZE_MB
MAX_BATCH_FILES = settings.MAX_BATCH_FILES


def validate_task_id(task_id: str) -> str:
    try:
        uuid.UUID(task_id)
        return task_id
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid task_id format: {task_id}. Must be a valid UUID.")


def validate_lang(lang: str) -> str:
    return normalize_lang_suffix(lang)


def _coerce_failure_payload(value: Any) -> dict[str, str]:
    if isinstance(value, dict) and value.get("error_code"):
        error_code = str(value["error_code"])
        return {
            "error_code": error_code,
            "message": str(value.get("message") or error_code),
            "suggestion": str(value.get("suggestion") or ""),
        }

    if isinstance(value, BaseException):
        fallback_source = value
    elif value is None:
        fallback_source = Exception("Task failed without error details")
    else:
        fallback_source = Exception(str(value))

    error_code = handle_known_error(fallback_source)
    error_info = get_error_response(error_code)
    return {
        "error_code": error_code,
        "message": str(error_info["message"]),
        "suggestion": str(error_info["suggestion"]),
    }


def _task_has_local_artifacts(task_id: str) -> bool:
    task_prefix = f"{task_id}_"
    for path in Path(UPLOAD_DIR).glob(f"{task_id}*"):
        if path.name == f"{task_id}.cancel":
            return True
        if path.name.startswith(task_prefix) or path.stem == task_id:
            return True
    return False


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
        # Determine queue based on video duration if available
        queue = "default"
        try:
            from moviepy.editor import VideoFileClip
            video = VideoFileClip(file_path)
            duration = video.duration
            video.close()
            if duration < 60:
                queue = "high_priority"
                logger.info("Routing task %s to high_priority queue (duration: %.2fs)", task_id, duration)
        except Exception as e:
            logger.warning("Failed to determine video duration for queue routing: %s", e)

        process_video_task.apply_async(args=[file_path, options], task_id=task_id, queue=queue)
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
        # Rebuild tasks are usually fast and user-triggered, so we put them in high_priority
        rebuild_final_video_task.apply_async(
            args=[task_id, lang_suffix, subtitle_format], task_id=task_id, queue="high_priority"
        )
        return

    logger.warning("rebuild_final_video_task has no apply_async; skipping enqueue for task_id=%s", task_id)


def _get_async_result(task_id: str):
    if _is_test_environment():
        return _TestingAsyncResult()

    from celery.result import AsyncResult

    from .celery_app import celery_app

    return AsyncResult(task_id, app=celery_app)


def _validate_uploaded_video_file(file: UploadFile) -> str:
    safe_filename = validate_upload_metadata(file.filename, file.content_type)
    validate_upload_size(file.file, MAX_UPLOAD_SIZE_MB)
    return safe_filename


def _validate_saved_video_file(file_path: str) -> None:
    ffprobe_result = subprocess.run(
        [
            settings.FFPROBE_BINARY,
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
    
    # Check video duration if in demo mode
    if settings.DEMO_MODE and settings.MAX_VIDEO_DURATION_MINUTES > 0:
        duration_result = subprocess.run(
            [
                settings.FFPROBE_BINARY,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                file_path,
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if duration_result.returncode == 0:
            try:
                duration_seconds = float(duration_result.stdout.strip())
            except (ValueError, TypeError) as e:
                logger.warning("Could not parse video duration: %s", e)
            else:
                max_seconds = settings.MAX_VIDEO_DURATION_MINUTES * 60
                if duration_seconds > max_seconds:
                    raise ValueError(
                        f"Video duration ({duration_seconds / 60:.1f} min) exceeds "
                        f"demo limit ({settings.MAX_VIDEO_DURATION_MINUTES} min)"
                    )


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/api/config", response_model=AppConfigResponse)
async def get_app_config():
    return AppConfigResponse(
        maxUploadSizeMb=settings.MAX_UPLOAD_SIZE_MB,
        maxBatchFiles=settings.MAX_BATCH_FILES,
        supportedExtensions=list(settings.SUPPORTED_VIDEO_EXTENSIONS),
        batchUploadEnabled=settings.BATCH_UPLOAD_ENABLED,
        subtitleFormats=list(settings.SUBTITLE_FORMATS),
        translationEnabled=bool(settings.OPENAI_API_KEY),
        openaiConfigured=bool(settings.OPENAI_API_KEY),
        defaultTargetLanguage="Traditional Chinese",
        availableModes=["transcribe"] + (["translate"] if settings.OPENAI_API_KEY else []),
    )


def check_system_dependencies():
    """Check critical dependencies on startup."""
    from .utils.error_messages import ERROR_MESSAGES
    
    # 1. Check ffmpeg
    try:
        subprocess.run([settings.FFMPEG_BINARY, "-version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.error("CRITICAL: %s. Suggestion: %s", 
                     ERROR_MESSAGES["ffmpeg_not_found"]["message"], 
                     ERROR_MESSAGES["ffmpeg_not_found"]["suggestion"])

    # 2. Check OpenAI API Key (required only when translation is requested)
    if not settings.OPENAI_API_KEY:
        logger.warning("%s. Suggestion: %s",
                       ERROR_MESSAGES["openai_api_key_missing"]["message"],
                       ERROR_MESSAGES["openai_api_key_missing"]["suggestion"])

    # 3. Check Redis (best effort on startup)
    try:
        import redis as _redis
        r = _redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
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
        r = _redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        r.ping()
    except Exception:
        errors.append({
            "code": "redis_not_running",
            "message": ERROR_MESSAGES["redis_not_running"]["message"],
            "suggestion": ERROR_MESSAGES["redis_not_running"]["suggestion"]
        })
        
    # ffmpeg check
    try:
        subprocess.run([settings.FFMPEG_BINARY, "-version"], capture_output=True, check=True)
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
    safe_filename = _validate_uploaded_video_file(file)
    langs = validate_target_langs(target_langs)
    normalized_subtitle_format = validate_subtitle_format(subtitle_format)

    # Check if translation is requested but not configured
    if len(langs) > 1 and not settings.OPENAI_API_KEY:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "openai_not_configured",
                "message": "Translation not available: OpenAI API Key is not configured.",
                "suggestion": "Set OPENAI_API_KEY in your .env file to enable translation, or request only original language subtitles."
            }
        )

    task_id = str(uuid.uuid4())
    file_extension = os.path.splitext(safe_filename)[1]
    file_path = str(settings.task_input_path(task_id, file_extension))
    file_path = validate_path_traversal(file_path, UPLOAD_DIR)

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

    try:
        _validate_saved_video_file(file_path)
    except Exception as e:
        try:
            os.remove(file_path)
        except OSError:
            logger.warning("Failed to remove invalid uploaded file: %s", file_path, exc_info=True)
        raise HTTPException(status_code=400, detail=f"Invalid video file: {str(e)}")

    options = {
        "business_id": task_id,
        "target_langs": langs,
        "burn_subtitles": burn_subtitles,
        "subtitle_format": normalized_subtitle_format,
        "remove_silence": remove_silence,
        "parallel": parallel,
        "hf_token": settings.HF_TOKEN,
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
        TASK_HISTORY.upsert_created(task_id=task_id, filename=safe_filename, status=TaskStatusEnum.PENDING.value)
    except Exception:
        logger.warning("Failed to record task history (non-fatal)", exc_info=True)

    return TaskStatusResponse(task_id=task_id, status=TaskStatusEnum.PENDING, progress=0)


@app.get("/status/{task_id}", response_model=TaskStatusResponse)
async def get_status(task_id: str):
    task_id = validate_task_id(task_id)

    if is_task_canceled(UPLOAD_DIR, task_id):
        return TaskStatusResponse(
            task_id=task_id,
            status=TaskStatusEnum.CANCELED,
            progress=0,
            message="Task canceled by user",
            result_url=None,
            warnings=[],
            error_code="task_canceled",
            suggestion="Restart the task if you still need subtitle generation for this file.",
        )

    task_result = _get_async_result(task_id)

    status = task_result.status
    progress = 0
    message = ""
    result_url = None
    warnings: List[str] = []
    error_code: Optional[str] = None
    suggestion: Optional[str] = None

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
        
        storage = get_storage_backend()
        # Try to get S3 URL first, fallback to local results page
        result_url = storage.get_url(f"{task_id}_final.mp4")
        if not result_url:
            result_url = f"/results/{task_id}"
            
        if isinstance(task_result.result, dict):
            warnings.extend(task_result.result.get("warnings", []) or [])
        status = TaskStatusEnum.SUCCESS
    elif status == "FAILURE":
        if isinstance(task_result.info, dict) and task_result.info.get("error_code"):
            failure_payload = _coerce_failure_payload(task_result.info)
        elif isinstance(task_result.result, dict) and task_result.result.get("error_code"):
            failure_payload = _coerce_failure_payload(task_result.result)
        else:
            fallback_value = task_result.result if task_result.result is not None else task_result.info
            failure_payload = _coerce_failure_payload(fallback_value)
        error_code = failure_payload["error_code"]
        message = failure_payload["message"]
        suggestion = failure_payload["suggestion"]
        status = TaskStatusEnum.FAILURE
    elif status == "PENDING":
        if TASK_HISTORY.get_created_at(task_id) is None and not _task_has_local_artifacts(task_id):
            error_info = get_error_response("task_not_found")
            raise HTTPException(
                status_code=404,
                detail={
                    "error_code": "task_not_found",
                    "message": error_info["message"],
                    "suggestion": error_info["suggestion"],
                },
            )
        message = "Waiting for worker..."
        status = TaskStatusEnum.PENDING
    else:
        # Any other Celery states are surfaced as PROCESSING for stability.
        status = TaskStatusEnum.PROCESSING

    # Best-effort status tracking for "Recent Tasks"
    try:
        duration = None
        if status in (TaskStatusEnum.SUCCESS, TaskStatusEnum.FAILURE, TaskStatusEnum.CANCELED):
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
        error_code=error_code,
        suggestion=suggestion,
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

    try:
        duration = duration_seconds_since(TASK_HISTORY.get_created_at(task_id))
        TASK_HISTORY.update_status(task_id=task_id, status=TaskStatusEnum.CANCELED.value, duration_seconds=duration)
    except Exception:
        logger.warning("Failed to record canceled status (non-fatal): %s", task_id, exc_info=True)

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


@app.post("/batch/upload", response_model=BatchUploadResponse)
async def batch_upload_videos(
    files: List[UploadFile] = File(...),
    target_langs: str = Form("Traditional Chinese", description="Comma separated languages"),
    burn_subtitles: bool = Form(True, description="Whether to burn subtitles into video"),
    subtitle_format: str = Form("ass", description="Subtitle format: ass or srt"),
    remove_silence: bool = Form(False, description="Remove silence from video"),
    parallel: bool = Form(True, description="Use parallel processing for long videos"),
):
    validate_batch_files(files, MAX_BATCH_FILES)

    langs = validate_target_langs(target_langs)
    normalized_subtitle_format = validate_subtitle_format(subtitle_format)
    
    # Check if translation is requested but not configured
    if len(langs) > 1 and not settings.OPENAI_API_KEY:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "openai_not_configured",
                "message": "Translation not available: OpenAI API Key is not configured.",
                "suggestion": "Set OPENAI_API_KEY in your .env file to enable translation, or request only original language subtitles."
            }
        )

    tasks_info: list[BatchTaskResponse] = []
    enqueue_jobs: List[dict[str, Any]] = []
    
    for file in files:
        task_id = str(uuid.uuid4())
        safe_filename = sanitize_filename(file.filename)
        file_extension = os.path.splitext(safe_filename)[1]
        file_path = str(settings.task_input_path(task_id, file_extension))

        try:
            _validate_uploaded_video_file(file)

            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            _validate_saved_video_file(file_path)

            options = {
                "business_id": task_id,
                "target_langs": langs,
                "burn_subtitles": burn_subtitles,
                "subtitle_format": normalized_subtitle_format,
                "remove_silence": remove_silence,
                "parallel": parallel,
                "hf_token": settings.HF_TOKEN,
            }

            enqueue_jobs.append(
                {
                    "task_id": task_id,
                    "file_path": file_path,
                    "filename": safe_filename,
                    "options": options,
                }
            )
            tasks_info.append(_build_batch_task_response(task_id, safe_filename, "PENDING"))
        except HTTPException as exc:
            tasks_info.append(_build_batch_task_response(task_id, safe_filename, "FAILURE", error=str(exc.detail)))
        except Exception as e:
            logger.error(f"Failed to process batch file {file.filename}: {e}")
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError:
                    logger.warning("Failed to remove invalid batch upload: %s", file_path, exc_info=True)
            tasks_info.append(_build_batch_task_response(task_id, safe_filename, "FAILURE", error=str(e)))
        finally:
            file.file.close()

    batch_id = BATCH_MANAGER.create_batch([_model_dump(task) for task in tasks_info])

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
                if task.task_id == job["task_id"]:
                    task.status = TaskStatusEnum.FAILURE.value
                    task.error = str(e)
                    break
            BATCH_MANAGER.update_task_status(batch_id, job["task_id"], TaskStatusEnum.FAILURE.value, str(e))

    return BatchUploadResponse(batch_id=batch_id, tasks=tasks_info)

@app.get("/batch/{batch_id}/status", response_model=BatchStatusResponse)
async def get_batch_status(batch_id: str):
    batch = BATCH_MANAGER.get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    tasks_details = []
    completed = 0
    failed = 0
    processing = 0
    pending = 0
    
    for task in batch.tasks:
        stored_status = str(task.status).upper()
        if stored_status == TaskStatusEnum.FAILURE.value:
            tasks_details.append(
                _build_batch_task_response(
                    task.task_id,
                    task.filename,
                    TaskStatusEnum.FAILURE.value,
                    error=task.error,
                    message=task.error,
                )
            )
            failed += 1
            continue

        try:
            status_resp = await get_status(task.task_id)
            task_info = _build_batch_task_response(
                task.task_id,
                task.filename,
                status_resp.status.value,
                progress=status_resp.progress,
                message=status_resp.message,
                error=status_resp.message if status_resp.status in (TaskStatusEnum.FAILURE, TaskStatusEnum.CANCELED) else None,
            )
            
            if status_resp.status == TaskStatusEnum.SUCCESS:
                manifest = await get_results_manifest(task.task_id)
                task_info.download_urls = _build_batch_download_urls(task.task_id, manifest)
                completed += 1
            elif status_resp.status == TaskStatusEnum.FAILURE:
                failed += 1
            elif status_resp.status == TaskStatusEnum.CANCELED:
                failed += 1
            elif status_resp.status == TaskStatusEnum.PENDING:
                pending += 1
            else:
                processing += 1
                
            tasks_details.append(task_info)
        except Exception:
            tasks_details.append(
                _build_batch_task_response(
                    task.task_id,
                    task.filename,
                    TaskStatusEnum.FAILURE.value,
                    error="Failed to load task status",
                    message="Failed to load task status",
                )
            )
            failed += 1

    return BatchStatusResponse(
        batch_id=batch_id,
        total=len(batch.tasks),
        completed=completed,
        failed=failed,
        processing=processing,
        pending=pending,
        tasks=tasks_details
    )


def _translation_info_from_result(result: Any) -> dict[str, TranslationInfo]:
    if not isinstance(result, dict):
        return {}
    raw_items = result.get("translations") or result.get("translation_metadata") or []
    translations: dict[str, TranslationInfo] = {}
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        language = str(item.get("language") or "").strip()
        if not language:
            continue
        try:
            lang_suffix = normalize_lang_suffix(language)
        except HTTPException:
            logger.warning("Skipping translation metadata with invalid language value: %s", language)
            continue
        translations[lang_suffix] = TranslationInfo(
            language=language,
            translated=bool(item.get("translated")),
            fallback_reason=item.get("fallback_reason"),
        )
    return translations

@app.get("/batch/{batch_id}/download")
async def download_batch_zip(batch_id: str):
    batch = BATCH_MANAGER.get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    zip_filename = f"subtitle_batch_{batch_id}.zip"
    zip_path = os.path.join(OUTPUT_DIR, zip_filename)
    
    failed_tasks = []
    
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zipf:
        for task in batch.tasks:
            try:
                status_resp = await get_status(task.task_id)
            except Exception as e:
                failed_tasks.append({"task_id": task.task_id, "filename": task.filename, "error": str(e)})
                continue

            if status_resp.status == TaskStatusEnum.SUCCESS:
                wrote_artifact = False
                for local_file in sorted(Path(UPLOAD_DIR).glob(f"{task.task_id}_*.srt")):
                    lang_suffix = local_file.stem.replace(f"{task.task_id}_", "", 1)
                    zipf.write(
                        local_file,
                        arcname=_build_batch_archive_name(task.filename, task.task_id, ".srt", lang_suffix),
                    )
                    wrote_artifact = True
                    write_vtt_for_srt_to_zip(
                        zipf,
                        local_file,
                        _build_batch_archive_name(task.filename, task.task_id, ".vtt", lang_suffix),
                    )
                    wrote_artifact = True
                for local_file in sorted(Path(UPLOAD_DIR).glob(f"{task.task_id}_*.ass")):
                    lang_suffix = local_file.stem.replace(f"{task.task_id}_", "", 1)
                    zipf.write(
                        local_file,
                        arcname=_build_batch_archive_name(task.filename, task.task_id, ".ass", lang_suffix),
                    )
                    wrote_artifact = True

                video_path = os.path.join(UPLOAD_DIR, f"{task.task_id}_final.mp4")
                if os.path.exists(video_path):
                    zipf.write(video_path, arcname=_build_batch_archive_name(task.filename, task.task_id, ".mp4"))
                    wrote_artifact = True
                if not wrote_artifact:
                    failed_tasks.append({
                        "task_id": task.task_id,
                        "filename": task.filename,
                        "error": "No subtitle or video artifacts found for completed task",
                    })
            elif status_resp.status in (TaskStatusEnum.FAILURE, TaskStatusEnum.CANCELED):
                failed_tasks.append({
                    "task_id": task.task_id,
                    "filename": task.filename,
                    "error": status_resp.message
                })
        
        if failed_tasks:
            zipf.writestr("failed_tasks.json", json.dumps(failed_tasks, indent=2))
            
    return FileResponse(zip_path, media_type="application/zip", filename=zip_filename)

@app.get("/results/{task_id}", response_model=TaskResultManifest, response_model_exclude_none=True)
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
        task_status = TaskStatusEnum.CANCELED
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
            translations=[],
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
    translations_by_lang = _translation_info_from_result(task_result.result)
    for lang_suffix, exts in sorted(lang_map.items(), key=lambda kv: kv[0].lower()):
        display_name = lang_suffix.replace("_", " ")
        translation_info = translations_by_lang.get(lang_suffix)
        available_files.append(
            FileInfo(
                lang=lang_suffix,
                display_name=display_name,
                ass=exts["ass"],
                srt=exts["srt"],
                translated=translation_info.translated if translation_info else None,
                fallback_reason=translation_info.fallback_reason if translation_info else None,
            )
        )

    return TaskResultManifest(
        task_id=task_id,
        task_status=task_status,
        has_video=has_video,
        subtitle_languages=[f.display_name for f in available_files],
        available_files=available_files,
        warnings=warnings,
        translations=list(translations_by_lang.values()),
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
        vtt = load_vtt_from_srt(UPLOAD_DIR, task_id, lang_suffix, lang)
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
        vtt = load_vtt_from_srt(UPLOAD_DIR, task_id, lang_suffix, lang)
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

    uvicorn.run(app, host=settings.API_HOST, port=settings.API_PORT)
