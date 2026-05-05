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


APP_ENV = _getenv("APP_ENV", "development") or "development"
TESTING = _get_bool("TESTING", False)

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = _getenv("UPLOAD_DIR", str(BASE_DIR / "uploads")) or str(BASE_DIR / "uploads")

REDIS_URL = _getenv("REDIS_URL", "redis://localhost:6379/0") or "redis://localhost:6379/0"
CELERY_BROKER_URL = _getenv("CELERY_BROKER_URL", REDIS_URL, aliases=("REDIS_URL",)) or REDIS_URL
CELERY_RESULT_BACKEND = _getenv("CELERY_RESULT_BACKEND", REDIS_URL, aliases=("REDIS_URL",)) or REDIS_URL

CORS_ORIGINS = _getenv("CORS_ORIGINS", "*", aliases=("CORS_ALLOWED_ORIGINS",)) or "*"
CORS_ALLOW_CREDENTIALS = _get_bool("CORS_ALLOW_CREDENTIALS", False)

MAX_UPLOAD_SIZE_MB = _get_int("MAX_UPLOAD_SIZE_MB", 2048)

TRANSLATE_PROVIDER = (_getenv("TRANSLATE_PROVIDER", "openai") or "openai").strip().lower()
TRANSLATE_MODEL = _getenv("TRANSLATE_MODEL", "gpt-4o-mini") or "gpt-4o-mini"
OPENAI_API_KEY = _getenv("OPENAI_API_KEY", "")
WHISPER_MODEL = _getenv("WHISPER_MODEL", "base") or "base"
HF_TOKEN = _getenv("HF_TOKEN", "")

STORAGE_BACKEND = (_getenv("STORAGE_BACKEND", "local") or "local").strip().lower()

