import logging
import os
from datetime import timedelta

from moviepy.editor import VideoFileClip

from .audio_utils import preprocess_audio
from .model_loader import get_model, get_model_by_duration

logger = logging.getLogger(__name__)


def format_timestamp(seconds: float) -> str:
    td = timedelta(seconds=seconds)
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    millis = int(td.microseconds / 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def generate_srt(segments) -> str:
    srt_content = ""
    for i, segment in enumerate(segments):
        start = format_timestamp(segment.start)
        end = format_timestamp(segment.end)
        text = segment.text.strip()
        srt_content += f"{i + 1}\n{start} --> {end}\n{text}\n\n"
    return srt_content


def transcribe_video(video_path: str, output_srt_path: str, model_size=None):
    """
    Transcribe a video file into an SRT subtitle file.

    Returns a list of segments with (start, end, text) attributes.
    """
    audio_path = None
    try:
        # 1) Read duration for model selection
        video = VideoFileClip(video_path)
        duration = video.duration
        video.close()

        if model_size is None:
            model_size = get_model_by_duration(duration)

        # 2) Extract audio to a temporary wav
        audio_path = f"{os.path.splitext(video_path)[0]}_temp.wav"
        preprocess_audio(video_path, audio_path)

        # 3) Run Faster-Whisper
        model = get_model(model_size)
        segments, _info = model.transcribe(audio_path, beam_size=5)
        segments_list = list(segments)

        # 4) Write SRT
        srt_content = generate_srt(segments_list)
        with open(output_srt_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(srt_content)

        return segments_list
    finally:
        if audio_path and os.path.exists(audio_path):
            try:
                os.remove(audio_path)
            except OSError:
                logger.warning("Failed to remove temp audio: %s", audio_path, exc_info=True)

