import os
import json
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

client = OpenAI()

# B) 翻譯模型與版本 pin：成本/品質不一定是你想要的（可配置比較好）
TRANSLATE_MODEL = os.getenv("TRANSLATE_MODEL", "gpt-4o-mini")

def format_timestamp(seconds: float):
    """將秒數轉換為 SRT 時間格式 (00:00:00,000)"""
    td_hours = int(seconds // 3600)
    td_minutes = int((seconds % 3600) // 60)
    td_seconds = int(seconds % 60)
    td_milliseconds = int((seconds % 1) * 1000)
    return f"{td_hours:02}:{td_minutes:02}:{td_seconds:02},{td_milliseconds:03}"

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type(ValueError),
    reraise=True
)
def translate_batch(texts, source_lang, target_lang):
    """
    批次翻譯：將多段文字合併為一個 JSON 物件發送。
    B) 翻譯可靠度：格式不符就 raise 讓 tenacity retry。
    """
    if not texts:
        return []
        
    prompt = f"""Translate the following strings from {source_lang} to {target_lang}.
Return a JSON object with a key "translations" containing the array of translated strings in the same order.

Input: {json.dumps(texts, ensure_ascii=False)}"""

    response = client.chat.completions.create(
        model=TRANSLATE_MODEL,
        messages=[
            {"role": "system", "content": "You are a professional translator. Always output a JSON object with a 'translations' key."},
            {"role": "user", "content": prompt}
        ],
        response_format={"type": "json_object"}
    )
    
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
        # 拋出異常以觸發 Tenacity 重試
        raise ValueError(f"Translation parsing failed: {str(e)}")

def translate_segments(segments, source_lang, target_langs, batch_size=30):
    """
    對所有字幕段落進行多語種批次翻譯。
    注意：此處不捕捉異常，讓它向上拋出給 tasks.py 處理語言級別的 fallback。
    """
    texts = [s.text for s in segments]
    all_translations = {}
    warnings: list[str] = []
    
    for lang in target_langs:
        translated_texts = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            # 這裡會拋出 ValueError 如果 5 次重試都失敗
            translated_batch = translate_batch(batch, source_lang, lang)
            translated_texts.extend(translated_batch)
        all_translations[lang] = translated_texts
        
    return all_translations, warnings

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
