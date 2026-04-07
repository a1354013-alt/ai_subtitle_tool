import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_REQUIRED_SEGMENT_RESULT_KEYS = ("start_offset", "end_offset", "overlap", "segment_idx", "segments")
_REQUIRED_SEGMENT_KEYS = ("start", "end", "text")
_REQUIRED_SEGMENT_DATA_KEYS = ("path", "start_offset", "end_offset", "overlap", "segment_idx")


@dataclass(frozen=True)
class SimpleSegment:
    start: float
    end: float
    text: str


def validate_segment_result_payload(res: dict) -> None:
    if not isinstance(res, dict):
        raise ValueError(f"segment result must be a dict, got {type(res).__name__}")

    missing = [k for k in _REQUIRED_SEGMENT_RESULT_KEYS if k not in res]
    if missing:
        raise ValueError(f"segment result missing keys: {missing}. Expected keys: {list(_REQUIRED_SEGMENT_RESULT_KEYS)}")

    segments = res["segments"]
    if not isinstance(segments, list):
        raise ValueError(f"segment result 'segments' must be a list, got {type(segments).__name__}")

    for idx, seg in enumerate(segments):
        if not isinstance(seg, dict):
            raise ValueError(
                f"segment result 'segments[{idx}]' must be a dict with keys {list(_REQUIRED_SEGMENT_KEYS)}, got {type(seg).__name__}"
            )
        seg_missing = [k for k in _REQUIRED_SEGMENT_KEYS if k not in seg]
        if seg_missing:
            raise ValueError(f"segment result 'segments[{idx}]' missing keys: {seg_missing}")


def prepare_segment_results_for_merge(segment_results: list) -> list:
    """
    finalize_pipeline() 只接受統一格式的 segment payload（dict）。
    在進入 merge_segments_subtitles() 前，於此單一地方轉成 SimpleSegment。
    """
    if not isinstance(segment_results, list):
        raise ValueError(f"segment_results must be a list, got {type(segment_results).__name__}")

    prepared = []
    for res in segment_results:
        validate_segment_result_payload(res)
        prepared.append(
            {
                "start_offset": res["start_offset"],
                "end_offset": res["end_offset"],
                "overlap": res["overlap"],
                "segment_idx": res["segment_idx"],
                "segments": [SimpleSegment(s["start"], s["end"], s["text"]) for s in res["segments"]],
            }
        )
    return prepared


def segments_to_dicts(segments: list) -> list[dict]:
    return [{"start": s.start, "end": s.end, "text": s.text} for s in segments]


def build_full_video_payload(segments: list, duration: float) -> dict:
    """
    非平行流程的統一 payload：讓 finalize_pipeline() 也走同一種格式。
    """
    return {
        "start_offset": 0,
        "end_offset": duration,
        "overlap": 0,
        "segment_idx": 0,
        "segments": segments_to_dicts(segments),
    }


def transcribe_segment(segment_data: dict, model_size: str, transcribe_video_func) -> dict:
    """
    平行分段轉錄的純函式版本，便於測試：
    - 回傳統一的 segment payload（dict）
    - 成功後主動刪除自己的 temp_srt（局部清理）
    """
    if not isinstance(segment_data, dict):
        raise ValueError(f"segment_data must be a dict, got {type(segment_data).__name__}")

    missing = [k for k in _REQUIRED_SEGMENT_DATA_KEYS if k not in segment_data]
    if missing:
        raise ValueError(f"segment_data missing keys: {missing}. Expected keys: {list(_REQUIRED_SEGMENT_DATA_KEYS)}")

    path = segment_data["path"]
    offset = segment_data["start_offset"]
    end_offset = segment_data["end_offset"]
    overlap = segment_data["overlap"]
    segment_idx = segment_data["segment_idx"]

    temp_srt = f"{path}.srt"
    success = False
    try:
        segments = transcribe_video_func(path, temp_srt, model_size=model_size)
        success = True
        return {
            "start_offset": offset,
            "end_offset": end_offset,
            "overlap": overlap,
            "segment_idx": segment_idx,
            "segments": segments_to_dicts(segments),
        }
    finally:
        if success and os.path.exists(temp_srt):
            try:
                os.remove(temp_srt)
            except Exception:
                logger.warning("Failed to remove temp_srt: %s", temp_srt, exc_info=True)

