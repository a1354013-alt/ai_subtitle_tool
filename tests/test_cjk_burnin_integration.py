from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.mark.integration
def test_cjk_subtitle_burnin_smoke(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    if os.getenv("RUN_CJK_BURNIN_SMOKE") != "1":
        pytest.skip("Set RUN_CJK_BURNIN_SMOKE=1 to run the real ffmpeg/fontconfig CJK burn-in smoke test.")

    import backend.main as main
    from backend.pipeline_segments import SimpleSegment
    from backend.utils.ass_utils import generate_ass
    from backend.utils.media_process import run_media_command
    from backend.utils.subtitle_video_utils import burn_subtitles

    font_status = main._check_subtitle_font()
    assert font_status["available"], font_status["detail"]

    source = tmp_path / "source.mp4"
    subtitles = tmp_path / "cjk.ass"
    output = tmp_path / "output.mp4"

    run_media_command(
        [
            main.settings.FFMPEG_BINARY,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=320x180:d=1",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-shortest",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(source),
        ],
        timeout=30,
        check=True,
    )
    generate_ass([SimpleSegment(0, 1, "繁體中文 日本語かな漢字 English")], str(subtitles))
    burn_subtitles(str(source), str(subtitles), str(output))

    assert output.exists()
    assert output.stat().st_size > 0
