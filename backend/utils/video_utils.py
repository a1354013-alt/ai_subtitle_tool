import os
import subprocess
import re
import logging

logger = logging.getLogger(__name__)

def has_audio(video_path):
    """檢查影片是否有音軌"""
    cmd = ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", video_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return len(result.stdout.strip()) > 0

def get_video_duration(video_path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return float(result.stdout.strip())

def get_hwaccel_params():
    """
    偵測環境並回傳 FFmpeg 硬體加速參數
    """
    # 1. 檢查 NVIDIA GPU (NVENC)
    try:
        res = subprocess.run(["ffmpeg", "-encoders"], capture_output=True, text=True)
        if "h264_nvenc" in res.stdout:
            logger.info("Hardware acceleration detected: NVIDIA NVENC")
            return ["-c:v", "h264_nvenc", "-preset", "p4"] # p4 is a good balance for NVENC
    except Exception:
        pass

    # 2. 檢查 Intel QuickSync (QSV)
    try:
        if "h264_qsv" in res.stdout:
            logger.info("Hardware acceleration detected: Intel QSV")
            return ["-c:v", "h264_qsv", "-preset", "veryfast"]
    except Exception:
        pass

    # 3. 檢查 macOS VideoToolbox
    try:
        if "h264_videotoolbox" in res.stdout:
            logger.info("Hardware acceleration detected: macOS VideoToolbox")
            return ["-c:v", "h264_videotoolbox", "-b:v", "5M"] # VideoToolbox often needs bitrate
    except Exception:
        pass

    # Fallback to CPU (libx264)
    logger.info("No hardware acceleration detected, falling back to CPU (libx264)")
    return ["-c:v", "libx264", "-preset", "ultrafast"]

def remove_silence(input_path, output_path, noise_threshold=-30, min_silence_duration=0.5):
    """
    使用 FFmpeg silencedetect 偵測靜音並移除
    """
    duration = get_video_duration(input_path)
    audio_exists = has_audio(input_path)
    
    if not audio_exists:
        raise RuntimeError("No audio stream found in video")

    cmd = [
        "ffmpeg", "-i", input_path,
        "-af", f"silencedetect=noise={noise_threshold}dB:d={min_silence_duration}",
        "-f", "null", "-"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    output = result.stderr

    silence_starts = [float(x) for x in re.findall(r"silence_start: ([\d\.]+)", output)]
    silence_ends = [float(x) for x in re.findall(r"silence_end: ([\d\.]+)", output)]
    
    if not silence_starts:
        subprocess.run(["ffmpeg", "-y", "-i", input_path, "-c", "copy", output_path], check=True)
        return output_path

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

    if not keep_segments:
        subprocess.run(["ffmpeg", "-y", "-i", input_path, "-c", "copy", output_path], check=True)
        return output_path

    video_filters = ""
    audio_filters = ""
    for i, (start, end) in enumerate(keep_segments):
        video_filters += f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS[v{i}];"
        audio_filters += f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a{i}];"
    
    concat_v = "".join([f"[v{i}]" for i in range(len(keep_segments))])
    concat_a = "".join([f"[a{i}]" for i in range(len(keep_segments))])
    
    filter_complex = f"{video_filters}{audio_filters}{concat_v}concat=n={len(keep_segments)}:v=1:a=0[outv];{concat_a}concat=n={len(keep_segments)}:v=0:a=1[outa]"
    
    hw_params = get_hwaccel_params()
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[outa]",
        *hw_params, "-c:a", "aac",
        output_path
    ]
    subprocess.run(cmd, check=True)
    return output_path

def burn_subtitles(video_path, subtitle_path, output_path):
    """
    燒錄字幕到影片中。
    """
    abs_subtitle_path = os.path.abspath(subtitle_path).replace("\\", "/").replace(":", "\\:")
    hw_params = get_hwaccel_params()
    
    # 第一階段：嘗試硬體加速或快速燒錄
    cmd_fast = [
        "ffmpeg", "-y", "-i", video_path,
        "-vf", f"subtitles='{abs_subtitle_path}':force_style='FontSize=12,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=1,Shadow=0,Alignment=2'",
        *hw_params, "-c:a", "aac",
        output_path
    ]
    
    try:
        subprocess.run(cmd_fast, check=True)
        return output_path
    except subprocess.CalledProcessError:
        # 第二階段：保守參數 Fallback (CPU)
        logger.warning("Fast burn failed, falling back to conservative CPU encoding")
        cmd_fallback = [
            "ffmpeg", "-y", "-i", video_path,
            "-vf", f"subtitles='{abs_subtitle_path}':force_style='FontSize=12,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=1,Shadow=0,Alignment=2'",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            output_path
        ]
        subprocess.run(cmd_fallback, check=True)
        return output_path
