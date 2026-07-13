from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass
from typing import Any
from urllib import error, request

from .. import settings
from ..utils.translate_policy import translation_targets_requested

logger = logging.getLogger(__name__)

SUPPORTED_PROVIDERS = {"openai", "ollama", "none"}
OPENAI_TRANSLATION_REQUIRED_MESSAGE = "OPENAI_API_KEY is required when translation targets are requested."
OLLAMA_UNAVAILABLE_MESSAGE = "Ollama is not reachable. Confirm OLLAMA_BASE_URL and that Ollama is running."
TRANSLATION_DISABLED_MESSAGE = "Translation is disabled because LLM_PROVIDER=none."
_OLLAMA_CACHE: dict[tuple[str, str], tuple[float, LLMCapabilityStatus]] = {}


@dataclass(frozen=True)
class LLMCapabilityStatus:
    provider: str
    model: str | None
    translation_enabled: bool
    reason: str | None
    message: str | None
    default_target_language: str
    available_modes: list[str]
    openai_configured: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def get_configured_provider() -> str:
    provider = (settings.LLM_PROVIDER or settings.TRANSLATE_PROVIDER or "none").strip().lower()
    return provider if provider in SUPPORTED_PROVIDERS else "none"


def _normalized_ollama_base_url() -> str:
    return (settings.OLLAMA_BASE_URL or "http://127.0.0.1:11434").rstrip("/")


def _openai_status() -> LLMCapabilityStatus:
    openai_configured = bool(settings.OPENAI_API_KEY)
    translation_enabled = openai_configured
    return LLMCapabilityStatus(
        provider="openai",
        model=settings.OPENAI_MODEL or settings.TRANSLATE_MODEL or "gpt-4o-mini",
        translation_enabled=translation_enabled,
        reason=None if translation_enabled else "openai_api_key_missing",
        message=None if translation_enabled else OPENAI_TRANSLATION_REQUIRED_MESSAGE,
        default_target_language="Traditional Chinese" if translation_enabled else "Original",
        available_modes=["transcribe"] + (["translate"] if translation_enabled else []),
        openai_configured=openai_configured,
    )


def _probe_ollama_tags(timeout_seconds: float = 2.0) -> tuple[bool, str | None]:
    base_url = _normalized_ollama_base_url()
    probe_url = f"{base_url}/api/tags"
    req = request.Request(probe_url, method="GET", headers={"Accept": "application/json"})
    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8") or "{}")
            if response.status >= 400:
                return False, f"Ollama probe failed with HTTP {response.status}"
            if isinstance(payload, dict) and "models" in payload:
                return True, None
            return True, None
    except error.HTTPError as exc:
        return False, f"Ollama probe failed with HTTP {exc.code}"
    except error.URLError as exc:
        return False, str(exc.reason)
    except TimeoutError:
        return False, "timed out"
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Unexpected Ollama probe error", exc_info=True)
        return False, str(exc)


def _ollama_status() -> LLMCapabilityStatus:
    model = settings.OLLAMA_MODEL or "gemma3:12b"
    if not (settings.OLLAMA_BASE_URL or "").strip():
        return LLMCapabilityStatus(
            provider="ollama",
            model=model,
            translation_enabled=False,
            reason="ollama_base_url_missing",
            message="OLLAMA_BASE_URL is required when LLM_PROVIDER=ollama.",
            default_target_language="Original",
            available_modes=["transcribe"],
            openai_configured=False,
        )
    if not model.strip():
        return LLMCapabilityStatus(
            provider="ollama",
            model=None,
            translation_enabled=False,
            reason="ollama_model_missing",
            message="OLLAMA_MODEL is required when LLM_PROVIDER=ollama.",
            default_target_language="Original",
            available_modes=["transcribe"],
            openai_configured=False,
        )

    cache_key = (_normalized_ollama_base_url(), model)
    ttl = settings.OLLAMA_CAPABILITY_CACHE_TTL_SECONDS
    now = time.time()
    if ttl > 0:
        cached = _OLLAMA_CACHE.get(cache_key)
        if cached and now - cached[0] < ttl:
            return cached[1]

    reachable, detail = _probe_ollama_tags()
    status = LLMCapabilityStatus(
        provider="ollama",
        model=model,
        translation_enabled=reachable,
        reason=None if reachable else "ollama_unreachable",
        message=None if reachable else f"{OLLAMA_UNAVAILABLE_MESSAGE} ({detail or _normalized_ollama_base_url()})",
        default_target_language="Traditional Chinese" if reachable else "Original",
        available_modes=["transcribe"] + (["translate"] if reachable else []),
        openai_configured=False,
    )
    if ttl > 0:
        _OLLAMA_CACHE[cache_key] = (now, status)
    return status


def _none_status() -> LLMCapabilityStatus:
    return LLMCapabilityStatus(
        provider="none",
        model=None,
        translation_enabled=False,
        reason="translation_disabled",
        message=TRANSLATION_DISABLED_MESSAGE,
        default_target_language="Original",
        available_modes=["transcribe"],
        openai_configured=False,
    )


def get_llm_capability_status() -> LLMCapabilityStatus:
    provider = get_configured_provider()
    if provider == "openai":
        return _openai_status()
    if provider == "ollama":
        return _ollama_status()
    return _none_status()


def ensure_translation_available(target_langs: list[str]) -> LLMCapabilityStatus:
    status = get_llm_capability_status()
    if not translation_targets_requested(target_langs):
        return status
    if status.translation_enabled:
        return status

    if status.provider == "openai":
        raise ValueError(OPENAI_TRANSLATION_REQUIRED_MESSAGE)
    if status.provider == "ollama":
        raise ValueError(OLLAMA_UNAVAILABLE_MESSAGE)
    raise ValueError(TRANSLATION_DISABLED_MESSAGE)
