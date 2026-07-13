import logging
import os
import shutil
import uuid
import json
import time
import base64
import hashlib
import hmac
from collections import deque
from pathlib import Path
from typing import Any, List, Optional
from urllib.parse import parse_qsl, urlencode

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from .models.status import TaskStatus as TaskStatusEnum
from .storage.task_history import TaskHistoryStore, duration_seconds_since
from .utils.task_control_utils import is_task_canceled, mark_task_canceled, read_task_error_artifact
from .utils.error_handler import handle_known_error, get_error_response
from .utils.media_process import MediaProcessError, run_media_command
from .utils.storage_utils import get_storage_backend
from .utils.translate_utils import translation_targets_requested
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
from .batch_manager import BatchManager, InvalidBatchIdError
from .core.paths import validate_path_traversal
from .schemas.batch import BatchStatusResponse, BatchTaskResponse, BatchUploadResponse
from .schemas.config import AppCapabilitiesResponse, AppConfigResponse
from .schemas.results import FileInfo, TaskResultManifest, TranslationInfo
from .schemas.subtitles import SubtitleEditRequest
from .schemas.tasks import RecentTask, TaskStatusResponse
from .services.batch_service import (
    build_batch_archive_name as _build_batch_archive_name,
    build_batch_download_urls as _build_batch_download_urls,
    build_batch_task_response as _build_batch_task_response,
    model_dump as _model_dump,
)
from .services.llm_capabilities import (
    OLLAMA_UNAVAILABLE_MESSAGE,
    OPENAI_TRANSLATION_REQUIRED_MESSAGE,
    TRANSLATION_DISABLED_MESSAGE,
    ensure_translation_available,
    get_llm_capability_status,
)
from .services.file_service import write_text_atomic
from .services.subtitle_service import load_vtt_from_srt, write_vtt_for_srt_to_zip
from .services.subtitle_validation import SubtitleValidationError, validate_subtitle_content
import zipfile

def _is_production_environment() -> bool:
    return (settings.ENVIRONMENT or "").strip().lower() == "production"


def _docs_path(path: str) -> str | None:
    return None if _is_production_environment() else path


def _project_version() -> str:
    version_path = Path(__file__).resolve().parents[1] / "VERSION"
    try:
        return version_path.read_text(encoding="utf-8").strip() or "0.0.0"
    except OSError:
        return "0.0.0"


app = FastAPI(
    title="AI Video Subtitle Tool",
    version=_project_version(),
    description="Automated video subtitle generation with translation and editing capabilities.",
    docs_url=_docs_path("/docs"),
    redoc_url=_docs_path("/redoc"),
    openapi_url=_docs_path("/openapi.json"),
)
logger = logging.getLogger(__name__)
_RATE_LIMIT_BUCKETS: dict[str, deque[float]] = {}
AUTH_EXEMPT_PATHS = {"/healthz", "/readyz", "/openapi.json", "/docs", "/redoc"}
RATE_LIMIT_EXEMPT_PREFIXES = ("/status/",)
DOWNLOAD_TICKET_PATHS = ("/download/",)


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


def _download_ticket_secret() -> bytes:
    configured = (settings.AUTH_TOKEN or "").strip()
    if configured:
        return configured.encode("utf-8")
    return b"development-download-ticket-secret"


def _canonical_download_path(path: str, query_params: dict[str, str]) -> str:
    filtered = {k: v for k, v in query_params.items() if k != "ticket"}
    query = urlencode(sorted(filtered.items()))
    return f"{path}?{query}" if query else path


def _sign_download_ticket(canonical_path: str, expires_at: int) -> str:
    payload = f"{expires_at}:{canonical_path}".encode("utf-8")
    digest = hmac.new(_download_ticket_secret(), payload, hashlib.sha256).digest()
    raw = f"{expires_at}:".encode("utf-8") + digest
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _verify_download_ticket(canonical_path: str, ticket: str | None) -> bool:
    if not ticket:
        return False
    try:
        padded = ticket + "=" * (-len(ticket) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        expires_raw, digest = raw.split(b":", 1)
        expires_at = int(expires_raw.decode("ascii"))
    except Exception:
        return False
    if expires_at < int(time.time()):
        return False
    expected = hmac.new(
        _download_ticket_secret(),
        f"{expires_at}:{canonical_path}".encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return hmac.compare_digest(digest, expected)


def _request_has_valid_download_ticket(request: Request) -> bool:
    path = request.url.path
    if not (path.startswith(DOWNLOAD_TICKET_PATHS) or (path.startswith("/batch/") and path.endswith("/download"))):
        return False
    canonical_path = _canonical_download_path(path, dict(request.query_params))
    return _verify_download_ticket(canonical_path, request.query_params.get("ticket"))


def _persist_task_state(
    task_id: str,
    status: TaskStatusEnum | str,
    *,
    progress: Optional[int] = None,
    message: Optional[str] = None,
    warnings: Optional[list[str]] = None,
    error_code: Optional[str] = None,
    suggestion: Optional[str] = None,
    result_task_id: Optional[str] = None,
    duration_seconds: Optional[float] = None,
) -> None:
    normalized = status.value if isinstance(status, TaskStatusEnum) else str(status)
    try:
        if duration_seconds is None and normalized in {"SUCCESS", "FAILURE", "CANCELED"}:
            duration_seconds = duration_seconds_since(TASK_HISTORY.get_created_at(task_id))
        TASK_HISTORY.update_status(
            task_id=task_id,
            status=normalized,
            duration_seconds=duration_seconds,
            progress=progress,
            message=message,
            warnings=warnings,
            error_code=error_code,
            suggestion=suggestion,
            result_task_id=result_task_id,
        )
    except Exception:
        logger.warning("Failed to persist task state: %s", task_id, exc_info=True)


def _ensure_openai_configured_for_targets(target_langs: list[str]) -> None:
    if not translation_targets_requested(target_langs):
        return
    try:
        ensure_translation_available(target_langs)
    except ValueError as exc:
        message = str(exc)
        error_code = "translation_unavailable"
        suggestion = "Request only original language subtitles, or configure the selected LLM provider."
        if message == OPENAI_TRANSLATION_REQUIRED_MESSAGE:
            error_code = "openai_not_configured"
            suggestion = "Set OPENAI_API_KEY in your .env file to enable OpenAI translation, or request only original language subtitles."
        elif message == OLLAMA_UNAVAILABLE_MESSAGE:
            error_code = "ollama_unavailable"
            suggestion = "Start Ollama and confirm OLLAMA_BASE_URL and OLLAMA_MODEL are correct."
        elif message == TRANSLATION_DISABLED_MESSAGE:
            error_code = "translation_disabled"
            suggestion = "Set LLM_PROVIDER to ollama or openai to enable translation, or request only original language subtitles."
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": error_code,
                "message": message,
                "suggestion": suggestion,
            },
        )


def _is_rate_limit_exempt_path(path: str) -> bool:
    if any(path.startswith(prefix) for prefix in RATE_LIMIT_EXEMPT_PREFIXES):
        return True
    return path.startswith("/batch/") and path.endswith("/status")


def _capability_response_payload() -> dict[str, Any]:
    status = get_llm_capability_status()
    return {
        "provider": status.provider,
        "model": status.model,
        "translationEnabled": status.translation_enabled,
        "reason": status.reason,
        "message": status.message,
        "defaultTargetLanguage": status.default_target_language,
        "availableModes": status.available_modes,
        "openaiConfigured": status.openai_configured,
    }


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


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    path = request.url.path
    if path not in AUTH_EXEMPT_PATHS:
        if settings.REQUIRE_AUTH_TOKEN:
            configured = (settings.AUTH_TOKEN or "").strip()
            auth_header = request.headers.get("Authorization", "")
            bearer = auth_header[7:].strip() if auth_header.lower().startswith("bearer ") else ""
            header_token = request.headers.get("X-API-Token", "").strip()
            ticket_ok = _request_has_valid_download_ticket(request)
            if not configured or (bearer != configured and header_token != configured) and not ticket_ok:
                return JSONResponse(status_code=401, content={"detail": "Invalid or missing API token"})

        if settings.RATE_LIMIT_PER_IP > 0 and not _is_rate_limit_exempt_path(path):
            client_ip = request.client.host if request.client else "unknown"
            now = time.time()
            bucket = _RATE_LIMIT_BUCKETS.setdefault(client_ip, deque())
            while bucket and now - bucket[0] >= 3600:
                bucket.popleft()
            if len(bucket) >= settings.RATE_LIMIT_PER_IP:
                return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})
            bucket.append(now)

    return await call_next(request)

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


def _failure_payload_from_artifact(task_id: str) -> Optional[dict[str, str]]:
    payload = read_task_error_artifact(task_id, UPLOAD_DIR)
    if payload is None:
        return None
    return _coerce_failure_payload(payload)


def _task_has_local_artifacts(task_id: str) -> bool:
    task_prefix = f"{task_id}_"
    for path in Path(UPLOAD_DIR).glob(f"{task_id}*"):
        if path.name == f"{task_id}.cancel":
            return True
        if path.name.startswith(task_prefix) or path.stem == task_id:
            return True
    return False


def _check_upload_dir_writable() -> None:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    test_path = os.path.join(UPLOAD_DIR, ".readyz_write_test")
    with open(test_path, "w", encoding="utf-8") as f:
        f.write("ok")
    os.remove(test_path)


def _check_redis_ready() -> None:
    import redis as _redis

    r = _redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
    r.ping()


def _check_ffmpeg_ready() -> None:
    run_media_command([settings.FFMPEG_BINARY, "-version"], timeout=settings.FFMPEG_TIMEOUT_SECONDS, check=True)


def _read_text_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _success_result_url(result_task_id: str) -> str:
    storage = get_storage_backend()
    result_url = storage.get_url(f"{result_task_id}_final.mp4")
    return result_url or f"/results/{result_task_id}"


def _response_from_history(task_id: str, entry) -> TaskStatusResponse:
    status = TaskStatusEnum(entry.status) if entry.status in TaskStatusEnum._value2member_map_ else TaskStatusEnum.PENDING
    result_task_id = entry.result_task_id
    result_url = _success_result_url(result_task_id or task_id) if status == TaskStatusEnum.SUCCESS else None
    message = entry.message or ("Waiting for worker..." if status == TaskStatusEnum.PENDING else None)
    return TaskStatusResponse(
        task_id=task_id,
        status=status,
        progress=entry.progress,
        message=message,
        result_url=result_url,
        result_task_id=result_task_id,
        warnings=entry.warnings,
        error_code=entry.error_code,
        suggestion=entry.suggestion,
    )


def _response_from_local_artifacts(task_id: str) -> Optional[TaskStatusResponse]:
    has_video, available_files = _scan_task_artifacts(task_id)
    if not has_video:
        return None
    return TaskStatusResponse(
        task_id=task_id,
        status=TaskStatusEnum.SUCCESS,
        progress=100,
        message="Completed",
        result_url=_success_result_url(task_id),
        warnings=[],
    )


def _resolve_task_state(task_id: str) -> TaskStatusResponse:
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
    celery_status = task_result.status

    if celery_status == "PROGRESS":
        info = task_result.info or {}
        progress = 0
        message = ""
        warnings: list[str] = []
        result_task_id = None
        if isinstance(info, dict):
            progress = int(info.get("progress", 0) or 0)
            message = str(info.get("status", "") or info.get("message", "") or "")
            if isinstance(info.get("warnings"), list):
                warnings = list(info["warnings"])
            if info.get("result_task_id"):
                result_task_id = validate_task_id(str(info["result_task_id"]))
        return TaskStatusResponse(
            task_id=task_id,
            status=TaskStatusEnum.PROCESSING,
            progress=progress,
            message=message,
            result_task_id=result_task_id,
            warnings=warnings,
        )

    if celery_status == "SUCCESS":
        warnings: list[str] = []
        result_task_id = None
        if isinstance(task_result.result, dict):
            raw_result_task_id = task_result.result.get("result_task_id")
            if raw_result_task_id:
                result_task_id = validate_task_id(str(raw_result_task_id))
            warnings = list(task_result.result.get("warnings", []) or [])
        result_owner_task_id = result_task_id or task_id
        return TaskStatusResponse(
            task_id=task_id,
            status=TaskStatusEnum.SUCCESS,
            progress=100,
            message="Completed",
            result_url=_success_result_url(result_owner_task_id),
            result_task_id=result_task_id,
            warnings=warnings,
        )

    if celery_status in {"FAILURE", "REVOKED"}:
        if isinstance(task_result.info, dict) and task_result.info.get("error_code"):
            failure_payload = _coerce_failure_payload(task_result.info)
        elif isinstance(task_result.result, dict) and task_result.result.get("error_code"):
            failure_payload = _coerce_failure_payload(task_result.result)
        elif _failure_payload_from_artifact(task_id):
            failure_payload = _failure_payload_from_artifact(task_id) or {}
        else:
            fallback = "Task was revoked" if celery_status == "REVOKED" else task_result.result or task_result.info
            failure_payload = _coerce_failure_payload(fallback)
        return TaskStatusResponse(
            task_id=task_id,
            status=TaskStatusEnum.FAILURE,
            progress=0,
            message=failure_payload["message"],
            warnings=[],
            error_code=failure_payload["error_code"],
            suggestion=failure_payload["suggestion"],
        )

    if celery_status != "PENDING":
        return TaskStatusResponse(
            task_id=task_id,
            status=TaskStatusEnum.PROCESSING,
            progress=0,
            message=str(celery_status or "Processing"),
            warnings=[],
        )

    persisted = TASK_HISTORY.get(task_id)
    if persisted and persisted.status in {
        TaskStatusEnum.SUCCESS.value,
        TaskStatusEnum.FAILURE.value,
        TaskStatusEnum.CANCELED.value,
        TaskStatusEnum.PROCESSING.value,
        TaskStatusEnum.PENDING.value,
    }:
        return _response_from_history(task_id, persisted)

    artifact_payload = _failure_payload_from_artifact(task_id)
    if artifact_payload:
        return TaskStatusResponse(
            task_id=task_id,
            status=TaskStatusEnum.FAILURE,
            progress=0,
            message=artifact_payload["message"],
            warnings=[],
            error_code=artifact_payload["error_code"],
            suggestion=artifact_payload["suggestion"],
        )

    if local_response := _response_from_local_artifacts(task_id):
        return local_response

    if _task_has_local_artifacts(task_id):
        return TaskStatusResponse(
            task_id=task_id,
            status=TaskStatusEnum.PENDING,
            progress=0,
            message="Waiting for worker...",
            warnings=[],
        )

    error_info = get_error_response("task_not_found")
    raise HTTPException(
        status_code=404,
        detail={
            "error_code": "task_not_found",
            "message": error_info["message"],
            "suggestion": error_info["suggestion"],
        },
    )


def _mark_enqueue_failure(task_id: str, exc: Exception) -> None:
    error_code = "enqueue_failed"
    message = f"Failed to enqueue task: {exc}"
    suggestion = "Confirm Redis and Celery are running, then retry the upload."
    try:
        TASK_HISTORY.update_status(
            task_id=task_id,
            status=TaskStatusEnum.FAILURE.value,
            progress=0,
            message=message,
            warnings=[],
            error_code=error_code,
            suggestion=suggestion,
        )
    except Exception:
        logger.warning("Failed to mark enqueue failure: %s", task_id, exc_info=True)


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
        queue = "transcription"
        try:
            from moviepy.editor import VideoFileClip
            video = VideoFileClip(file_path)
            duration = video.duration
            video.close()
            if duration < 60:
                queue = "transcription"
                logger.info("Routing task %s to transcription queue (duration: %.2fs)", task_id, duration)
        except Exception as e:
            logger.warning("Failed to determine video duration for queue routing: %s", e)

        process_video_task.apply_async(args=[file_path, options], task_id=task_id, queue=queue)
        return

    # Lightweight test environments may import undecorated task functions when Celery
    # is unavailable. Treat this as a no-op enqueue so API contract tests can still run.
    logger.warning("process_video_task has no apply_async; skipping enqueue for task_id=%s", task_id)


def _enqueue_rebuild_final_task(
    task_id: str, lang_suffix: str, subtitle_format: str, rebuild_task_id: str | None = None
) -> str:
    rebuild_task_id = rebuild_task_id or str(uuid.uuid4())
    if _is_test_environment():
        logger.info("Skipping Celery rebuild enqueue in test environment for task_id=%s", task_id)
        return rebuild_task_id

    try:
        from .tasks import rebuild_final_video_task
    except Exception:
        logger.error("Task module unavailable; cannot enqueue rebuild_final_video_task", exc_info=True)
        raise HTTPException(status_code=503, detail="Task worker unavailable")

    if hasattr(rebuild_final_video_task, "apply_async"):
        rebuild_final_video_task.apply_async(
            args=[task_id, lang_suffix, subtitle_format], task_id=rebuild_task_id, queue="rebuild"
        )
        return rebuild_task_id

    logger.warning("rebuild_final_video_task has no apply_async; skipping enqueue for task_id=%s", task_id)
    return rebuild_task_id


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


def _uploaded_file_size(file: UploadFile) -> int:
    current = file.file.tell()
    file.file.seek(0, os.SEEK_END)
    size = file.file.tell()
    file.file.seek(current)
    return size


def _validate_saved_video_file(file_path: str) -> None:
    ffprobe_result = run_media_command(
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
        timeout=settings.FFPROBE_TIMEOUT_SECONDS,
    )
    if ffprobe_result.returncode != 0 or "video" not in (ffprobe_result.stdout or ""):
        raise ValueError("Not a valid video file")

    audio_result = run_media_command(
        [
            settings.FFPROBE_BINARY,
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "csv=p=0",
            file_path,
        ],
        timeout=settings.FFPROBE_TIMEOUT_SECONDS,
    )
    if audio_result.returncode != 0 or "audio" not in (audio_result.stdout or ""):
        raise ValueError("Video file does not contain an audio stream")
    
    # Check video duration if in demo mode
    if settings.DEMO_MODE and settings.MAX_VIDEO_DURATION_MINUTES > 0:
        duration_result = run_media_command(
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
            timeout=settings.FFPROBE_TIMEOUT_SECONDS,
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
    capabilities = _capability_response_payload()
    return AppConfigResponse(
        version=_project_version(),
        maxUploadSizeMb=settings.MAX_UPLOAD_SIZE_MB,
        maxBatchFiles=settings.MAX_BATCH_FILES,
        supportedExtensions=list(settings.SUPPORTED_VIDEO_EXTENSIONS),
        batchUploadEnabled=settings.BATCH_UPLOAD_ENABLED,
        subtitleFormats=list(settings.SUBTITLE_FORMATS),
        translationEnabled=capabilities["translationEnabled"],
        openaiConfigured=capabilities["openaiConfigured"],
        defaultTargetLanguage=capabilities["defaultTargetLanguage"],
        availableModes=capabilities["availableModes"],
        provider=capabilities["provider"],
        model=capabilities["model"],
        reason=capabilities["reason"],
        message=capabilities["message"],
    )


@app.get("/api/capabilities", response_model=AppCapabilitiesResponse)
async def get_app_capabilities():
    return AppCapabilitiesResponse(**_capability_response_payload())


@app.get("/download-ticket")
async def create_download_ticket(path: str = Query(..., description="Download path beginning with /download/ or /batch/")):
    path_part, _, query = path.partition("?")
    if not (path_part.startswith("/download/") or (path_part.startswith("/batch/") and path_part.endswith("/download"))):
        raise HTTPException(status_code=400, detail="Download tickets can only be issued for download paths")
    query_params = dict(parse_qsl(query, keep_blank_values=True))
    canonical_path = _canonical_download_path(path_part, query_params)
    expires_at = int(time.time()) + settings.DOWNLOAD_TICKET_TTL_SECONDS
    ticket = _sign_download_ticket(canonical_path, expires_at)
    separator = "&" if "?" in path else "?"
    return {"url": f"{path}{separator}ticket={ticket}", "expires_at": expires_at}


def check_system_dependencies():
    """Check critical dependencies on startup."""
    from .utils.error_messages import ERROR_MESSAGES

    if settings.ENVIRONMENT.lower() == "production":
        if settings.REQUIRE_AUTH_TOKEN and not settings.AUTH_TOKEN:
            raise RuntimeError("REQUIRE_AUTH_TOKEN=true requires AUTH_TOKEN in production.")
        if not settings.REQUIRE_AUTH_TOKEN:
            logger.warning("Production is running without REQUIRE_AUTH_TOKEN=true.")
    
    production = _is_production_environment()

    # 1. Check ffmpeg
    try:
        run_media_command([settings.FFMPEG_BINARY, "-version"], timeout=settings.FFMPEG_TIMEOUT_SECONDS, check=True)
    except (MediaProcessError, FileNotFoundError):
        log = logger.error if production else logger.warning
        prefix = "CRITICAL: " if production else "Development warning: "
        log("%s%s. Suggestion: %s",
            prefix,
            ERROR_MESSAGES["ffmpeg_not_found"]["message"],
            ERROR_MESSAGES["ffmpeg_not_found"]["suggestion"])

    # 2. Check translation provider (warn only; do not block general startup)
    llm_status = get_llm_capability_status()
    if not llm_status.translation_enabled and llm_status.message:
        if llm_status.provider == "openai":
            logger.warning(
                "%s. Suggestion: %s",
                ERROR_MESSAGES["openai_api_key_missing"]["message"],
                ERROR_MESSAGES["openai_api_key_missing"]["suggestion"],
            )
        elif llm_status.provider == "ollama":
            logger.warning(
                "%s. Suggestion: Confirm OLLAMA_BASE_URL=%s and that the Ollama service is running.",
                llm_status.message,
                settings.OLLAMA_BASE_URL,
            )

    # 3. Check Redis (best effort on startup)
    try:
        import redis as _redis
        r = _redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        r.ping()
    except Exception:
        log = logger.error if production else logger.warning
        prefix = "CRITICAL: " if production else "Development warning: "
        log("%s%s. Suggestion: %s",
            prefix,
            ERROR_MESSAGES["redis_not_running"]["message"],
            ERROR_MESSAGES["redis_not_running"]["suggestion"])

    # 4. Check configured subtitle font (best effort outside production)
    font_status = _check_subtitle_font()
    if not font_status["available"]:
        log = logger.error if production else logger.warning
        log(
            "Configured subtitle font could not be resolved: %s. Detail: %s",
            settings.SUBTITLE_FONT_NAME,
            font_status["detail"],
        )


def _check_subtitle_font() -> dict[str, Any]:
    requested_family = settings.SUBTITLE_FONT_NAME
    try:
        import subprocess

        result = subprocess.run(
            ["fc-match", "-f", "%{family}\n%{file}\n", requested_family],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except FileNotFoundError:
        return {
            "font": requested_family,
            "requested_family": requested_family,
            "resolved_family": None,
            "resolved_file": None,
            "exact_match": False,
            "available": False,
            "detail": "fontconfig fc-match is not installed",
        }
    except Exception as exc:
        return {
            "font": requested_family,
            "requested_family": requested_family,
            "resolved_family": None,
            "resolved_file": None,
            "exact_match": False,
            "available": False,
            "detail": str(exc),
        }

    output = (result.stdout or "").strip()
    if result.returncode != 0 or not output:
        return {
            "font": requested_family,
            "requested_family": requested_family,
            "resolved_family": None,
            "resolved_file": None,
            "exact_match": False,
            "available": False,
            "detail": result.stderr.strip() or "fc-match returned no match",
        }
    lines = output.splitlines()
    resolved_family = lines[0].strip() if lines else ""
    resolved_file = lines[1].strip() if len(lines) > 1 else ""
    requested = requested_family.casefold().strip()
    resolved_names = [item.casefold().strip() for item in resolved_family.split(",")]
    exact_match = requested in resolved_names
    detail = output if exact_match else f"fc-match resolved '{requested_family}' to '{resolved_family}'"
    return {
        "font": requested_family,
        "requested_family": requested_family,
        "resolved_family": resolved_family,
        "resolved_file": resolved_file or None,
        "exact_match": exact_match,
        "available": exact_match,
        "detail": detail,
    }

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
        await run_in_threadpool(_check_upload_dir_writable)
    except Exception as e:
        errors.append({"code": "upload_dir_error", "message": f"UPLOAD_DIR not writable: {e}"})

    # Redis check
    try:
        await run_in_threadpool(_check_redis_ready)
    except Exception:
        errors.append({
            "code": "redis_not_running",
            "message": ERROR_MESSAGES["redis_not_running"]["message"],
            "suggestion": ERROR_MESSAGES["redis_not_running"]["suggestion"]
        })
        
    # ffmpeg check
    try:
        await run_in_threadpool(_check_ffmpeg_ready)
    except Exception:
        errors.append({
            "code": "ffmpeg_not_found",
            "message": ERROR_MESSAGES["ffmpeg_not_found"]["message"],
            "suggestion": ERROR_MESSAGES["ffmpeg_not_found"]["suggestion"]
        })

    font_status = await run_in_threadpool(_check_subtitle_font)
    if not font_status["available"]:
        errors.append({
            "code": "subtitle_font_unavailable",
            "message": f"Configured subtitle font is unavailable: {settings.SUBTITLE_FONT_NAME}",
            "suggestion": "Install fontconfig and a CJK-capable font package, or set SUBTITLE_FONT_NAME to an installed font.",
            "detail": font_status["detail"],
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

    _ensure_openai_configured_for_targets(langs)

    task_id = str(uuid.uuid4())
    file_extension = os.path.splitext(safe_filename)[1]
    file_path = str(settings.task_input_path(task_id, file_extension))
    file_path = validate_path_traversal(file_path, UPLOAD_DIR)

    try:
        with open(file_path, "wb") as buffer:
            await run_in_threadpool(shutil.copyfileobj, file.file, buffer)
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
        await run_in_threadpool(_validate_saved_video_file, file_path)
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
        TASK_HISTORY.upsert_created(task_id=task_id, filename=safe_filename, status=TaskStatusEnum.PENDING.value)
    except Exception:
        logger.error("Failed to record task history before enqueue: %s", task_id, exc_info=True)
        try:
            os.remove(file_path)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Failed to record task history") from None

    try:
        await run_in_threadpool(_enqueue_process_video_task, file_path, options, task_id)
    except HTTPException as exc:
        _mark_enqueue_failure(task_id, exc)
        raise
    except Exception as e:
        _mark_enqueue_failure(task_id, e)
        raise HTTPException(status_code=503, detail="Failed to enqueue task") from None

    return TaskStatusResponse(task_id=task_id, status=TaskStatusEnum.PENDING, progress=0)


@app.get("/status/{task_id}", response_model=TaskStatusResponse)
async def get_status(task_id: str):
    task_id = validate_task_id(task_id)
    response = await run_in_threadpool(_resolve_task_state, task_id)

    # Best-effort status tracking for "Recent Tasks"
    await run_in_threadpool(
        _persist_task_state,
        task_id,
        response.status,
        progress=response.progress,
        message=response.message,
        warnings=response.warnings,
        error_code=response.error_code,
        suggestion=response.suggestion,
        result_task_id=response.result_task_id,
    )
    return response


@app.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    task_id = validate_task_id(task_id)
    has_known_task = await run_in_threadpool(lambda: TASK_HISTORY.get(task_id) is not None or _task_has_local_artifacts(task_id))
    if not has_known_task:
        error_info = get_error_response("task_not_found")
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "task_not_found",
                "message": error_info["message"],
                "suggestion": error_info["suggestion"],
            },
        )

    # Mark as canceled first so any polling becomes deterministic immediately.
    await run_in_threadpool(mark_task_canceled, UPLOAD_DIR, task_id)

    # Best-effort revoke; may not terminate a running task depending on worker settings.
    try:
        task_result = await run_in_threadpool(_get_async_result, task_id)
        await run_in_threadpool(task_result.revoke, terminate=False)
    except Exception:
        logger.warning("Failed to revoke task (non-fatal): %s", task_id, exc_info=True)

    await run_in_threadpool(
        _persist_task_state,
        task_id,
        TaskStatusEnum.CANCELED,
        progress=0,
        message="Task canceled by user",
        warnings=[],
        error_code="task_canceled",
        suggestion="Restart the task if you still need subtitle generation for this file.",
    )

    return {"status": "canceled", "task_id": task_id}


@app.post("/tasks/{task_id}/rebuild-final")
async def rebuild_final(task_id: str, lang: str = Query(..., description="Language for subtitle"), format: str = Query("ass")):
    task_id = validate_task_id(task_id)
    lang_suffix = validate_lang(lang)
    subtitle_format = (format or "ass").lower()

    if subtitle_format not in ("ass", "srt"):
        raise HTTPException(status_code=400, detail="format must be 'ass' or 'srt'")

    rebuild_task_id = str(uuid.uuid4())
    try:
        await run_in_threadpool(
            TASK_HISTORY.upsert_created,
            task_id=rebuild_task_id,
            filename=f"Rebuild final video for {task_id}",
            status=TaskStatusEnum.PENDING.value,
        )
    except Exception:
        logger.error("Failed to record rebuild task history before enqueue: %s", rebuild_task_id, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to record rebuild task history") from None

    try:
        await run_in_threadpool(
            _enqueue_rebuild_final_task,
            task_id=task_id,
            lang_suffix=lang_suffix,
            subtitle_format=subtitle_format,
            rebuild_task_id=rebuild_task_id,
        )
    except HTTPException:
        try:
            await run_in_threadpool(TASK_HISTORY.update_status, task_id=rebuild_task_id, status=TaskStatusEnum.FAILURE.value)
        except Exception:
            logger.warning("Failed to mark rebuild task history as failed: %s", rebuild_task_id, exc_info=True)
        raise
    except Exception:
        logger.error("Failed to enqueue rebuild task: %s", rebuild_task_id, exc_info=True)
        try:
            await run_in_threadpool(TASK_HISTORY.update_status, task_id=rebuild_task_id, status=TaskStatusEnum.FAILURE.value)
        except Exception:
            logger.warning("Failed to mark rebuild task history as failed: %s", rebuild_task_id, exc_info=True)
        raise HTTPException(status_code=503, detail="Failed to enqueue rebuild task") from None

    return {"status": "queued", "task_id": task_id, "rebuild_task_id": rebuild_task_id}


@app.get("/tasks/recent", response_model=list[RecentTask])
async def get_recent_tasks():
    try:
        entries = await run_in_threadpool(TASK_HISTORY.list_recent, limit=20)
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
    total_size = sum(_uploaded_file_size(file) for file in files)
    max_total_bytes = settings.MAX_BATCH_TOTAL_SIZE_MB * 1024 * 1024
    if total_size > max_total_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Combined batch size exceeds MAX_BATCH_TOTAL_SIZE_MB={settings.MAX_BATCH_TOTAL_SIZE_MB}",
        )

    langs = validate_target_langs(target_langs)
    normalized_subtitle_format = validate_subtitle_format(subtitle_format)
    
    _ensure_openai_configured_for_targets(langs)

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
                await run_in_threadpool(shutil.copyfileobj, file.file, buffer)
            await run_in_threadpool(_validate_saved_video_file, file_path)

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
            TASK_HISTORY.upsert_created(
                task_id=job["task_id"],
                filename=job["filename"],
                status=TaskStatusEnum.PENDING.value,
            )
            await run_in_threadpool(_enqueue_process_video_task, job["file_path"], job["options"], job["task_id"])
        except Exception as e:
            logger.error("Failed to enqueue batch file %s: %s", job["filename"], e)
            _mark_enqueue_failure(job["task_id"], e)
            for task in tasks_info:
                if task.task_id == job["task_id"]:
                    task.status = TaskStatusEnum.FAILURE.value
                    task.error = str(e)
                    break
            BATCH_MANAGER.update_task_status(batch_id, job["task_id"], TaskStatusEnum.FAILURE.value, str(e))

    return BatchUploadResponse(batch_id=batch_id, tasks=tasks_info)

@app.get("/batch/{batch_id}/status", response_model=BatchStatusResponse)
async def get_batch_status(batch_id: str):
    try:
        batch = await run_in_threadpool(BATCH_MANAGER.get_batch, batch_id)
    except InvalidBatchIdError:
        raise HTTPException(status_code=400, detail="Invalid batch_id format") from None
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


def _scan_task_artifacts(task_id: str) -> tuple[bool, list[FileInfo]]:
    final_video_path = validate_path_traversal(os.path.join(UPLOAD_DIR, f"{task_id}_final.mp4"), UPLOAD_DIR)
    has_video = os.path.exists(final_video_path)

    lang_map: dict[str, dict[str, bool]] = {}
    try:
        files = sorted(f for f in os.listdir(UPLOAD_DIR) if f.startswith(f"{task_id}_"))
    except OSError:
        logger.warning("Failed to list upload dir for results manifest", exc_info=True)
        files = []

    for filename in files:
        if not filename.endswith((".ass", ".srt")):
            continue
        parts = filename.replace(f"{task_id}_", "", 1).rsplit(".", 1)
        if len(parts) != 2:
            continue
        lang_suffix, ext = parts[0], parts[1]
        lang_map.setdefault(lang_suffix, {"ass": False, "srt": False})
        lang_map[lang_suffix][ext] = True

    return has_video, [
        FileInfo(
            lang=lang_suffix,
            display_name=lang_suffix.replace("_", " "),
            ass=exts["ass"],
            srt=exts["srt"],
            vtt=exts["srt"],
        )
        for lang_suffix, exts in sorted(lang_map.items(), key=lambda kv: kv[0].lower())
    ]


def _build_batch_zip_file(batch, zip_path: str) -> None:
    tmp_path = f"{zip_path}.tmp-{uuid.uuid4().hex}"
    failed_tasks = []

    try:
        with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as zipf:
            for task in batch.tasks:
                try:
                    status_resp = _resolve_task_state(task.task_id)
                except Exception as e:
                    failed_tasks.append({"task_id": task.task_id, "filename": task.filename, "error": str(e)})
                    continue

                result_owner_task_id = status_resp.result_task_id or task.task_id
                if status_resp.status == TaskStatusEnum.SUCCESS:
                    wrote_artifact = False
                    for local_file in sorted(Path(UPLOAD_DIR).glob(f"{result_owner_task_id}_*.srt")):
                        lang_suffix = local_file.stem.replace(f"{result_owner_task_id}_", "", 1)
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
                    for local_file in sorted(Path(UPLOAD_DIR).glob(f"{result_owner_task_id}_*.ass")):
                        lang_suffix = local_file.stem.replace(f"{result_owner_task_id}_", "", 1)
                        zipf.write(
                            local_file,
                            arcname=_build_batch_archive_name(task.filename, task.task_id, ".ass", lang_suffix),
                        )
                        wrote_artifact = True

                    video_path = os.path.join(UPLOAD_DIR, f"{result_owner_task_id}_final.mp4")
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
                        "error": status_resp.message,
                    })

            if failed_tasks:
                zipf.writestr("failed_tasks.json", json.dumps(failed_tasks, indent=2))
        os.replace(tmp_path, zip_path)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                logger.warning("Failed to remove partial batch ZIP: %s", tmp_path, exc_info=True)


@app.get("/batch/{batch_id}/download")
async def download_batch_zip(batch_id: str):
    try:
        batch = await run_in_threadpool(BATCH_MANAGER.get_batch, batch_id)
    except InvalidBatchIdError:
        raise HTTPException(status_code=400, detail="Invalid batch_id format") from None
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    zip_filename = f"subtitle_batch_{batch_id}.zip"
    zip_path = os.path.join(OUTPUT_DIR, zip_filename)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    await run_in_threadpool(_build_batch_zip_file, batch, zip_path)
            
    return FileResponse(zip_path, media_type="application/zip", filename=zip_filename)

@app.get("/results/{task_id}", response_model=TaskResultManifest, response_model_exclude_none=True)
async def get_results_manifest(task_id: str):
    task_id = validate_task_id(task_id)
    try:
        status_resp = await run_in_threadpool(_resolve_task_state, task_id)
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
        has_video_probe, available_files_probe = await run_in_threadpool(_scan_task_artifacts, task_id)
        if not has_video_probe and not available_files_probe:
            raise
        status_resp = TaskStatusResponse(
            task_id=task_id,
            status=TaskStatusEnum.PENDING,
            progress=0,
            message="Waiting for worker...",
            warnings=[],
        )
    result_owner_task_id = status_resp.result_task_id or task_id

    has_video, available_files = await run_in_threadpool(_scan_task_artifacts, result_owner_task_id)
    task_result = await run_in_threadpool(_get_async_result, task_id)
    translations_by_lang = _translation_info_from_result(task_result.result)
    enriched_files: List[FileInfo] = []
    for file_info in available_files:
        lang_suffix = file_info.lang
        translation_info = translations_by_lang.get(lang_suffix)
        enriched_files.append(
            FileInfo(
                lang=lang_suffix,
                display_name=file_info.display_name,
                ass=file_info.ass,
                srt=file_info.srt,
                vtt=file_info.vtt,
                translated=translation_info.translated if translation_info else None,
                fallback_reason=translation_info.fallback_reason if translation_info else None,
            )
        )

    artifacts_exist = has_video or bool(enriched_files)
    return TaskResultManifest(
        task_id=task_id,
        task_status=status_resp.status,
        has_video=has_video,
        subtitle_languages=[f.display_name for f in enriched_files],
        available_files=enriched_files,
        warnings=status_resp.warnings,
        translations=list(translations_by_lang.values()),
        is_partial=(status_resp.status == TaskStatusEnum.SUCCESS and not artifacts_exist),
        orphaned_files_detected=(status_resp.status != TaskStatusEnum.SUCCESS and artifacts_exist),
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
        vtt = await run_in_threadpool(load_vtt_from_srt, UPLOAD_DIR, task_id, lang_suffix, lang)
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
        vtt = await run_in_threadpool(load_vtt_from_srt, UPLOAD_DIR, task_id, lang_suffix, lang)
        filename = f"{task_id}_{lang_suffix}.vtt"
        return {"content": vtt, "format": "vtt", "filename": filename}

    formats_to_try = [format] if format else ["ass", "srt"]
    for ext in formats_to_try:
        filename = f"{task_id}_{lang_suffix}.{ext}"
        path = validate_path_traversal(os.path.join(UPLOAD_DIR, filename), UPLOAD_DIR)
        if os.path.exists(path):
            content = await run_in_threadpool(_read_text_file, path)
            return {"content": content, "format": ext, "filename": filename}

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
        validate_subtitle_content(edit.content, target_format)
    except SubtitleValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.payload) from None

    try:
        await run_in_threadpool(write_text_atomic, filepath, edit.content)
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

    if settings.STORAGE_BACKEND == "s3":
        try:
            deleted = get_storage_backend().delete_file(f"{task_id}_final.mp4")
            if deleted:
                result["warnings"].append(
                    "Stored final video was deleted to prevent using old subtitles. "
                    "Use rebuild to generate a fresh final video."
                )
            else:
                result["warnings"].append("Subtitle updated but stored final video could not be deleted.")
        except Exception:
            logger.warning("Failed to delete stored final video after subtitle update: %s", task_id, exc_info=True)
            result["warnings"].append("Subtitle updated but stored final video could not be deleted.")

    return result


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.API_HOST, port=settings.API_PORT)
