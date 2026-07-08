import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _load_pyannote_pipeline(hf_token: str):
    from pyannote.audio import Pipeline

    try:
        return Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            token=hf_token,
        )
    except TypeError as exc:
        logger.debug("pyannote Pipeline.from_pretrained(token=...) failed; retrying use_auth_token=...", exc_info=True)
        try:
            return Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=hf_token,
            )
        except TypeError:
            raise exc


def diarize_audio(audio_path: str, hf_token: str) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Run optional speaker diarization with pyannote."""
    if not hf_token:
        return [], "Diarization skipped: HF_TOKEN not set"

    try:
        import torch

        pipeline = _load_pyannote_pipeline(hf_token)
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        pipeline.to(device)

        diarization = pipeline(audio_path)

        speaker_segments = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            speaker_segments.append(
                {
                    "start": turn.start,
                    "end": turn.end,
                    "speaker": speaker,
                }
            )
        return speaker_segments, None
    except ImportError:
        logger.warning("pyannote diarization dependency is unavailable", exc_info=True)
        return [], "Diarization skipped: optional dependency 'pyannote.audio' is not installed"
    except TypeError:
        logger.exception("pyannote diarization API compatibility error")
        return [], "Diarization failed: pyannote pipeline API is incompatible with this environment (see server logs for details)"
    except Exception:
        logger.exception("pyannote diarization error")
        return [], "Diarization failed: pyannote pipeline inference error (see server logs for details)"


def merge_speaker_info(whisper_segments, speaker_segments):
    """Prefix each Whisper segment with the speaker label matching its midpoint."""
    if not speaker_segments:
        return whisper_segments

    for seg in whisper_segments:
        s_start = seg.start if hasattr(seg, "start") else seg["start"]
        s_end = seg.end if hasattr(seg, "end") else seg["end"]
        s_text = seg.text if hasattr(seg, "text") else seg["text"]

        seg_mid = (s_start + s_end) / 2

        current_speaker = "Unknown"
        for spk in speaker_segments:
            if spk["start"] <= seg_mid <= spk["end"]:
                current_speaker = spk["speaker"]
                break

        speaker_tag = f"[{current_speaker}]: "
        new_text = speaker_tag + s_text.strip()

        if hasattr(seg, "text"):
            seg.text = new_text
        else:
            seg["text"] = new_text

    return whisper_segments
