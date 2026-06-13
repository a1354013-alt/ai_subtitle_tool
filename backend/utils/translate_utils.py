from __future__ import annotations

import json
import logging
import time
from urllib import error, request

from .. import settings
from ..services.llm_capabilities import get_configured_provider
from .time_utils import format_timestamp
from .translate_policy import is_translation_request, should_translate, translation_targets_requested

logger = logging.getLogger(__name__)

_openai_client = None


def get_openai_client():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI

        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY environment variable not set. Translation feature requires OpenAI API key.")
        _openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _openai_client


def is_retriable_exception(exception: Exception) -> bool:
    class_name = exception.__class__.__name__
    if class_name in {"APIConnectionError", "RateLimitError"}:
        return True
    if class_name == "APIError" and getattr(exception, "status_code", None) in (429, 500, 502, 503):
        return True
    return isinstance(exception, (ValueError, TimeoutError, error.URLError))


def _build_translation_prompt(texts: list[str], source_lang: str, target_lang: str) -> str:
    return (
        f"Translate the following strings from {source_lang} to {target_lang}.\n"
        'Return a JSON object with a key "translations" containing the array of translated strings in the same order.\n\n'
        f"Input: {json.dumps(texts, ensure_ascii=False)}"
    )


def _parse_translation_payload(content: str, expected_count: int) -> list[str]:
    try:
        result = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Translation parsing failed: {exc}") from exc

    if not isinstance(result, dict) or "translations" not in result:
        raise ValueError("Translation parsing failed: Missing 'translations' key in response")

    translations = result["translations"]
    if not isinstance(translations, list):
        raise ValueError("Translation parsing failed: 'translations' is not a list")
    if len(translations) != expected_count:
        raise ValueError(f"Translation parsing failed: Length mismatch: expected {expected_count}, got {len(translations)}")
    return [str(item) for item in translations]


def translate_batch_openai(texts: list[str], source_lang: str, target_lang: str) -> list[str]:
    if not texts:
        return []

    client = get_openai_client()
    prompt = _build_translation_prompt(texts, source_lang, target_lang)

    response = None
    for attempt in range(5):
        try:
            response = client.chat.completions.create(
                model=settings.OPENAI_MODEL or settings.TRANSLATE_MODEL or "gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a professional translator. Always output a JSON object with a 'translations' key.",
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                timeout=30.0,
            )
            break
        except Exception as exc:
            if attempt == 4 or not is_retriable_exception(exc):
                raise
            logger.info("Retrying OpenAI translation after provider error: %s", exc)
            time.sleep(min(10, 2**attempt))

    if response is None:
        raise RuntimeError("OpenAI translation failed")

    content = response.choices[0].message.content
    return _parse_translation_payload(content, len(texts))


def _ollama_chat_request(payload: dict, timeout_seconds: float = 60.0) -> dict:
    base_url = (settings.OLLAMA_BASE_URL or "http://127.0.0.1:11434").rstrip("/")
    req = request.Request(
        f"{base_url}/api/chat",
        method="POST",
        headers={"Content-Type": "application/json"},
        data=json.dumps(payload).encode("utf-8"),
    )
    with request.urlopen(req, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8") or "{}")


def translate_batch_ollama(texts: list[str], source_lang: str, target_lang: str) -> list[str]:
    if not texts:
        return []

    prompt = _build_translation_prompt(texts, source_lang, target_lang)
    payload = {
        "model": settings.OLLAMA_MODEL,
        "stream": False,
        "format": "json",
        "messages": [
            {
                "role": "system",
                "content": "You are a professional translator. Always output valid JSON with a 'translations' array.",
            },
            {"role": "user", "content": prompt},
        ],
    }

    response = None
    for attempt in range(3):
        try:
            response = _ollama_chat_request(payload)
            break
        except Exception as exc:
            if attempt == 2 or not is_retriable_exception(exc):
                raise
            logger.info("Retrying Ollama translation after provider error: %s", exc)
            time.sleep(min(5, 2**attempt))

    if response is None:
        raise RuntimeError("Ollama translation failed")

    content = (((response.get("message") or {}).get("content")) or "").strip()
    if not content:
        raise ValueError("Ollama returned an empty translation response")
    return _parse_translation_payload(content, len(texts))


def translate_batch(texts, source_lang, target_lang):
    provider = get_configured_provider()
    if provider == "ollama":
        return translate_batch_ollama(texts, source_lang, target_lang)
    if provider == "openai":
        return translate_batch_openai(texts, source_lang, target_lang)
    raise ValueError("Translation is disabled because LLM_PROVIDER=none.")


def translate_segments(segments, source_lang, target_langs, batch_size=30):
    texts = [s.text for s in segments]
    all_translations = {}

    for lang in target_langs:
        translated_texts = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            translated_texts.extend(translate_batch(batch, source_lang, lang))
        all_translations[lang] = translated_texts

    return all_translations, []


def generate_bilingual_srt(segments, translated_texts, output_path):
    srt_content = ""
    for i, (seg, trans) in enumerate(zip(segments, translated_texts)):
        start = format_timestamp(seg.start)
        end = format_timestamp(seg.end)
        combined_text = f"{trans}\n{seg.text}"
        srt_content += f"{i + 1}\n{start} --> {end}\n{combined_text}\n\n"

    with open(output_path, "w", encoding="utf-8") as file_obj:
        file_obj.write(srt_content)
    return output_path
