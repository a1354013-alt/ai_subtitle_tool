# Test Plan

This repo aims for a small but reliable test suite that validates:

- backend HTTP contracts (upload/status/results/subtitle/download)
- backend safety invariants (path traversal containment, atomic writes)
- frontend routing + key UI states (happy path + common errors)
- release packaging is clean and reproducible

---

## Backend tests

Run:

```bash
pytest
```

Scope:

- FastAPI integration tests using `TestClient`
- Contract coverage for core endpoints:
  - `POST /upload`
  - `GET /status/{task_id}`
  - `GET /results/{task_id}`
  - `GET /subtitle/{task_id}` and `PUT /subtitle/{task_id}`
  - `GET /download/{task_id}`
- Warning policy:
  - Deprecation warnings from **our code** are treated as errors.
  - Known third-party deprecation noise is filtered precisely (not a blanket ignore).

Notes:

- Integration tests stub Celery/ffprobe interactions so they are deterministic and do not require a running Redis/worker.
- Full end-to-end video processing is intentionally excluded from unit/CI tests due to runtime cost; it is covered by manual smoke checks.

---

## Frontend tests

Run:

```bash
cd frontend
npm ci
npm run typecheck
npm run lint
npm run test:ci
npm run build
```

Scope:

- Route smoke tests (Home / TaskStatus / Subtitle / Download / RecentTasks)
- Component behavior tests for:
  - error states (not found, failed task, missing subtitle)
  - status polling UI states and warnings rendering

---

## Release package checks

Release zip must be built via script only:

```bash
python scripts/verify_delivery.py
```

The check fails if the zip contains:

- `.git/`, `node_modules/`, `dist/`
- runtime outputs (`uploads/`, `segments/`)
- caches (`__pycache__/`, `.pytest_cache/`, `.coverage`, `htmlcov/`, etc.)
- local env files (`.env`, `.env.*`, `*.env` except `.env.example`)

---

## Manual smoke checks (recommended before tagging a release)

Local (3 terminals):

```bash
redis-server
celery -A backend.celery_app:celery_app worker --loglevel=info
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Frontend:

```bash
cd frontend
npm ci
npm run dev
```

Then:

- Upload a short MP4
- Verify status progresses to `SUCCESS`
- Verify results show subtitles + final video
- Edit a subtitle line and verify the UI reflects updated content
- Download final video and subtitle files
