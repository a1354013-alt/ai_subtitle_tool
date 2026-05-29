from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List

from .time_utils import format_timestamp


@dataclass(frozen=True)
class SrtCue:
    index: int
    start_seconds: float
    end_seconds: float
    text: str


def generate_srt(segments: Iterable) -> str:
    """
    Generate SRT text from a list/iterable of segment-like objects.

    A segment must have:
    - start (seconds)
    - end (seconds)
    - text (string)
    """
    srt_content = ""
    for i, segment in enumerate(segments):
        start = format_timestamp(segment.start)
        end = format_timestamp(segment.end)
        text = str(segment.text or "").strip()
        srt_content += f"{i + 1}\n{start} --> {end}\n{text}\n\n"
    return srt_content


_SRT_TS_RE = re.compile(
    r"^(?P<sh>\d{2}):(?P<sm>\d{2}):(?P<ss>\d{2}),(?P<sms>\d{3})\s*-->\s*(?P<eh>\d{2}):(?P<em>\d{2}):(?P<es>\d{2}),(?P<ems>\d{3})$"
)


def _ts_to_seconds(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + (int(ms) / 1000.0)


def parse_srt(srt_text: str) -> List[SrtCue]:
    """
    Parse SRT into structured cues.

    This is a small utility for validation and integration tests; it intentionally
    stays independent from video/media libraries.
    """
    cues: list[SrtCue] = []
    blocks: list[list[str]] = []
    cur: list[str] = []
    for line in (srt_text or "").splitlines():
        if line.strip() == "":
            if cur:
                blocks.append(cur)
                cur = []
            continue
        cur.append(line.rstrip("\n"))
    if cur:
        blocks.append(cur)

    for block in blocks:
        if len(block) < 2:
            continue
        idx_line = block[0].strip()
        ts_line = block[1].strip()
        if not idx_line.isdigit():
            continue
        m = _SRT_TS_RE.match(ts_line)
        if not m:
            continue
        start_seconds = _ts_to_seconds(m["sh"], m["sm"], m["ss"], m["sms"])
        end_seconds = _ts_to_seconds(m["eh"], m["em"], m["es"], m["ems"])
        text = "\n".join(block[2:]).strip()
        cues.append(SrtCue(index=int(idx_line), start_seconds=start_seconds, end_seconds=end_seconds, text=text))

    return cues


def srt_to_vtt(srt_text: str) -> str:
    """
    Convert SRT text to WebVTT.

    Rules:
    - Remove numeric cue indices
    - Replace timestamp comma with dot
    - Add WEBVTT header
    """
    blocks: list[list[str]] = []
    cur: list[str] = []
    for line in (srt_text or "").splitlines():
        if line.strip() == "":
            if cur:
                blocks.append(cur)
                cur = []
            continue
        cur.append(line.rstrip("\n"))
    if cur:
        blocks.append(cur)

    out_lines = ["WEBVTT", ""]
    for block in blocks:
        if not block:
            continue

        i = 0
        if block[0].strip().isdigit():
            i = 1
        if i >= len(block):
            continue

        ts = block[i].replace(",", ".")
        ts = re.sub(r"\s*-->\s*", " --> ", ts)

        out_lines.append(ts)
        out_lines.extend(block[i + 1 :])
        out_lines.append("")

    return "\n".join(out_lines).rstrip() + "\n"

