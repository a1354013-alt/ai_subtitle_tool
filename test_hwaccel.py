from __future__ import annotations

from backend.utils.video_utils import get_hwaccel_params


def test_hwaccel_detection_returns_safe_ffmpeg_args():
    params = get_hwaccel_params()

    assert isinstance(params, list)
    assert "-c:v" in params
    encoder = params[params.index("-c:v") + 1]
    assert encoder == "libx264"
    assert "-c:a" in params
