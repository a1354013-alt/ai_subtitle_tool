import os
from datetime import timedelta

def format_ass_timestamp(seconds: float):
    """將秒數轉換為 ASS 時間格式 (h:mm:ss.cc)"""
    td = timedelta(seconds=seconds)
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    millis = int(td.microseconds / 10000)  # ASS 使用百分之一秒
    return f"{hours}:{minutes:02}:{secs:02}.{millis:02}"

def generate_ass(segments, output_path: str, title="AI Subtitles"):
    """
    生成 ASS 格式字幕檔案。
    
    Args:
        segments: list of SimpleSegment objects
        output_path: 輸出檔案路徑
        title: 字幕標題
        
    Returns:
        output_path
    """
    header = f"""[Script Info]
Title: {title}
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,24,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = ""
    for segment in segments:
        start = format_ass_timestamp(segment.start)
        end = format_ass_timestamp(segment.end)
        text = segment.text.strip().replace("\n", "\\N")
        events += f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}\n"
        
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header + events)
    return output_path
