from pathlib import Path


def test_benchmark_smoke_runs_without_models():
    from benchmarks.run_benchmarks import run_smoke

    results = run_smoke()
    assert results["timestamp_formatting"]["status"] == "ok"
    assert results["subtitle_conversion"]["status"] == "ok"
    assert results["ffmpeg"]["status"] in {"ok", "skipped"}


def test_docker_config_static_verification():
    from scripts.verify_docker_config import verify

    verify(Path(__file__).resolve().parents[1])

