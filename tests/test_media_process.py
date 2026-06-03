import subprocess

import pytest

from backend.utils.media_process import MediaProcessError, MediaProcessTimeout, run_media_command


def test_run_media_command_timeout_preserves_stderr_summary(monkeypatch):
    def _timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd=["ffmpeg"], timeout=1, stderr=b"timed out details")

    monkeypatch.setattr(subprocess, "run", _timeout)

    with pytest.raises(MediaProcessTimeout) as exc_info:
        run_media_command(["ffmpeg", "-version"], timeout=1)

    assert "timed out after 1s" in str(exc_info.value)
    assert exc_info.value.stderr == "timed out details"


def test_run_media_command_failure_preserves_stderr_summary(monkeypatch):
    def _failure(*_args, **_kwargs):
        raise subprocess.CalledProcessError(1, ["ffmpeg"], stderr="bad input")

    monkeypatch.setattr(subprocess, "run", _failure)

    with pytest.raises(MediaProcessError) as exc_info:
        run_media_command(["ffmpeg", "-i", "demo.mp4"], timeout=10, check=True)

    assert "bad input" in str(exc_info.value)
    assert exc_info.value.stderr == "bad input"
