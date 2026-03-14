import os
import time
from celery_app import celery_app
from utils.subtitle_utils import transcribe_video
from utils.video_utils import burn_subtitles, remove_silence
from utils.translate_utils import translate_segments, generate_bilingual_srt
from utils.ass_utils import generate_ass
from moviepy import VideoFileClip

@celery_app.task
def transcribe_segment_task(segment_data: dict, model_size: str):
    """
    子任務：辨識單個影片片段
    """
    from utils.subtitle_utils import transcribe_video
    path = segment_data['path']
    offset = segment_data['start_offset']
    temp_srt = f"{path}.srt"
    segments = transcribe_video(path, temp_srt, model_size=model_size)
    return {"start_offset": offset, "segments": segments}

@celery_app.task(bind=True)
def process_video_task(self, video_path: str, options: dict = None):
    from celery import group
    from utils.split_utils import split_video, merge_segments_subtitles
    from utils.model_loader import get_model_by_duration
    
    options = options or {}
    target_langs = options.get("target_langs", ["Traditional Chinese"])
    do_burn = options.get("burn_subtitles", True)
    subtitle_format = options.get("subtitle_format", "ass")
    parallel = options.get("parallel", True)
    
    base_path = os.path.splitext(video_path)[0]
    video = VideoFileClip(video_path)
    duration = video.duration
    video.close()
    
    model_size = get_model_by_duration(duration)
    
    # 1. 語音辨識 (分段並行處理)
    if parallel and duration > 60: # 超過 1 分鐘才並行
        self.update_state(state='PROGRESS', meta={'progress': 10, 'status': 'Splitting video for parallel processing...'})
        video_segments = split_video(video_path)
        
        self.update_state(state='PROGRESS', meta={'progress': 20, 'status': f'Transcribing {len(video_segments)} segments in parallel...'})
        # 建立並行任務組
        job = group(transcribe_segment_task.s(seg, model_size) for seg in video_segments)
        result = job.apply_async()
        
        # 等待所有子任務完成
        while not result.ready():
            time.sleep(1)
            
        segment_results = result.get()
        segments = merge_segments_subtitles(segment_results)
    else:
        self.update_state(state='PROGRESS', meta={'progress': 20, 'status': 'Transcribing with Faster-Whisper...'})
        srt_path = f"{base_path}.srt"
        segments = transcribe_video(video_path, srt_path, model_size=model_size)
    
    # 2. 多語種同步翻譯
    self.update_state(state='PROGRESS', meta={'progress': 50, 'status': 'Translating to multiple languages...'})
    translations = translate_segments(segments, "English/Japanese", target_langs)
    
    # 3. 生成字幕檔案 (SRT & ASS)
    self.update_state(state='PROGRESS', meta={'progress': 70, 'status': 'Generating stylized subtitles...'})
    result_files = {}
    
    # 為每個目標語言生成雙語字幕
    for lang in target_langs:
        lang_suffix = lang.replace(" ", "_")
        bilingual_srt = f"{base_path}_{lang_suffix}.srt"
        generate_bilingual_srt(segments, translations[lang], bilingual_srt)
        
        if subtitle_format == "ass":
            bilingual_ass = f"{base_path}_{lang_suffix}.ass"
            # 這裡簡化：將翻譯後的文字包裝成 segment-like 物件供 ASS 生成
            class MockSegment:
                def __init__(self, start, end, text):
                    self.start = start
                    self.end = end
                    self.text = text
            
            ass_segments = [MockSegment(s.start, s.end, f"{translations[lang][i]}\\N{s.text}") for i, s in enumerate(segments)]
            generate_ass(ass_segments, bilingual_ass)
            result_files[lang] = bilingual_ass
        else:
            result_files[lang] = bilingual_srt

    # 4. 字幕燒錄 (Hardsub)
    final_video = video_path
    if do_burn:
        self.update_state(state='PROGRESS', meta={'progress': 90, 'status': 'Burning subtitles...'})
        # 預設燒錄第一個目標語言的字幕
        first_lang_file = list(result_files.values())[0]
        final_video = f"{base_path}_final.mp4"
        burn_subtitles(video_path, first_lang_file, final_video)
    
    self.update_state(state='PROGRESS', meta={'progress': 100, 'status': 'Completed'})
    
    return {
        "status": "COMPLETED",
        "result_files": result_files,
        "video_path": final_video
    }

@celery_app.task
def cleanup_old_files():
    upload_dir = "/home/ubuntu/ai_subtitle_tool/backend/uploads"
    now = time.time()
    retention_period = 24 * 3600
    for filename in os.listdir(upload_dir):
        file_path = os.path.join(upload_dir, filename)
        if os.path.isfile(file_path) and now - os.path.getmtime(file_path) > retention_period:
            os.remove(file_path)
