from __future__ import annotations

import os
from pathlib import Path


def _getenv(name: str, default: str | None = None, aliases: tuple[str, ...] = ()) -> str | None:
    for key in (name, *aliases):
        value = os.getenv(key)
        if value not in (None, ""):
            return value
    return default


def _get_bool(name: str, default: bool = False, aliases: tuple[str, ...] = ()) -> bool:
    raw = _getenv(name, aliases=aliases)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int, aliases: tuple[str, ...] = ()) -> int:
    raw = _getenv(name, aliases=aliases)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


BASE_DIR = Path(__file__).resolve().parent

ENVIRONMENT = _getenv("ENVIRONMENT", "development", aliases=("APP_ENV",)) or "development"
APP_ENV = ENVIRONMENT
TESTING = _get_bool("TESTING", False)

API_HOST = _getenv("API_HOST", "0.0.0.0") or "0.0.0.0"
API_PORT = _get_int("API_PORT", 8000)

UPLOAD_DIR = Path(_getenv("UPLOAD_DIR", str(BASE_DIR / "uploads")) or (BASE_DIR / "uploads")).resolve()
OUTPUT_DIR = Path(_getenv("OUTPUT_DIR", str(BASE_DIR / "outputs")) or (BASE_DIR / "outputs")).resolve()
TEMP_DIR = Path(_getenv("TEMP_DIR", str(BASE_DIR / "tmp")) or (BASE_DIR / "tmp")).resolve()

REDIS_URL = _getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
CELERY_BROKER_URL = _getenv("CELERY_BROKER_URL", REDIS_URL, aliases=("REDIS_URL",)) or REDIS_URL
CELERY_RESULT_BACKEND = _getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1") or "redis://localhost:6379/1"

CORS_ORIGINS = _getenv("CORS_ORIGINS", "*", aliases=("CORS_ALLOWED_ORIGINS",)) or "*"
CORS_ALLOW_CREDENTIALS = _get_bool("CORS_ALLOW_CREDENTIALS", False)

MAX_UPLOAD_SIZE_MB = _get_int("MAX_UPLOAD_SIZE_MB", 2048)
MAX_BATCH_FILES = _get_int("MAX_BATCH_FILES", 20)

TRANSLATE_PROVIDER = (_getenv("TRANSLATE_PROVIDER", "openai") or "openai").strip().lower()
TRANSLATE_MODEL = _getenv("TRANSLATE_MODEL", _getenv("OPENAI_MODEL", "gpt-4o-mini")) or "gpt-4o-mini"
OPENAI_API_KEY = _getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = _getenv("OPENAI_MODEL", TRANSLATE_MODEL) or TRANSLATE_MODEL
WHISPER_MODEL = _getenv("WHISPER_MODEL", "base") or "base"
HF_TOKEN = _getenv("HF_TOKEN", "")

FFMPEG_BINARY = _getenv("FFMPEG_BINARY", "ffmpeg") or "ffmpeg"
FFPROBE_BINARY = _getenv("FFPROBE_BINARY", "ffprobe") or "ffprobe"

STORAGE_BACKEND = (_getenv("STORAGE_BACKEND", "local") or "local").strip().lower()

SUPPORTED_VIDEO_EXTENSIONS = (".mp4", ".mkv", ".avi", ".mov")
EDITABLE_SUBTITLE_FORMATS = ("srt", "ass")
SUBTITLE_FORMATS = ("srt", "ass", "vtt")
BATCH_UPLOAD_ENABLED = True


def get_upload_dir() -> str:
    path = Path(_getenv("UPLOAD_DIR", str(BASE_DIR / "uploads")) or (BASE_DIR / "uploads")).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def get_output_dir() -> str:
    path = Path(_getenv("OUTPUT_DIR", str(BASE_DIR / "outputs")) or (BASE_DIR / "outputs")).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def get_temp_dir() -> str:
    path = Path(_getenv("TEMP_DIR", str(BASE_DIR / "tmp")) or (BASE_DIR / "tmp")).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def get_cors_origins() -> list[str]:
    return [origin.strip() for origin in CORS_ORIGINS.split(",") if origin.strip()]


def task_input_path(task_id: str, extension: str) -> Path:
    ext = extension if extension.startswith(".") else f".{extension}"
    return Path(get_upload_dir()) / f"{task_id}{ext}"


def task_artifact_base(task_id: str) -> Path:
    return Path(get_upload_dir()) / task_id


def task_output_path(task_id: str, suffix: str, extension: str) -> Path:
    ext = extension if extension.startswith(".") else f".{extension}"
    if suffix:
        return Path(get_upload_dir()) / f"{task_id}_{suffix}{ext}"
    return Path(get_upload_dir()) / f"{task_id}{ext}"


def task_final_video_path(task_id: str) -> Path:
    return task_output_path(task_id, "final", ".mp4")


def ensure_runtime_dirs() -> None:
    get_upload_dir()
    get_output_dir()
    get_temp_dir()


ensure_runtime_dirs()
