# Benchmark Report Guide

This repository does not include fabricated benchmark numbers. Hardware, model cache state, ffmpeg availability, and worker count all change the results enough that placeholder tables would be misleading.

## CI-Safe Smoke Check

Run the smoke check when you only need to verify benchmark dependencies and utility code are callable:

```bash
python benchmarks/run_benchmarks.py --smoke
```

This mode checks timestamp formatting, SRT-to-VTT conversion, and whether `ffmpeg`/`ffprobe` are available. Missing ffmpeg is reported as `skipped`, not as a fake timing.

## Local Benchmark

Run a local benchmark when the target machine has the model/runtime dependencies installed:

```bash
python benchmarks/run_benchmarks.py --model base --json
```

Interpretation rules:

- `status: ok` means the check ran and the reported number is from the current machine.
- `status: skipped` means a dependency such as a Whisper model, ffmpeg, or optional package was unavailable.
- Do not compare results across machines unless you record CPU/GPU, RAM, storage, OS, Python version, model size, ffmpeg version, Redis/Celery worker count, and whether the model was already cached.

## Reporting Template

When publishing real benchmark results, include:

- Date and commit SHA.
- CPU, GPU if used, RAM, storage type, and OS.
- Python, ffmpeg, Redis, Celery, and faster-whisper versions.
- Model size and whether the model was cold-loaded or cached.
- Worker count and queue settings.
- Input media length, codec, resolution, and audio characteristics.

Keep generated reports outside the release ZIP unless they are curated and reproducible.

