import logging
import threading

logger = logging.getLogger(__name__)


class ModelLoader:
    """Thread-safe Faster-Whisper model cache."""

    _instances = {}
    _lock = threading.Lock()

    @classmethod
    def get_faster_whisper_model(cls, model_size="base"):
        with cls._lock:
            if model_size not in cls._instances:
                import torch
                from faster_whisper import WhisperModel

                logger.info("Loading Faster-Whisper model: %s", model_size)
                device = "cuda" if torch.cuda.is_available() else "cpu"
                compute_type = "float16" if device == "cuda" else "int8"

                logger.info("Using device=%s compute_type=%s", device, compute_type)
                cls._instances[model_size] = WhisperModel(
                    model_size,
                    device=device,
                    compute_type=compute_type,
                )

            return cls._instances[model_size]


def get_model_by_duration(duration_seconds: float) -> str:
    """Choose a Whisper model by video duration."""
    if duration_seconds < 60:
        return "base"
    if duration_seconds < 600:
        return "small"
    return "medium"


def resolve_model_size(duration_seconds: float, requested_model_size: str | None = None) -> str:
    """Resolve Whisper model priority: task option, environment setting, duration auto-selection."""
    if requested_model_size:
        return requested_model_size

    from .. import settings

    if settings.WHISPER_MODEL:
        return settings.WHISPER_MODEL

    return get_model_by_duration(duration_seconds)


def get_model(model_size="base"):
    return ModelLoader.get_faster_whisper_model(model_size)
