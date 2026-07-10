import re


MAX_SUBTITLE_CONTENT_BYTES = 5 * 1024 * 1024


class SubtitleValidationError(ValueError):
    def __init__(self, message: str, suggestion: str):
        super().__init__(message)
        self.payload = {
            "error_code": "invalid_subtitle_format",
            "message": message,
            "suggestion": suggestion,
        }


_SRT_TIMESTAMP_RE = re.compile(
    r"^(?P<start>\d{2}:\d{2}:\d{2},\d{3})\s+-->\s+(?P<end>\d{2}:\d{2}:\d{2},\d{3})$"
)


def validate_subtitle_content(content: str, subtitle_format: str) -> None:
    if not content or not content.strip():
        raise SubtitleValidationError(
            "Subtitle content must not be empty.",
            "Paste a valid subtitle file before saving.",
        )

    size_bytes = len(content.encode("utf-8"))
    if size_bytes > MAX_SUBTITLE_CONTENT_BYTES:
        raise SubtitleValidationError(
            "Subtitle content exceeds the 5 MB limit.",
            "Reduce the subtitle file size and try again.",
        )

    normalized_format = subtitle_format.lower()
    if normalized_format == "srt":
        _validate_srt(content)
        return
    if normalized_format == "ass":
        _validate_ass(content)
        return
    raise SubtitleValidationError(
        "Unsupported subtitle format.",
        "Save subtitles as ASS or SRT.",
    )


def _parse_srt_timestamp(value: str) -> int:
    hours = int(value[0:2])
    minutes = int(value[3:5])
    seconds = int(value[6:8])
    millis = int(value[9:12])
    if minutes > 59 or seconds > 59:
        raise ValueError("timestamp out of range")
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + millis


def _validate_srt(content: str) -> None:
    lines = [line.strip() for line in content.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    cue_count = 0
    previous_start: int | None = None
    saw_malformed_arrow = False

    for line in lines:
        if "-->" not in line:
            continue

        match = _SRT_TIMESTAMP_RE.match(line)
        if not match:
            saw_malformed_arrow = True
            continue

        try:
            start_ms = _parse_srt_timestamp(match.group("start"))
            end_ms = _parse_srt_timestamp(match.group("end"))
        except ValueError:
            raise SubtitleValidationError(
                "SRT timestamps must use valid HH:MM:SS,mmm values.",
                "Check minute and second values and save again.",
            ) from None

        if start_ms >= end_ms:
            raise SubtitleValidationError(
                "SRT cue start time must be before its end time.",
                "Adjust the cue timestamps so each cue has a positive duration.",
            )

        if previous_start is not None and start_ms < previous_start:
            raise SubtitleValidationError(
                "SRT cue times must not go backwards.",
                "Sort cues by start time before saving.",
            )

        previous_start = start_ms
        cue_count += 1

    if cue_count == 0:
        if saw_malformed_arrow:
            raise SubtitleValidationError(
                "SRT timestamps must use HH:MM:SS,mmm --> HH:MM:SS,mmm.",
                "Fix malformed cue timestamp lines before saving.",
            )
        raise SubtitleValidationError(
            "SRT subtitles must contain at least one cue.",
            "Add at least one numbered cue with timestamps and text.",
        )


def _validate_ass(content: str) -> None:
    lines = [line.strip() for line in content.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    sections = {line.lower() for line in lines if line.startswith("[") and line.endswith("]")}

    required_sections = {
        "[script info]": "[Script Info]",
        "[v4+ styles]": "[V4+ Styles]",
        "[events]": "[Events]",
    }
    for normalized, display in required_sections.items():
        if normalized not in sections:
            raise SubtitleValidationError(
                f"ASS subtitles must contain a {display} section.",
                "Save a complete ASS file with Script Info, V4+ Styles, and Events sections.",
            )

    if not any(line.lower().startswith("dialogue:") for line in lines):
        raise SubtitleValidationError(
            "ASS subtitles must contain at least one Dialogue: line.",
            "Add at least one dialogue event before saving.",
        )
