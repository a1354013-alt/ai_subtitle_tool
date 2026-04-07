import os
import subprocess
from moviepy.editor import VideoFileClip

class SimpleSegment:
    """簡單的字幕段落物件"""
    def __init__(self, start, end, text):
        self.start = start
        self.end = end
        self.text = text

def split_video(video_path: str, segment_length: int = 30, overlap: int = 2):
    """
    將影片切成多個指定長度的片段，含重疊以確保邊界不遺漏。
    
    Args:
        video_path: 影片路徑
        segment_length: 每個片段的長度（秒），default 30
        overlap: 片段間的重疊時間（秒），default 2（用於去重）
    
    Returns:
        list of segment dicts, each containing 'path', 'start_offset', 'end_offset', 'overlap', 'segment_idx'
    
    Raises:
        ValueError: 若 segment_length <= overlap
    """
    # Guard: segment_length 必須大於 overlap
    if segment_length <= overlap:
        raise ValueError(f"segment_length ({segment_length}s) must be > overlap ({overlap}s)")
    
    video = VideoFileClip(video_path)
    duration = video.duration
    video.close()
    
    base_path = os.path.splitext(video_path)[0]
    output_dir = f"{base_path}_segments"
    os.makedirs(output_dir, exist_ok=True)
    
    segments = []
    start = 0
    segment_idx = 0
    
    while start < duration:
        end = min(start + segment_length, duration)
        
        # 避免最後一個片段太短
        if duration - end < 5 and end < duration:
            end = duration
        
        output_file = os.path.join(output_dir, f"seg_{segment_idx:03d}_{start:.0f}_{end:.0f}.mp4")
        
        # 使用 FFmpeg 切片（-c copy 無重新編碼）
        command = [
            "ffmpeg", "-y", "-ss", str(start), "-t", str(end - start),
            "-i", video_path, "-c", "copy", output_file
        ]
        subprocess.run(command, check=True, capture_output=True)
        
        segments.append({
            "path": output_file,
            "start_offset": start,
            "end_offset": end,
            "overlap": overlap,
            "segment_idx": segment_idx
        })
        
        # *** 關鍵修正：當到達影片末端時，直接 break ***
        if end >= duration:
            break
        
        # 帶 overlap 移動起點（僅當未到末端時）
        start = end - overlap
        segment_idx += 1
        
    return segments

def merge_segments_subtitles(segment_results):
    """
    將多個片段的辨識結果合併，並修正時間偏移。
    去除重疊部分的重複字幕。
    
    Args:
        segment_results: list of results from transcribe_segment_task
        
    Returns:
        list of merged subtitle segments
    """
    all_segments = []
    
    # 按照時間偏移排序
    sorted_results = sorted(segment_results, key=lambda x: x['start_offset'])
    
    for result_idx, res in enumerate(sorted_results):
        offset = res['start_offset']
        overlap = res.get('overlap', 0)
        
        for seg in res['segments']:
            # 修正時間偏移
            seg_start = seg.start + offset
            seg_end = seg.end + offset
            
            # 如果不是第一個片段，且在重疊區域內，檢查是否已存在
            if result_idx > 0 and overlap > 0:
                overlap_start = offset
                overlap_end = overlap_start + overlap
                
                # 如果段落完全在重疊區域內，檢查是否已在 all_segments 中
                if seg_start >= overlap_start and seg_end <= overlap_end:
                    # 檢查是否存在時間接近的相同文本
                    found_duplicate = False
                    for existing in all_segments[-10:]:  # 只檢查最後 10 個
                        time_diff = abs(existing.start - seg_start)
                        text_match = existing.text.strip() == seg.text.strip()
                        if time_diff < 0.5 and text_match:
                            found_duplicate = True
                            break
                    
                    if found_duplicate:
                        continue
            
            # 建立新 SimpleSegment 物件
            new_seg = SimpleSegment(seg_start, seg_end, seg.text)
            all_segments.append(new_seg)
    
    # 最後按時間排序
    all_segments.sort(key=lambda x: x.start)
    
    return all_segments
