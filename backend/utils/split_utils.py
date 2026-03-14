import os
import subprocess
from moviepy.editor import VideoFileClip

def split_video(video_path: str, segment_length: int = 30):
    """
    將影片切成多個指定長度的片段
    """
    video = VideoFileClip(video_path)
    duration = video.duration
    video.close()
    
    base_path = os.path.splitext(video_path)[0]
    output_dir = f"{base_path}_segments"
    os.makedirs(output_dir, exist_ok=True)
    
    segments = []
    for start in range(0, int(duration), segment_length):
        end = min(start + segment_length, duration)
        output_file = os.path.join(output_dir, f"seg_{start}_{end}.mp4")
        
        # 使用 FFmpeg 快速切片 (不重新編碼)
        command = [
            "ffmpeg", "-y", "-ss", str(start), "-t", str(end - start),
            "-i", video_path, "-c", "copy", output_file
        ]
        subprocess.run(command, check=True, capture_output=True)
        segments.append({
            "path": output_file,
            "start_offset": start
        })
        
    return segments

def merge_segments_subtitles(segment_results):
    """
    將多個片段的辨識結果合併，並修正時間偏移
    """
    all_segments = []
    # 按照時間偏移排序
    sorted_results = sorted(segment_results, key=lambda x: x['start_offset'])
    
    for res in sorted_results:
        offset = res['start_offset']
        for seg in res['segments']:
            # 修正時間偏移
            seg.start += offset
            seg.end += offset
            all_segments.append(seg)
            
    return all_segments
