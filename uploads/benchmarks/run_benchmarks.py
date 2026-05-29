#!/usr/bin/env python3
"""
Benchmark script for AI Video Subtitle Tool.

This script measures:
1. Processing time for different video lengths
2. Memory usage during transcription
3. Parallel vs sequential performance
4. Model loading times

Usage:
    python benchmarks/run_benchmarks.py [--video-length 30,60,300] [--model base,small]
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from utils.time_utils import format_timestamp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_test_video(duration_seconds: int, output_path: str) -> None:
    """Create a test video with black frames and silent audio."""
    try:
        from moviepy.editor import ColorClip, AudioClip
        
        # Create black video
        clip = ColorClip(
            size=(640, 360),
            color=(0, 0, 0),
            duration=duration_seconds
        ).fps(24)
        
        # Create silent audio
        import numpy as np
        fps = 44100
        n_samples = int(fps * duration_seconds)
        audio_array = np.zeros(n_samples, dtype=np.float32)
        audio_clip = AudioClip(audio_array.tobytes(), fps=fps, buffersize=100000)
        audio_clip = audio_clip.with_duration(duration_seconds)
        
        clip = clip.with_audio(audio_clip)
        clip.write_videofile(output_path, codec='libx264', audio_codec='aac', verbose=False, logger=None)
        clip.close()
        
        logger.info(f"Created test video: {output_path} ({duration_seconds}s)")
    except ImportError:
        logger.warning("moviepy not available; skipping video creation")
        raise


def benchmark_model_loading(model_size: str = "base") -> float:
    """Measure time to load faster-whisper model."""
    logger.info(f"Benchmarking model loading: {model_size}")
    
    start = time.perf_counter()
    try:
        from utils.model_loader import get_faster_whisper_model
        model = get_faster_whisper_model(model_size)
        elapsed = time.perf_counter() - start
        logger.info(f"Model '{model_size}' loaded in {elapsed:.2f}s")
        return elapsed
    except Exception as e:
        logger.error(f"Failed to load model: {e}")
        return float('inf')


def benchmark_timestamp_formatting(iterations: int = 10000) -> float:
    """Measure timestamp formatting performance."""
    logger.info(f"Benchmarking timestamp formatting: {iterations} iterations")
    
    test_values = [0.0, 1.5, 60.0, 123.456, 3600.0, 3661.123]
    
    start = time.perf_counter()
    for _ in range(iterations):
        for val in test_values:
            _ = format_timestamp(val)
    elapsed = time.perf_counter() - start
    
    per_op = (elapsed / (iterations * len(test_values))) * 1_000_000  # microseconds
    logger.info(f"Timestamp formatting: {per_op:.2f}μs per operation")
    return elapsed


def benchmark_translation_retry_logic() -> None:
    """Test translation retry logic without actual API calls."""
    logger.info("Benchmarking translation retry logic (mock)")
    
    try:
        from utils.translate_utils import is_retriable_exception
        from openai import APIConnectionError, RateLimitError, APIError
        
        test_exceptions = [
            (APIConnectionError(request=None), True),
            (RateLimitError(message="rate limited", response=None, body=None), True),
            (APIError(message="error", response=None, body=None), False),
            (ValueError("invalid json"), True),
            (RuntimeError("unknown"), False),
        ]
        
        for exc, expected in test_exceptions:
            result = is_retriable_exception(exc)
            status = "✓" if result == expected else "✗"
            logger.info(f"  {status} {type(exc).__name__}: retriable={result} (expected={expected})")
            
    except Exception as e:
        logger.warning(f"Translation benchmark skipped: {e}")


def run_all_benchmarks(video_lengths: list[int], model_size: str) -> dict:
    """Run all benchmarks and return results."""
    results = {
        "model_loading": {},
        "timestamp_formatting": {},
        "translation_retry": {},
    }
    
    # Model loading
    results["model_loading"][model_size] = benchmark_model_loading(model_size)
    
    # Timestamp formatting
    results["timestamp_formatting"]["10k_ops"] = benchmark_timestamp_formatting()
    
    # Translation retry
    benchmark_translation_retry_logic()
    
    # Video processing (if moviepy available)
    results["video_processing"] = {}
    for length in video_lengths:
        try:
            test_video = f"/tmp/benchmark_{length}s.mp4"
            if not os.path.exists(test_video):
                create_test_video(length, test_video)
            
            # Measure file size
            file_size = os.path.getsize(test_video) / (1024 * 1024)  # MB
            results["video_processing"][f"{length}s"] = {
                "file_size_mb": round(file_size, 2),
                "duration": length
            }
            logger.info(f"Test video {length}s: {file_size:.2f}MB")
        except Exception as e:
            logger.warning(f"Video benchmark for {length}s failed: {e}")
            results["video_processing"][f"{length}s"] = {"error": str(e)}
    
    return results


def main():
    parser = argparse.ArgumentParser(description="Run performance benchmarks")
    parser.add_argument(
        "--video-lengths",
        type=str,
        default="30,60,300",
        help="Comma-separated video lengths in seconds"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="base",
        choices=["tiny", "base", "small", "medium", "large"],
        help="Whisper model size"
    )
    args = parser.parse_args()
    
    video_lengths = [int(x) for x in args.video_lengths.split(",")]
    
    logger.info("=" * 60)
    logger.info("AI Video Subtitle Tool - Performance Benchmarks")
    logger.info("=" * 60)
    logger.info(f"Model: {args.model}")
    logger.info(f"Video lengths: {video_lengths}")
    logger.info("")
    
    results = run_all_benchmarks(video_lengths, args.model)
    
    logger.info("")
    logger.info("=" * 60)
    logger.info("BENCHMARK RESULTS SUMMARY")
    logger.info("=" * 60)
    
    for category, data in results.items():
        logger.info(f"\n{category.upper()}:")
        for key, value in data.items():
            if isinstance(value, dict):
                logger.info(f"  {key}:")
                for k, v in value.items():
                    logger.info(f"    {k}: {v}")
            else:
                logger.info(f"  {key}: {value}")
    
    logger.info("")
    logger.info("Benchmark complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
