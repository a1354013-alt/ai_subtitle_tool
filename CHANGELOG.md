# Changelog

## 1.0.0-rc3

- Added a shared task-state resolver across status, results, and batch flows so durable terminal history remains authoritative when Redis result metadata is lost.
- Fixed enqueue/history ordering, worker-side terminal timing persistence, rebuild cancellation ownership, CJK font exact-match validation, atomic batch ZIP creation, and parallel segment count preflight.
- Expanded CI with deterministic release ZIP SHA-256 comparison and an opt-in Redis/FFmpeg/CJK integration job.
- Clarified Docker static checks, real Compose smoke validation, CJK integration opt-in behavior, and documentation routes.

## 1.0.0-rc2

- Added durable task-state persistence for progress, terminal status, warnings, errors, result ownership, and timing metadata.
- Added short-lived signed download tickets for protected final-video, subtitle, and batch ZIP downloads.
- Expanded cleanup to use `TASK_CLEANUP_DAYS`, structured counts, dry-run support, batch metadata cleanup, temp/output cleanup, and stale lock removal.
- Added CJK-capable Docker font packages, configurable `SUBTITLE_FONT_NAME`, and readiness diagnostics for font resolution.
- Added worker resource controls, queue separation, batch total-size checks, and parallel segment caps.
- Made release ZIP output deterministic and added reproducibility coverage.
- Updated CI for Python 3.11/3.12, frontend gates, production npm audit, release ZIP verification, and Docker config validation.
