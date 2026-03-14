import os
import subprocess

def burn_subtitles(video_path: str, srt_path: str, output_video_path: str):
    """
    使用 FFmpeg 將 SRT 字幕燒錄進影片中 (Hardsub)
    """
    # 注意：FFmpeg 的 subtitles 濾鏡路徑在 Windows/Linux 下處理方式不同
    # 這裡針對 Linux 環境，路徑需要進行特殊轉義
    abs_srt_path = os.path.abspath(srt_path).replace("\\", "/").replace(":", "\\:")
    
    command = [
        "ffmpeg", "-y", "-i", video_path,
        "-vf", f"subtitles='{abs_srt_path}':force_style='FontSize=12,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=1,Shadow=0,Alignment=2'",
        "-c:a", "copy", # 音訊直接複製，不重新編碼
        output_video_path
    ]
    
    try:
        subprocess.run(command, check=True, capture_output=True)
        return output_video_path
    except subprocess.CalledProcessError as e:
        print(f"Burning subtitles failed: {e.stderr.decode()}")
        raise e

from moviepy import VideoFileClip, concatenate_videoclips
from moviepy.video.fx import MultiplyVolume

def remove_silence(video_path: str, output_path: str, silence_threshold=0.03, min_silence_len=0.5):
    """
    偵測並移除影片中的靜音片段
    """
    video = VideoFileClip(video_path)
    audio = video.audio
    
    # 獲取音量資訊
    # 這裡簡化處理：將音訊切成小段，計算每段的平均音量
    fps = 20
    chunk_size = 1 / fps
    duration = video.duration
    
    keep_clips = []
    start_time = None
    
    for i in range(int(duration * fps)):
        t = i * chunk_size
        # 獲取該時間點的音量
        vol = audio.subclipped(t, min(t + chunk_size, duration)).to_soundarray(fps=fps)
        if vol.size == 0: continue
        
        avg_vol = (vol**2).mean()**0.5
        
        is_silent = avg_vol < silence_threshold
        
        if not is_silent:
            if start_time is None:
                start_time = t
        else:
            if start_time is not None:
                if t - start_time >= min_silence_len:
                    keep_clips.append(video.subclipped(start_time, t))
                start_time = None
                
    if start_time is not None:
        keep_clips.append(video.subclipped(start_time, duration))
        
    if keep_clips:
        final_video = concatenate_videoclips(keep_clips)
        final_video.write_videofile(output_path, codec="libx264", audio_codec="aac")
        return output_path
    else:
        return video_path # 如果全部都是靜音或沒偵測到，回傳原始影片
