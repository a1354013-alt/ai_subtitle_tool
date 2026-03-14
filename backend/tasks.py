import os
import time
import shutil
from celery import chord
from celery_app import celery_app
from utils.subtitle_utils import transcribe_video
from utils.video_utils import burn_subtitles, remove_silence
from utils.translate_utils import translate_segments, generate_bilingual_srt
from utils.ass_utils import generate_ass
from utils.split_utils import split_video, merge_segments_subtitles
from utils.model_loader import get_model_by_duration
from utils.diarization_utils import diarize_audio, merge_speaker_info
from moviepy import VideoFileClip

@celery_app.task
def transcribe_segment_task(segment_data: dict, model_size: str):
    """
    子任務：辨識單個影片片段
    """
    path = segment_data['path']
    offset = segment_data['start_offset']
    temp_srt = f"{path}.srt"
    # 執行辨識
    segments = transcribe_video(path, temp_srt, model_size=model_size)
    # 轉換為 dict 格式以利序列化與後續處理
    segment_dicts = []
    for s in segments:
        segment_dicts.append({
            "start": s.start,
            "end": s.end,
            "text": s.text
        })
    return {"start_offset": offset, "segments": segment_dicts}

@celery_app.task(bind=True)
def merge_and_finalize_task(self, segment_results, video_path, options):
    """
    Callback 任務：合併結果並執行後續流程 (翻譯、燒錄等)
    """
    business_id = options.get("business_id")
    target_langs = options.get("target_langs", ["Traditional Chinese"])
    do_burn = options.get("burn_subtitles", True)
    subtitle_format = options.get("subtitle_format", "ass")
    hf_token = options.get("hf_token")
    
    base_path = os.path.splitext(video_path)[0]
    
    # 1. 合併片段結果
    self.update_state(state='PROGRESS', meta={'progress': 40, 'status': 'Merging parallel results...'})
    # 這裡需要一個簡單的 Mock 物件來適配 merge_segments_subtitles
    class SimpleSegment:
        def __init__(self, start, end, text):
            self.start = start
            self.end = end
            self.text = text
            
    adapted_results = []
    for res in segment_results:
        adapted_res = {
            "start_offset": res["start_offset"],
            "segments": [SimpleSegment(s["start"], s["end"], s["text"]) for s in res["segments"]]
        }
        adapted_results.append(adapted_res)
        
    segments = merge_segments_subtitles(adapted_results)
    
    # 清理片段檔案
    segments_dir = f"{base_path}_segments"
    if os.path.exists(segments_dir):
        shutil.rmtree(segments_dir)
    
    # 2. 可選：說話者偵測 (Diarization)
    if hf_token:
        self.update_state(state='PROGRESS', meta={'progress': 50, 'status': 'Performing speaker diarization...'})
        try:
            # 提取音軌進行偵測
            audio_path = f"{base_path}.wav"
            subprocess.run(["ffmpeg", "-y", "-i", video_path, "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", audio_path], check=True)
            diarization_result = diarize_audio(audio_path, hf_token)
            segments = merge_speaker_info(segments, diarization_result)
            if os.path.exists(audio_path): os.remove(audio_path)
        except Exception as e:
            print(f"Diarization failed: {e}")

    # 3. 多語種同步翻譯 (批次處理)
    self.update_state(state='PROGRESS', meta={'progress': 70, 'status': 'Translating (Batch Mode)...'})
    translations = translate_segments(segments, "Auto", target_langs)
    
    # 4. 生成字幕檔案
    self.update_state(state='PROGRESS', meta={'progress': 85, 'status': 'Generating final subtitles...'})
    result_files = {}
    for lang in target_langs:
        lang_suffix = lang.replace(" ", "_")
        bilingual_srt = f"{base_path}_{lang_suffix}.srt"
        generate_bilingual_srt(segments, translations[lang], bilingual_srt)
        
        if subtitle_format == "ass":
            bilingual_ass = f"{base_path}_{lang_suffix}.ass"
            # 建立 ASS 專用 segment 物件
            ass_segments = [SimpleSegment(s.start, s.end, f"{translations[lang][i]}\\N{s.text}") for i, s in enumerate(segments)]
            generate_ass(ass_segments, bilingual_ass)
            result_files[lang] = bilingual_ass
        else:
            result_files[lang] = bilingual_srt

    # 5. 字幕燒錄
    final_video = video_path
    if do_burn:
        self.update_state(state='PROGRESS', meta={'progress': 95, 'status': 'Burning subtitles...'})
        first_lang_file = list(result_files.values())[0]
        final_video = f"{base_path}_final.mp4"
        burn_subtitles(video_path, first_lang_file, final_video)
    
    self.update_state(state='PROGRESS', meta={'progress': 100, 'status': 'Completed'})
    return {"status": "COMPLETED", "business_id": business_id, "video_path": final_video}

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
    
    # 1. 語音辨識 (分段並行處理)
    if parallel and duration > 60:
        self.update_state(state='PROGRESS', meta={'progress': 10, 'status': 'Splitting video for parallel processing...'})
        video_segments = split_video(current_video)
        
        # 使用 chord 建立非阻塞並行鏈路
        header = [transcribe_segment_task.s(seg, model_size) for seg in video_segments]
        callback = merge_and_finalize_task.s(current_video, options)
        chord(header)(callback)
        
        self.update_state(state='PROGRESS', meta={'progress': 20, 'status': f'Parallel tasks dispatched ({len(video_segments)} segments).'})
        return {"status": "DISPATCHED", "parallel": True}
    else:
        # 非並行流程：直接執行辨識與後續
        self.update_state(state='PROGRESS', meta={'progress': 20, 'status': 'Transcribing (Single Worker)...'})
        srt_path = f"{base_path}.srt"
        segments = transcribe_video(current_video, srt_path, model_size=model_size)
        
        # 轉換格式以符合 merge_and_finalize_task 的輸入
        segment_dicts = [{"start": s.start, "end": s.end, "text": s.text} for s in segments]
        return merge_and_finalize_task([{"start_offset": 0, "segments": segment_dicts}], current_video, options)

@celery_app.task
def cleanup_old_files():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    upload_dir = os.getenv("UPLOAD_DIR", os.path.join(base_dir, "uploads"))
    if not os.path.exists(upload_dir): return
        
    now = time.time()
    retention_period = 24 * 3600
    for filename in os.listdir(upload_dir):
        file_path = os.path.join(upload_dir, filename)
        if os.path.isfile(file_path) and now - os.path.getmtime(file_path) > retention_period:
            try:
                if os.path.isdir(file_path): shutil.rmtree(file_path)
                else: os.remove(file_path)
            except: pass
