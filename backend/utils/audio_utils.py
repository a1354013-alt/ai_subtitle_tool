import logging

from backend import settings
from backend.utils.media_process import MediaProcessError, run_media_command

logger = logging.getLogger(__name__)


def preprocess_audio(video_path: str, output_audio_path: str):
    """Extract mono 16 kHz audio with denoise filters and a basic fallback."""
    command = [
        settings.FFMPEG_BINARY,
        "-y",
        "-i",
        video_path,
        "-vn",
        "-af",
        "afftdn,highpass=f=200,lowpass=f=3000,loudnorm",
        "-ar",
        "16000",
        "-ac",
        "1",
        output_audio_path,
    ]

    try:
        run_media_command(command, check=True, timeout=settings.FFMPEG_TIMEOUT_SECONDS)
        return output_audio_path
    except MediaProcessError as e:
        logger.warning("Audio preprocessing failed; falling back to basic ffmpeg. stderr=%s", e.stderr)
        fallback_command = [
            settings.FFMPEG_BINARY,
            "-y",
            "-i",
            video_path,
            "-vn",
            "-ar",
            "16000",
            "-ac",
            "1",
            output_audio_path,
        ]
        try:
            run_media_command(fallback_command, check=True, timeout=settings.FFMPEG_TIMEOUT_SECONDS)
        except MediaProcessError:
            logger.exception("Audio preprocessing fallback ffmpeg failed")
            raise
        return output_audio_path
