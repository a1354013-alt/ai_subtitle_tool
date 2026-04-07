import os
from datetime import timedelta
from .model_loader import get_model, get_model_by_duration
from .audio_utils import preprocess_audio
import moviepy

def format_timestamp(seconds: float):
    td = timedelta(seconds=seconds)
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    millis = int(td.microseconds / 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"

def generate_srt(segments):
    srt_content = ""
    for i, segment in enumerate(segments):
        start = format_timestamp(segment.start)
        end = format_timestamp(segment.end)
        text = segment.text.strip()
        srt_content += f"{i + 1}\n{start} --> {end}\n{text}\n\n"
    return srt_content

def transcribe_video(video_path: str, output_srt_path: str, model_size=None):
    """
    轉錄影片並生成 SRT 字幕檔。
    
    Args:
        video_path: 影片檔案路徑
        output_srt_path: 輸出 SRT 路徑
        model_size: Whisper 模型大小（tiny/small/medium/base），若為 None 則根據時長決定
    
    Returns:
        list of segments with (start, end, text) attributes
    """
    audio_path = None
    
    try:
        # 1. 獲取影片時長以決定模型
        video = moviepy.VideoFileClip(video_path)
        duration = video.duration
        video.close()
        
        if model_size is None:
            model_size = get_model_by_duration(duration)
        
        # 2. 音訊預處理
        audio_path = f"{os.path.splitext(video_path)[0]}_temp.wav"
        preprocess_audio(video_path, audio_path)
        
        # 3. 獲取 Faster-Whisper 模型
        model = get_model(model_size)
        
        # 4. 進行辨識
        segments, info = model.transcribe(audio_path, beam_size=5)
        
        # Faster-Whisper 的 segments 是 generator，需要轉為 list
        segments_list = list(segments)
        
        # 5. 生成 SRT
        srt_content = generate_srt(segments_list)
        
        with open(output_srt_path, "w", encoding="utf-8") as f:
            f.write(srt_content)
        
        return segments_list
    
    finally:
        # *** 確保暫存音訊一律被清理 ***
        if audio_path and os.path.exists(audio_path):
            try:
                os.remove(audio_path)
            except Exception as e:
                print(f"Warning: Failed to remove temp audio {audio_path}: {e}")
