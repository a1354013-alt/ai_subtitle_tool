# Test Plan

This project aims to keep delivery reproducible and batch processing stable.

## Backend

Run:

```bash
python -m pytest -q
```

Coverage focus:

- `POST /upload` and `POST /batch/upload` share the same validation rules
- invalid extension, content type, subtitle format, empty `target_langs`, and ffprobe failures are rejected before enqueue
- `GET /batch/{batch_id}/status` preserves failed task metadata and emits `/download/{task_id}` URLs
- batch metadata keeps failed statuses and errors instead of rewriting everything to queued
- docs and env example files required for Docker delivery remain present

## Frontend

Run:

```bash
cd frontend
npm ci
npm run typecheck
npm run lint
npm run test:ci
npm run build
```

Coverage focus:

- batch success state (`SUCCESS`) shows download actions
- failure states (`FAILURE`, `FAILED`, `ERROR`) show failed styling
- processing states (`PROCESSING`, `PENDING`, `STARTED`, `QUEUED`) show in-progress styling
- batch download links use `/download/{task_id}` instead of `/results/{task_id}/download`

## Release Verification

Fast path:

```bash
python scripts/verify_delivery.py --zip-only
```

Checks:

- builds `release.zip`
- blocks forbidden paths and file types
- ensures required repo files exist
- ensures `backend/.env.example` and `frontend/.env.example` are shipped

Full path:

```bash
python scripts/verify_delivery.py --full
```

Adds:

- `python -m pytest -q`
- `cd frontend && npm ci`
- `cd frontend && npm run typecheck`
- `cd frontend && npm run lint`
- `cd frontend && npm run test:ci`
- `cd frontend && npm run build`
