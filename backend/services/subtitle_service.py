from pathlib import Path
from zipfile import ZipFile

from fastapi import HTTPException

from backend.core.paths import validate_path_traversal
from backend.utils.subtitle_text_utils import srt_to_vtt


def load_vtt_from_srt(upload_dir: str, task_id: str, lang_suffix: str, requested_lang: str) -> str:
    srt_path = validate_path_traversal(str(Path(upload_dir) / f"{task_id}_{lang_suffix}.srt"), upload_dir)
    if not Path(srt_path).exists():
        raise HTTPException(
            status_code=404,
            detail=f"Subtitle 'srt' for language '{requested_lang}' not found (required for vtt)",
        )
    return srt_to_vtt(Path(srt_path).read_text(encoding="utf-8"))


def write_vtt_for_srt_to_zip(
    archive: ZipFile,
    srt_path: Path,
    archive_name: str,
) -> None:
    archive.writestr(archive_name, srt_to_vtt(srt_path.read_text(encoding="utf-8")))

