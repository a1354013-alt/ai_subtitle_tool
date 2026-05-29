"""
Backwards-compatibility module.

Prefer importing from `backend.utils.subtitle_text_utils` going forward.
"""

from .subtitle_text_utils import generate_srt, parse_srt, srt_to_vtt

__all__ = ["generate_srt", "parse_srt", "srt_to_vtt"]
