import os
import torch
from pyannote.audio import Pipeline

def diarize_audio(audio_path: str, hf_token: str):
    """
    執行說話者偵測 (Diarization)
    """
    if not hf_token:
        return []
        
    try:
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=hf_token
        )
        
        # 偵測 GPU
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        pipeline.to(device)
        
        diarization = pipeline(audio_path)
        
        speaker_segments = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            speaker_segments.append({
                "start": turn.start,
                "end": turn.end,
                "speaker": speaker
            })
        return speaker_segments
    except Exception as e:
        print(f"Diarization error: {e}")
        return []

def merge_speaker_info(whisper_segments, speaker_segments):
    """
    將說話者資訊合併到 Whisper 的字幕片段中
    支援 whisper_segments 為物件 (有 .start/.end) 或字典格式
    """
    if not speaker_segments:
        return whisper_segments
        
    for seg in whisper_segments:
        # 支援物件與字典
        s_start = seg.start if hasattr(seg, 'start') else seg['start']
        s_end = seg.end if hasattr(seg, 'end') else seg['end']
        s_text = seg.text if hasattr(seg, 'text') else seg['text']
        
        seg_mid = (s_start + s_end) / 2
        
        # 尋找中點落在其中的說話者區段
        current_speaker = "Unknown"
        for spk in speaker_segments:
            if spk['start'] <= seg_mid <= spk['end']:
                current_speaker = spk['speaker']
                break
        
        # 更新文字內容
        speaker_tag = f"[{current_speaker}]: "
        new_text = speaker_tag + s_text.strip()
        
        if hasattr(seg, 'text'):
            seg.text = new_text
        else:
            seg['text'] = new_text
            
    return whisper_segments
