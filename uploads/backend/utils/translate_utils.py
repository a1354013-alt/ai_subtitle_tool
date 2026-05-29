import logging
import os
import json
import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception, after_log
from openai import APIError, APIConnectionError, RateLimitError

from .time_utils import format_timestamp
from .. import settings

logger = logging.getLogger(__name__)

# Lazy 初始化 OpenAI client
_openai_client = None


def get_openai_client():
    """Lazy 初始化 OpenAI client"""
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        if not settings.OPENAI_API_KEY:
            logger.error("OPENAI_API_KEY not set, but openai provider selected.")
            return None
        _openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _openai_client


def is_retriable_exception(exception: Exception) -> bool:
    """判斷異常是否應該重試"""
    if isinstance(exception, (APIConnectionError, RateLimitError, requests.exceptions.RequestException)):
        return True
    
    if isinstance(exception, APIError):
        if hasattr(exception, 'status_code') and exception.status_code in (429, 500, 502, 503):
            return True
    
    if isinstance(exception, ValueError):
        return True
    
    return False


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception(is_retriable_exception),
    reraise=True,
    after=after_log(logger, logging.INFO)
)
def _translate_openai(texts, source_lang, target_lang):
    """使用 OpenAI 進行翻譯"""
    client = get_openai_client()
    if not client:
        raise ValueError("OpenAI client not initialized")

    prompt = f"""Translate the following strings from {source_lang} to {target_lang}.
Return a JSON object with a key "translations" containing the array of translated strings in the same order.

Input: {json.dumps(texts, ensure_ascii=False)}"""

    response = client.chat.completions.create(
        model=settings.TRANSLATE_MODEL,
        messages=[
            {"role": "system", "content": "You are a professional translator. Always output a JSON object with a 'translations' key."},
            {"role": "user", "content": prompt}
        ],
        response_format={"type": "json_object"},
        timeout=30.0
    )
    
    content = response.choices[0].message.content
    result = json.loads(content)
    return result["translations"]


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception(is_retriable_exception),
    reraise=True,
    after=after_log(logger, logging.INFO)
)
def _translate_ollama(texts, source_lang, target_lang):
    """使用 Ollama 進行翻譯"""
    url = f"{settings.OLLAMA_BASE_URL}/api/generate"
    
    # 為了確保 Ollama 回傳正確格式，我們要求它回傳 JSON
    prompt = f"""Translate the following strings from {source_lang} to {target_lang}.
Return a JSON object with a key "translations" containing the array of translated strings in the same order.
Do not include any other text in your response.

Input: {json.dumps(texts, ensure_ascii=False)}"""

    payload = {
        "model": settings.OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json"
    }
    
    response = requests.post(url, json=payload, timeout=60.0)
    response.raise_for_status()
    
    data = response.json()
    content = data.get("response", "")
    result = json.loads(content)
    return result["translations"]


def translate(texts, source_lang, target_lang):
    """
    統一翻譯入口
    """
    if not texts:
        return []

    provider = settings.TRANSLATE_PROVIDER
    
    try:
        if provider == "openai":
            return _translate_openai(texts, source_lang, target_lang)
        elif provider == "ollama":
            return _translate_ollama(texts, source_lang, target_lang)
        else:
            # fallback to original text
            return texts
    except Exception as e:
        logger.error(f"Translation failed with provider {provider}: {e}. Falling back to original text.")
        return texts


def translate_segments(segments, source_lang, target_langs, batch_size=30):
    """
    對所有字幕段落進行多語種批次翻譯。
    """
    texts = [s.text for s in segments]
    all_translations = {}
    
    for lang in target_langs:
        translated_texts = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            translated_batch = translate(batch, source_lang, lang)
            
            # 確保長度一致，如果不一致則補齊原文
            if len(translated_batch) != len(batch):
                logger.warning(f"Translation length mismatch for {lang}. Expected {len(batch)}, got {len(translated_batch)}")
                translated_batch = translated_batch[:len(batch)] + batch[len(translated_batch):]
                
            translated_texts.extend(translated_batch)
        all_translations[lang] = translated_texts
        
    return all_translations, []


def generate_bilingual_srt(segments, translated_texts, output_path):
    """
    生成雙語 SRT 檔案
    """
    srt_content = ""
    for i, (seg, trans) in enumerate(zip(segments, translated_texts)):
        start = format_timestamp(seg.start)
        end = format_timestamp(seg.end)
        combined_text = f"{trans}\n{seg.text}"
        srt_content += f"{i + 1}\n{start} --> {end}\n{combined_text}\n\n"
        
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(srt_content)
    return output_path
