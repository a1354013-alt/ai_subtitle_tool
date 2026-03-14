import os
from pyannote.audio import Pipeline
import torch

def run_diarization(audio_path: str, auth_token: str = None):
    """
    執行說話者偵測。注意：這需要 HuggingFace 的 Token 且需同意 pyannote 的使用條款。
    如果沒有 Token，此功能將回傳空結果。
    """
    if not auth_token:
        print("No HuggingFace token provided for diarization. Skipping...")
        return None
        
    try:
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=auth_token
        )
        
        # 使用 GPU (如果可用)
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
        print(f"Diarization failed: {e}")
        return None

def merge_speaker_info(whisper_segments, speaker_segments):
    """
    將 Whisper 的文字片段與說話者資訊合併
    """
    if not speaker_segments:
        return whisper_segments
        
    for seg in whisper_segments:
        # 尋找重疊時間最長的說話者
        seg_mid = (seg['start'] + seg['end']) / 2
        for spk in speaker_segments:
            if spk['start'] <= seg_mid <= spk['end']:
                seg['speaker'] = spk['speaker']
                seg['text'] = f"[{spk['speaker']}]: {seg['text'].strip()}"
                break
    return whisper_segments
