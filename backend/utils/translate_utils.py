import json
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

client = OpenAI()

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
    reraise=True
)
def translate_batch(texts, source_lang, target_lang):
    """
    批次翻譯：將多段文字合併為一個 JSON 物件發送，確保模型輸出穩定
    """
    if not texts:
        return []
        
    # 統一要求回傳 {"translations": ["...", "..."]} 格式
    prompt = f"""Translate the following strings from {source_lang} to {target_lang}.
Return a JSON object with a key "translations" containing the array of translated strings in the same order.

Input: {json.dumps(texts, ensure_ascii=False)}"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a professional translator. Always output a JSON object with a 'translations' key."},
            {"role": "user", "content": prompt}
        ],
        response_format={"type": "json_object"}
    )
    
    try:
        content = response.choices[0].message.content
        result = json.loads(content)
        # 強制讀取 translations 鍵值
        if isinstance(result, dict) and "translations" in result:
            return result["translations"]
        return texts # 格式不符時回傳原文
    except Exception as e:
        print(f"Translation parsing error: {e}")
        return texts # 失敗時回傳原文

def translate_segments(segments, source_lang, target_langs, batch_size=30):
    """
    對所有字幕段落進行多語種批次翻譯
    """
    texts = [s.text for s in segments]
    all_translations = {}
    
    for lang in target_langs:
        translated_texts = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            translated_batch = translate_batch(batch, source_lang, lang)
            # 確保長度一致，若不一致則補原文
            if len(translated_batch) != len(batch):
                translated_batch = translated_batch[:len(batch)] + batch[len(translated_batch):]
            translated_texts.extend(translated_batch)
        all_translations[lang] = translated_texts
        
    return all_translations

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
