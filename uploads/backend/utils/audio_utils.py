import os
import subprocess
import logging

logger = logging.getLogger(__name__)

def preprocess_audio(video_path: str, output_audio_path: str):
    """
    使用 FFmpeg 提取音訊並進行降噪處理
    """
    # 提取音訊並應用 lowpass/highpass 濾鏡進行基礎降噪，並標準化音量
    # afftdn 是 FFmpeg 的 FFT 降噪濾鏡
    command = [
        "ffmpeg", "-y", "-i", video_path,
        "-vn", # 不處理影片
        "-af", "afftdn,highpass=f=200,lowpass=f=3000,loudnorm", 
        "-ar", "16000", # Whisper 建議採樣率
        "-ac", "1",     # 單聲道
        output_audio_path
    ]
    
    try:
        subprocess.run(command, check=True, capture_output=True)
        return output_audio_path
    except subprocess.CalledProcessError as e:
        stderr = ""
        try:
            stderr = (e.stderr or b"").decode(errors="replace")
        except Exception:
            stderr = "<decode_failed>"
        logger.warning("Audio preprocessing failed; falling back to basic ffmpeg. stderr=%s", stderr)
        # 如果降噪失敗，嘗試僅提取原始音訊
        fallback_command = ["ffmpeg", "-y", "-i", video_path, "-vn", "-ar", "16000", "-ac", "1", output_audio_path]
        try:
            subprocess.run(fallback_command, check=True, capture_output=True)
        except subprocess.CalledProcessError:
            logger.exception("Audio preprocessing fallback ffmpeg failed")
            raise
        return output_audio_path
