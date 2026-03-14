import os
import time
import shutil
import subprocess
from celery import chord
from .celery_app import celery_app
from .utils.subtitle_utils import transcribe_video
from .utils.video_utils import burn_subtitles, remove_silence
from .utils.translate_utils import translate_segments, generate_bilingual_srt
from .utils.ass_utils import generate_ass
from .utils.split_utils import split_video, merge_segments_subtitles
from .utils.model_loader import get_model_by_duration
from .utils.diarization_utils import diarize_audio, merge_speaker_info
from moviepy import VideoFileClip

class SimpleSegment:
    def __init__(self, start, end, text):
        self.start = start
        self.end = end
        self.text = text

def finalize_pipeline(segment_results, video_path, options, update_state_func=None):
    """
    核心處理流程：合併、翻譯、燒錄。
    """
    business_id = options.get("business_id")
    target_langs = options.get("target_langs", ["Traditional Chinese"])
    do_burn = options.get("burn_subtitles", True)
    subtitle_format = options.get("subtitle_format", "ass")
    hf_token = options.get("hf_token")
    
    # 致命問題 1 修復：強制使用 business_id 作為命名基底，避免靜音剪輯後路徑不一致
    upload_dir = os.path.dirname(os.path.abspath(video_path))
    base_path = os.path.join(upload_dir, business_id)
    
    # 1. 合併片段結果
    if update_state_func:
        update_state_func(state='PROGRESS', meta={'progress': 40, 'status': 'Merging parallel results...'})
            
    adapted_results = []
    for res in segment_results:
        adapted_res = {
            "start_offset": res["start_offset"],
            "segments": [SimpleSegment(s["start"], s["end"], s["text"]) for s in res["segments"]]
        }
        adapted_results.append(adapted_res)
        
    segments = merge_segments_subtitles(adapted_results)
    
    # 清理片段目錄 (使用 video_path 推導，因為 split_video 是基於它產生的)
    segments_dir = f"{os.path.splitext(video_path)[0]}_segments"
    if os.path.exists(segments_dir):
        shutil.rmtree(segments_dir)
    
    # 2. 說話者偵測 (Diarization)
    if hf_token:
        if update_state_func:
            update_state_func(state='PROGRESS', meta={'progress': 50, 'status': 'Performing speaker diarization...'})
        try:
            audio_path = f"{base_path}_temp.wav"
            subprocess.run(["ffmpeg", "-y", "-i", video_path, "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", audio_path], check=True)
            diarization_result = diarize_audio(audio_path, hf_token)
            segments = merge_speaker_info(segments, diarization_result)
            if os.path.exists(audio_path): os.remove(audio_path)
        except Exception as e:
            print(f"Diarization failed: {e}")

    # 3. 多語種同步翻譯 (批次處理)
    if update_state_func:
        update_state_func(state='PROGRESS', meta={'progress': 70, 'status': 'Translating (Batch Mode)...'})
    
    try:
        translations = translate_segments(segments, "Auto", target_langs)
    except Exception as e:
        print(f"Translation critical error: {e}")
        # 發生嚴重錯誤時回傳原文，並在狀態中提示
        translations = {lang: [s.text for s in segments] for lang in target_langs}
        if update_state_func:
            update_state_func(state='PROGRESS', meta={'progress': 70, 'status': f'Translation failed: {str(e)}. Using original text.'})
    
    # 4. 生成字幕檔案
    if update_state_func:
        update_state_func(state='PROGRESS', meta={'progress': 85, 'status': 'Generating final subtitles...'})
    result_files = {}
    for lang in target_langs:
        lang_suffix = lang.replace(" ", "_")
        bilingual_srt = f"{base_path}_{lang_suffix}.srt"
        generate_bilingual_srt(segments, translations[lang], bilingual_srt)
        
        if subtitle_format == "ass":
            bilingual_ass = f"{base_path}_{lang_suffix}.ass"
            ass_segments = [SimpleSegment(s.start, s.end, f"{translations[lang][i]}\\N{s.text}") for i, s in enumerate(segments)]
            generate_ass(ass_segments, bilingual_ass)
            result_files[lang] = bilingual_ass
        else:
            result_files[lang] = bilingual_srt

    # 5. 字幕燒錄
    final_video_path = f"{base_path}_final.mp4"
    if do_burn:
        if update_state_func:
            update_state_func(state='PROGRESS', meta={'progress': 95, 'status': 'Burning subtitles...'})
        first_lang_file = list(result_files.values())[0]
        burn_subtitles(video_path, first_lang_file, final_video_path)
    else:
        # 如果不燒錄，則將處理後的影片複製為 final 名稱以便下載
        shutil.copy2(video_path, final_video_path)
    
    if update_state_func:
        update_state_func(state='PROGRESS', meta={'progress': 100, 'status': 'Completed'})
    return {"status": "COMPLETED", "business_id": business_id, "video_path": final_video_path}

@celery_app.task
def transcribe_segment_task(segment_data: dict, model_size: str):
    path = segment_data['path']
    offset = segment_data['start_offset']
    temp_srt = f"{path}.srt"
    segments = transcribe_video(path, temp_srt, model_size=model_size)
    segment_dicts = [{"start": s.start, "end": s.end, "text": s.text} for s in segments]
    return {"start_offset": offset, "segments": segment_dicts}

@celery_app.task(bind=True)
def merge_and_finalize_task(self, segment_results, video_path, options):
    return finalize_pipeline(segment_results, video_path, options, update_state_func=self.update_state)

@celery_app.task(bind=True)
def process_video_task(self, video_path: str, options: dict = None):
    options = options or {}
    parallel = options.get("parallel", True)
    do_remove_silence = options.get("remove_silence", False)
    
    base_path = os.path.splitext(video_path)[0]
    
    # 0. 預處理：靜音剪輯
    current_video = video_path
    if do_remove_silence:
        self.update_state(state='PROGRESS', meta={'progress': 5, 'status': 'Removing silence (FFmpeg)...'})
        silence_removed_video = f"{base_path}_no_silence.mp4"
        remove_silence(video_path, silence_removed_video)
        current_video = silence_removed_video

    video = VideoFileClip(current_video)
    duration = video.duration
    video.close()
    model_size = get_model_by_duration(duration)
    
    # 1. 語音辨識
    if parallel and duration > 60:
        self.update_state(state='PROGRESS', meta={'progress': 10, 'status': 'Splitting video for parallel processing...'})
        video_segments = split_video(current_video)
        
        header = [transcribe_segment_task.s(seg, model_size) for seg in video_segments]
        callback = merge_and_finalize_task.s(current_video, options)
        return self.replace(chord(header)(callback))
    else:
        self.update_state(state='PROGRESS', meta={'progress': 20, 'status': 'Transcribing (Single Worker)...'})
        srt_path = f"{base_path}.srt"
        segments = transcribe_video(current_video, srt_path, model_size=model_size)
        segment_dicts = [{"start": s.start, "end": s.end, "text": s.text} for s in segments]
        return finalize_pipeline([{"start_offset": 0, "segments": segment_dicts}], current_video, options, update_state_func=self.update_state)

@celery_app.task
def cleanup_old_files():
    """
    定時清理任務：刪除超過 24 小時的檔案與目錄
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    upload_dir = os.getenv("UPLOAD_DIR", os.path.join(base_dir, "uploads"))
    if not os.path.exists(upload_dir): return
        
    now = time.time()
    retention_period = 24 * 3600
    for filename in os.listdir(upload_dir):
        file_path = os.path.join(upload_dir, filename)
        # 致命問題 3 修復：修正邏輯，確保資料夾與檔案都能被正確刪除
        if now - os.path.getmtime(file_path) > retention_period:
            try:
                if os.path.isdir(file_path):
                    shutil.rmtree(file_path)
                else:
                    os.remove(file_path)
            except Exception as e:
                print(f"Cleanup failed for {file_path}: {e}")
