from __future__ import annotations

import subprocess
from collections.abc import Sequence


MAX_STDERR_SUMMARY_CHARS = 500


class MediaProcessError(RuntimeError):
    def __init__(self, message: str, *, stderr: str = "", returncode: int | None = None):
        super().__init__(message)
        self.stderr = stderr
        self.returncode = returncode


class MediaProcessTimeout(MediaProcessError):
    pass


def summarize_stderr(stderr: str | bytes | None, *, limit: int = MAX_STDERR_SUMMARY_CHARS) -> str:
    if stderr is None:
        return ""
    text = stderr.decode(errors="replace") if isinstance(stderr, bytes) else stderr
    text = text.strip()
    return f"{text[:limit]}..." if len(text) > limit else text


def run_media_command(
    cmd: Sequence[str],
    *,
    timeout: int,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(cmd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=check,
        )
    except subprocess.TimeoutExpired as exc:
        stderr = summarize_stderr(exc.stderr)
        detail = f" stderr={stderr}" if stderr else ""
        raise MediaProcessTimeout(f"Media command timed out after {timeout}s: {cmd[0]}{detail}", stderr=stderr) from exc
    except subprocess.CalledProcessError as exc:
        stderr = summarize_stderr(exc.stderr)
        raise MediaProcessError(
            f"Media command failed: {stderr or exc}",
            stderr=stderr,
            returncode=exc.returncode,
        ) from exc
