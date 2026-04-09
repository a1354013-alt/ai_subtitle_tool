import os
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

def diarize_audio(audio_path: str, hf_token: str) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    執行說話者偵測 (Diarization)
    """
    if not hf_token:
        return [], "Diarization skipped: HF_TOKEN not set"
        
    try:
        # Optional dependency: only import when diarization is actually requested.
        from pyannote.audio import Pipeline
        import torch

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
        return speaker_segments, None
    except ImportError:
        return [], "Diarization skipped: optional dependency 'pyannote.audio' is not installed"
    except Exception:
        logger.exception("Diarization error")
        return [], "Diarization failed: pipeline inference error (see server logs for details)"

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
