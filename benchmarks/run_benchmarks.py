#!/usr/bin/env python3
"""Safe benchmark and smoke checks for AI Subtitle Tool.

Default benchmark mode is best-effort and marks unavailable media/model checks as
skipped instead of inventing numbers. CI should use ``--smoke``.
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.utils.subtitle_text_utils import srt_to_vtt
from backend.utils.time_utils import format_timestamp


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _result(status: str, **extra):
    return {"status": status, **extra}


def benchmark_timestamp_formatting(iterations: int = 10_000) -> dict:
    test_values = [0.0, 1.5, 60.0, 123.456, 3600.0, 3661.123]
    start = time.perf_counter()
    for _ in range(iterations):
        for value in test_values:
            format_timestamp(value)
    elapsed = time.perf_counter() - start
    return _result(
        "ok",
        iterations=iterations,
        total_operations=iterations * len(test_values),
        elapsed_seconds=round(elapsed, 6),
        microseconds_per_operation=round((elapsed / (iterations * len(test_values))) * 1_000_000, 3),
    )


def smoke_subtitle_conversion() -> dict:
    sample = "1\n00:00:00,000 --> 00:00:01,250\nhello\n"
    vtt = srt_to_vtt(sample)
    if not vtt.startswith("WEBVTT\n\n") or "00:00:00.000 --> 00:00:01.250" not in vtt:
        return _result("failed", reason="SRT to VTT conversion produced unexpected output")
    return _result("ok")


def smoke_ffmpeg_available() -> dict:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        return _result("skipped", reason="ffmpeg/ffprobe unavailable in this environment")
    return _result("ok", ffmpeg=ffmpeg, ffprobe=ffprobe)


def benchmark_model_loading(model_size: str) -> dict:
    try:
        from backend.utils.model_loader import get_faster_whisper_model
    except Exception as exc:
        return _result("skipped", reason=f"model loader unavailable: {exc}")

    start = time.perf_counter()
    try:
        get_faster_whisper_model(model_size)
    except Exception as exc:
        return _result("skipped", reason=f"model '{model_size}' unavailable: {exc}")
    return _result("ok", model=model_size, elapsed_seconds=round(time.perf_counter() - start, 3))


def run_smoke() -> dict:
    return {
        "timestamp_formatting": benchmark_timestamp_formatting(iterations=100),
        "subtitle_conversion": smoke_subtitle_conversion(),
        "ffmpeg": smoke_ffmpeg_available(),
    }


def run_benchmarks(model_size: str) -> dict:
    return {
        "timestamp_formatting": benchmark_timestamp_formatting(),
        "subtitle_conversion": smoke_subtitle_conversion(),
        "ffmpeg": smoke_ffmpeg_available(),
        "model_loading": benchmark_model_loading(model_size),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run safe performance checks for AI Subtitle Tool.")
    parser.add_argument("--smoke", action="store_true", help="Run CI-safe smoke checks only; no model download required.")
    parser.add_argument("--model", default="base", choices=["tiny", "base", "small", "medium", "large"])
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    results = run_smoke() if args.smoke else run_benchmarks(args.model)
    if args.json:
        print(json.dumps(results, indent=2, sort_keys=True))
    else:
        for name, result in results.items():
            logger.info("%s: %s", name, result)

    failed = [name for name, result in results.items() if result.get("status") == "failed"]
    if failed:
        logger.error("benchmark smoke failures: %s", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

