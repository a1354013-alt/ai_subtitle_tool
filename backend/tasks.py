import os
import time
import shutil
import subprocess
import json
from celery import chord
from .celery_app import celery_app
from .utils.subtitle_utils import transcribe_video
from .utils.video_utils import burn_subtitles, remove_silence
from .utils.translate_utils import translate_segments, generate_bilingual_srt
from .utils.ass_utils import generate_ass
from .utils.split_utils import split_video, merge_segments_subtitles
from .utils.model_loader import get_model_by_duration
from .utils.diarization_utils import diarize_audio, merge_speaker_info
from moviepy.editor import VideoFileClip

class SimpleSegment:
    def __init__(self, start, end, text):
        self.start = start
        self.end = end
        self.text = text

def create_task_lock(business_id):
    """建立任務鎖定檔，防止被 cleanup 誤刪"""
    upload_dir = os.getenv("UPLOAD_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads"))
    # B) 高風險修復：確保目錄存在
    os.makedirs(upload_dir, exist_ok=True)
    
    lock_path = os.path.join(upload_dir, f"{business_id}.lock")
    lock_info = {
        "business_id": business_id,
        "pid": os.getpid(),
        "timestamp": time.time()
    }
    with open(lock_path, "w") as f:
        json.dump(lock_info, f)
    return lock_path

def remove_task_lock(business_id):
    """移除任務鎖定檔"""
    upload_dir = os.getenv("UPLOAD_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads"))
    lock_path = os.path.join(upload_dir, f"{business_id}.lock")
    if os.path.exists(lock_path):
        os.remove(lock_path)

def finalize_pipeline(segment_results, video_path, options, update_state_func=None, segments_dir=None):
    """
    核心處理流程：合併、翻譯、燒錄。
    """
    business_id = options.get("business_id")
    target_langs = options.get("target_langs", ["Traditional Chinese"])
    do_burn = options.get("burn_subtitles", True)
    subtitle_format = options.get("subtitle_format", "ass")
    hf_token = options.get("hf_token")
    warnings = []
    
    try:
        upload_dir = os.path.dirname(os.path.abspath(video_path))
        # C) 品質優化：強制使用 business_id 作為基底，確保下載路徑一致
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
        
        # C) 品質優化：精準清理暫存目錄
        if segments_dir and os.path.exists(segments_dir):
            shutil.rmtree(segments_dir)
        
        # 2. 說話者偵測
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
                warnings.append(f"Diarization failed: {str(e)}")

        # 3. 多語種同步翻譯
        if update_state_func:
            update_state_func(state='PROGRESS', meta={'progress': 70, 'status': 'Translating...'})
        
        translations = {}
        for lang in target_langs:
            try:
                lang_trans = translate_segments(segments, "Auto", [lang])
                translations[lang] = lang_trans[lang]
            except Exception as e:
                msg = f"Translation failed for {lang}. Using original text."
                warnings.append(msg)
                translations[lang] = [s.text for s in segments]
        
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
            try:
                burn_subtitles(video_path, first_lang_file, final_video_path)
            except Exception as e:
                warnings.append(f"Subtitle burning failed: {str(e)}. Copying original video.")
                shutil.copy2(video_path, final_video_path)
        else:
            shutil.copy2(video_path, final_video_path)
        
        if update_state_func:
            update_state_func(state='PROGRESS', meta={'progress': 100, 'status': 'Completed'})
        
        return {
            "status": "COMPLETED", 
            "business_id": business_id, 
            "video_path": final_video_path,
            "warnings": warnings
        }
    finally:
        remove_task_lock(business_id)

@celery_app.task
def transcribe_segment_task(segment_data: dict, model_size: str):
    path = segment_data['path']
    offset = segment_data['start_offset']
    temp_srt = f"{path}.srt"
    segments = transcribe_video(path, temp_srt, model_size=model_size)
    segment_dicts = [{"start": s.start, "end": s.end, "text": s.text} for s in segments]
    return {"start_offset": offset, "segments": segment_dicts}

@celery_app.task(bind=True)
def merge_and_finalize_task(self, segment_results, video_path, options, segments_dir=None):
    return finalize_pipeline(segment_results, video_path, options, update_state_func=self.update_state, segments_dir=segments_dir)

@celery_app.task(bind=True)
def process_video_task(self, video_path: str, options: dict = None):
    options = options or {}
    business_id = options.get("business_id")
    create_task_lock(business_id)
    
    try:
        parallel = options.get("parallel", True)
        do_remove_silence = options.get("remove_silence", False)
        upload_dir = os.path.dirname(os.path.abspath(video_path))
        base_path = os.path.join(upload_dir, business_id)
        
        current_video = video_path
        if do_remove_silence:
            self.update_state(state='PROGRESS', meta={'progress': 5, 'status': 'Removing silence...'})
            silence_removed_video = f"{base_path}_no_silence.mp4"
            remove_silence(video_path, silence_removed_video)
            current_video = silence_removed_video

        video = VideoFileClip(current_video)
        duration = video.duration
        video.close()
        model_size = get_model_by_duration(duration)
        
        if parallel and duration > 60:
            self.update_state(state='PROGRESS', meta={'progress': 10, 'status': 'Splitting video...'})
            video_segments = split_video(current_video)
            # C) 品質優化：精準傳遞暫存目錄路徑
            segments_dir = f"{os.path.splitext(current_video)[0]}_segments"
            header = [transcribe_segment_task.s(seg, model_size) for seg in video_segments]
            callback = merge_and_finalize_task.s(current_video, options, segments_dir=segments_dir)
            return self.replace(chord(header)(callback))
        else:
            self.update_state(state='PROGRESS', meta={'progress': 20, 'status': 'Transcribing...'})
            srt_path = f"{base_path}.srt"
            segments = transcribe_video(current_video, srt_path, model_size=model_size)
            segment_dicts = [{"start": s.start, "end": s.end, "text": s.text} for s in segments]
            return finalize_pipeline([{"start_offset": 0, "segments": segment_dicts}], current_video, options, update_state_func=self.update_state)
    except Exception as e:
        remove_task_lock(business_id)
        raise e

@celery_app.task
def cleanup_old_files():
    """
    定時清理任務：刪除超過 24 小時的檔案。
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    upload_dir = os.getenv("UPLOAD_DIR", os.path.join(base_dir, "uploads"))
    if not os.path.exists(upload_dir): return
        
    now = time.time()
    retention_period = 24 * 3600
    
    locked_ids = set()
    for filename in os.listdir(upload_dir):
        if filename.endswith(".lock"):
            locked_ids.add(filename.replace(".lock", ""))
            
    for filename in os.listdir(upload_dir):
        if filename.endswith(".lock"):
            continue
            
        # B) 高風險修復：更精準的鎖定比對
        is_locked = False
        for bid in locked_ids:
            if filename.startswith(f"{bid}_") or filename.startswith(bid + "."):
                is_locked = True
                break
        if is_locked:
            continue
            
        file_path = os.path.join(upload_dir, filename)
        if now - os.path.getmtime(file_path) > retention_period:
            try:
                if os.path.isdir(file_path):
                    shutil.rmtree(file_path)
                else:
                    os.remove(file_path)
            except Exception as e:
                print(f"Cleanup failed for {file_path}: {e}")
