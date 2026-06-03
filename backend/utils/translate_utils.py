import json
import logging
import os
import time

from .time_utils import format_timestamp
from .translate_policy import is_translation_request, should_translate, translation_targets_requested

logger = logging.getLogger(__name__)

TRANSLATE_MODEL = os.getenv("TRANSLATE_MODEL", "gpt-4o-mini")
_openai_client = None


def get_openai_client():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY environment variable not set. "
                "Translation feature requires OpenAI API key."
            )
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client


def is_retriable_exception(exception: Exception) -> bool:
    class_name = exception.__class__.__name__
    if class_name in {"APIConnectionError", "RateLimitError"}:
        return True
    if class_name == "APIError" and getattr(exception, "status_code", None) in (429, 500, 502, 503):
        return True
    return isinstance(exception, ValueError)


def translate_batch(texts, source_lang, target_lang):
    if not texts:
        return []

    client = get_openai_client()
    prompt = f"""Translate the following strings from {source_lang} to {target_lang}.
Return a JSON object with a key "translations" containing the array of translated strings in the same order.

Input: {json.dumps(texts, ensure_ascii=False)}"""

    response = None
    for attempt in range(5):
        try:
            response = client.chat.completions.create(
                model=TRANSLATE_MODEL,
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
        except Exception as e:
            if attempt == 4 or not is_retriable_exception(e):
                raise
            logger.info("Retrying translation after provider error: %s", e)
            time.sleep(min(10, 2**attempt))

    if response is None:
        raise RuntimeError("Translation failed")

    content = response.choices[0].message.content
    try:
        result = json.loads(content)
        if not isinstance(result, dict) or "translations" not in result:
            raise ValueError("Missing 'translations' key in response")

        translations = result["translations"]
        if not isinstance(translations, list):
            raise ValueError("'translations' is not a list")
        if len(translations) != len(texts):
            raise ValueError(f"Length mismatch: expected {len(texts)}, got {len(translations)}")
        return translations
    except (json.JSONDecodeError, ValueError) as e:
        raise ValueError(f"Translation parsing failed: {str(e)}") from e


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

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(srt_content)
    return output_path
