import os
import subprocess
import re

def has_audio(video_path):
    """檢查影片是否有音軌"""
    cmd = ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", video_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return len(result.stdout.strip()) > 0

def get_video_duration(video_path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return float(result.stdout.strip())

def remove_silence(input_path, output_path, noise_threshold=-30, min_silence_duration=0.5):
    """
    使用 FFmpeg silencedetect 偵測靜音並移除
    """
    duration = get_video_duration(input_path)
    audio_exists = has_audio(input_path)
    
    if not audio_exists:
        # 無音軌影片不進行靜音剪輯，直接複製
        subprocess.run(["ffmpeg", "-y", "-i", input_path, "-c", "copy", output_path], check=True)
        return output_path

    # 1. 偵測靜音區段
    cmd = [
        "ffmpeg", "-i", input_path,
        "-af", f"silencedetect=noise={noise_threshold}dB:d={min_silence_duration}",
        "-f", "null", "-"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    output = result.stderr

    # 2. 解析靜音區段 (修正 zip 邏輯，處理有頭無尾的情況)
    silence_starts = [float(x) for x in re.findall(r"silence_start: ([\d\.]+)", output)]
    silence_ends = [float(x) for x in re.findall(r"silence_end: ([\d\.]+)", output)]
    
    if not silence_starts:
        subprocess.run(["ffmpeg", "-y", "-i", input_path, "-c", "copy", output_path], check=True)
        return output_path

    # 補齊 silence_ends (如果最後一段是靜音且沒偵測到 end)
    if len(silence_starts) > len(silence_ends):
        silence_ends.append(duration)

    keep_segments = []
    last_end = 0.0
    
    for start, end in zip(silence_starts, silence_ends):
        if start > last_end:
            keep_segments.append((last_end, start))
        last_end = end
    
    if last_end < duration:
        keep_segments.append((last_end, duration))

    # 3. 建立 FFmpeg filter_complex
    if not keep_segments:
        return input_path

    video_filters = ""
    audio_filters = ""
    for i, (start, end) in enumerate(keep_segments):
        video_filters += f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS[v{i}];"
        audio_filters += f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a{i}];"
    
    concat_v = "".join([f"[v{i}]" for i in range(len(keep_segments))])
    concat_a = "".join([f"[a{i}]" for i in range(len(keep_segments))])
    
    filter_complex = f"{video_filters}{audio_filters}{concat_v}concat=n={len(keep_segments)}:v=1:a=0[outv];{concat_a}concat=n={len(keep_segments)}:v=0:a=1[outa]"
    
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
        output_path
    ]
    subprocess.run(cmd, check=True)
    return output_path

def burn_subtitles(video_path, subtitle_path, output_path):
    abs_subtitle_path = os.path.abspath(subtitle_path).replace("\\", "/").replace(":", "\\:")
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vf", f"subtitles='{abs_subtitle_path}':force_style='FontSize=12,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=1,Shadow=0,Alignment=2'",
        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "copy",
        output_path
    ]
    subprocess.run(cmd, check=True)
    return output_path
