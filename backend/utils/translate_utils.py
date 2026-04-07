import os
import json
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
from openai import APIError, APIConnectionError, RateLimitError

# B) 翻譯模型與版本 pin
TRANSLATE_MODEL = os.getenv("TRANSLATE_MODEL", "gpt-4o-mini")

# Lazy 初始化 OpenAI client
_openai_client = None

def get_openai_client():
    """Lazy 初始化 OpenAI client，避免在 import 時就連接"""
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

def format_timestamp(seconds: float):
    """將秒數轉換為 SRT 時間格式 (00:00:00,000)"""
    td_hours = int(seconds // 3600)
    td_minutes = int((seconds % 3600) // 60)
    td_seconds = int(seconds % 60)
    td_milliseconds = int((seconds % 1) * 1000)
    return f"{td_hours:02}:{td_minutes:02}:{td_seconds:02},{td_milliseconds:03}"

def is_retriable_exception(exception: Exception) -> bool:
    """
    P1.4 統一重試策略：單一判斷函式。
    判斷異常是否應該重試。
    
    可重試的情況：
    - 網路連接錯誤 (APIConnectionError)
    - API 速率限制 (RateLimitError)
    - 伺服器暫時故障 (429, 500, 502, 503)
    - JSON 解析錯誤 (ValueError) - 可能是臨時格式問題
    
    不可重試的情況：
    - 授權失敗
    - 模型不存在
    - 其他明確的客戶端編程錯誤
    """
    # 網路錯誤、連接錯誤、速率限制應該重試
    if isinstance(exception, (APIConnectionError, RateLimitError)):
        return True
    
    # 一般 APIError（包括伺服器錯誤和 timeout）
    if isinstance(exception, APIError):
        # 檢查 HTTP 狀態碼（429, 500, 502, 503 都是臨時故障）
        if hasattr(exception, 'status_code') and exception.status_code in (429, 500, 502, 503):
            return True
        # 其他 APIError（例如 4xx 客戶端錯誤）不重試
    
    # JSON 解析失敗可能是臨時問題，應該重試
    if isinstance(exception, ValueError):
        return True
    
    return False

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception(is_retriable_exception),
    reraise=True
)
def translate_batch(texts, source_lang, target_lang):
    """
    批次翻譯：將多段文字合併為一個 JSON 物件發送。
    支持重試 (最多 5 次)：網路錯誤、timeout、rate limit、JSON parse error
    """
    if not texts:
        return []
        
    client = get_openai_client()  # Lazy 初始化
    
    prompt = f"""Translate the following strings from {source_lang} to {target_lang}.
Return a JSON object with a key "translations" containing the array of translated strings in the same order.

Input: {json.dumps(texts, ensure_ascii=False)}"""

    try:
        response = client.chat.completions.create(
            model=TRANSLATE_MODEL,
            messages=[
                {"role": "system", "content": "You are a professional translator. Always output a JSON object with a 'translations' key."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            timeout=30.0  # 30 秒超時
        )
    except (APIConnectionError, RateLimitError, APIError, TimeoutError) as e:
        # 這些異常會由 retry_if_exception(is_retriable_exception) 判斷是否重試
        raise e
    
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
        # JSON 解析失敗會由 is_retriable_exception 判斷是否重試
        raise ValueError(f"Translation parsing failed: {str(e)}")

def translate_segments(segments, source_lang, target_langs, batch_size=30):
    """
    對所有字幕段落進行多語種批次翻譯。
    注意：此處不捕捉異常，讓它向上拋出給 tasks.py 處理語言級別的 fallback。
    """
    texts = [s.text for s in segments]
    all_translations = {}
    
    for lang in target_langs:
        translated_texts = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            # 這裡會拋出異常如果 5 次重試都失敗
            translated_batch = translate_batch(batch, source_lang, lang)
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
