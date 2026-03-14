import os
from openai import OpenAI
from .subtitle_utils import format_timestamp
from tenacity import retry, stop_after_attempt, wait_exponential

client = OpenAI() # 使用環境變數中的 API Key

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    reraise=True
)
def translate_text(text: str, source_lang: str, target_lang: str = "Traditional Chinese"):
    if not text.strip():
        return ""
    
    prompt = f"Translate the following {source_lang} text to {target_lang}. Maintain the original tone and context. Only provide the translation.\n\nText: {text}"
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content.strip()

def translate_segments(segments, source_lang: str, target_langs: list = ["Traditional Chinese"]):
    """
    同步翻譯所有片段到多個語言
    """
    translated_results = {lang: [] for lang in target_langs}
    
    for segment in segments:
        original_text = segment.text.strip()
        for lang in target_langs:
            translated_text = translate_text(original_text, source_lang, lang)
            translated_results[lang].append(translated_text)
            
    return translated_results

def generate_bilingual_srt(segments, translated_texts, output_path: str):
    srt_content = ""
    for i, segment in enumerate(segments):
        start = format_timestamp(segment.start)
        end = format_timestamp(segment.end)
        original_text = segment.text.strip()
        translated_text = translated_texts[i]
        
        combined_text = f"{translated_text}\n{original_text}"
        srt_content += f"{i + 1}\n{start} --> {end}\n{combined_text}\n\n"
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(srt_content)
    return output_path
