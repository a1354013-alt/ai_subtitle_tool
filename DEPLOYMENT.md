# Deployment Guide

This document covers local development, Docker startup, and release packaging for the current `ai_subtitle_tool` delivery contract.

## Local Development

For one-click local development, open the repository root in VS Code and press F5. The default `Run Full Stack Dev` launch starts:

- Frontend: `http://127.0.0.1:5173`
- Backend API docs: `http://127.0.0.1:8891/docs`
- Backend ReDoc: `http://127.0.0.1:8891/redoc`
- Backend health: `http://127.0.0.1:8891/healthz`

F5 creates `.venv` with Python 3.11 or 3.12 when needed, installs `requirements.lock.txt`, runs frontend `npm ci` when needed, creates `backend/.env` and `frontend/.env` from examples, and sets `VITE_API_BASE_URL=http://127.0.0.1:8891`. Redis on `127.0.0.1:6379` is used when available; Docker Redis is tried next; if Redis cannot be started, local F5 uses Celery eager mode and skips the worker.

### Manual Backend

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.lock.txt
cp backend/.env.example backend/.env
```

Python 3.11 or 3.12 is required.
Recommended: Python 3.11
Supported: Python 3.11-3.12
Unsupported: Python 3.13+

Recommended local overrides in `backend/.env`:

```ini
REDIS_URL=redis://127.0.0.1:6379/0
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/1
UPLOAD_DIR=./backend/uploads
OUTPUT_DIR=./backend/outputs
TEMP_DIR=./backend/tmp
TASK_CLEANUP_DAYS=7
SUBTITLE_FONT_NAME=Noto Sans CJK TC
CELERY_WORKER_CONCURRENCY=1
```

Run services:

```bash
redis-server
celery -A backend.celery_app:celery_app worker --loglevel=info
celery -A backend.celery_app:celery_app beat --loglevel=info
uvicorn backend.main:app --host 127.0.0.1 --port 8891 --reload
```

### Manual Frontend

```bash
cd frontend
npm ci
cp .env.example .env
npm run dev
```

Node.js 20.x is required.

Default local frontend env:

```ini
VITE_API_BASE_URL=http://127.0.0.1:8891
VITE_APP_TITLE=AI Subtitle Tool
```

Do not treat `VITE_API_TOKEN` as a protected server secret. If backend token auth is enabled, browser fetch requests may send it as a convenience header, while direct downloads use short-lived signed tickets.

## Docker Startup

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
docker compose config
docker compose up --build
```

Docker starts Redis, API, worker, and a separate Celery beat service. Beat owns scheduled cleanup; the worker is not started with `-B`. The backend image installs fontconfig plus Noto CJK fonts for CJK subtitle burn-in diagnostics.

Expected URLs:

- Frontend: `http://localhost:5173`
- Backend: `http://localhost:9091`
- Health: `http://localhost:9091/healthz`

Contract notes:

- `docker-compose.yml` points backend services at `backend/.env.example`.
- The frontend Docker build uses `VITE_API_BASE_URL=http://localhost:9091`.
- Docker maps backend container port `8000` to external port `9091`; this is separate from local F5 backend port `8891`.
- Runtime directories are mounted under `backend/uploads`, `backend/outputs`, and `backend/tmp`.

## Release Packaging

Canonical command:

```bash
python scripts/make_release_zip.py --out release.zip --check
```

PowerShell wrapper:

```powershell
powershell -ExecutionPolicy Bypass -File .\make_release_zip.ps1
```

Verification command:

```bash
python scripts/verify_docker_config.py
python -m pip install -r requirements.lock.txt
cd frontend
npm ci
cd ..
python scripts/verify_delivery.py --zip-only
python scripts/verify_delivery.py --full
python scripts/make_release_zip.py --out release.zip --check
python scripts/verify_release_zip.py release.zip
```

`python scripts/verify_delivery.py --full` is the pre-release closed-loop check. It runs Python version validation, backend dependency preflight, backend compile/tests, frontend `npm ci`, `lint`, `typecheck`, `test:ci`, `build`, `npm audit --omit=dev`, then rebuilds and re-validates the release zip.

The source CI workflow is `.github/workflows/ci.yml` and is intentionally excluded from release ZIP archives. Its delivery job runs release source validation, release ZIP creation and verification, deterministic ZIP comparison, Docker delivery-contract verification, and `docker compose config`; it does not claim `docker compose up` unless a separate smoke workflow starts containers.

Use [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md) for final `1.0.0-rc3` manual smoke validation. Do not create the stable `v1.0.0` tag until the real Docker, Redis, Celery, FFmpeg, CJK burn-in, download, cancellation, cleanup, and recovery checks have passed.

Real integration smoke remains opt-in. Local process startup should target `http://127.0.0.1:8891`; Docker-based smoke should target `http://127.0.0.1:9091`. For deterministic cancellation coverage, run the worker with `CELERY_WORKER_CONCURRENCY=1`. The integration-only worker hooks used by `scripts/run_real_integration_smoke.py` are disabled unless `INTEGRATION_TEST_MODE=true`.

Recommended local smoke environment:

```bash
export INTEGRATION_TEST_MODE=true
export CELERY_WORKER_CONCURRENCY=1
export UPLOAD_DIR=.integration-runtime/uploads
export OUTPUT_DIR=.integration-runtime/outputs
export TEMP_DIR=.integration-runtime/tmp
export INTEGRATION_WORK_DIR=.integration-runtime/work
python -m pytest -q -m integration tests/test_cjk_burnin_integration.py -ra
python scripts/run_real_integration_smoke.py --base-url http://127.0.0.1:8891
```

The CJK burn-in pytest command and the real integration smoke script are both opt-in because they require live FFmpeg, Redis, Celery, and fontconfig. Generated videos land under `INTEGRATION_WORK_DIR`; task artifacts land under `UPLOAD_DIR`, `OUTPUT_DIR`, and `TEMP_DIR`; backend, worker, and beat logs are the process log files you redirect during startup. Remove `.integration-runtime` after the run to clean the integration workspace.

Local storage is the fully supported storage mode for release deployments. `STORAGE_BACKEND=s3` is experimental; rebuild-final uploads rebuilt `{task_id}_final.mp4` to object storage, subtitle edits attempt to delete stale stored final videos, and `S3_UPLOAD_REQUIRED=true` makes rebuild upload failures fail the task.

If backend dependencies are missing, verification stops before pytest and prints:

```txt
[backend-preflight] Missing backend dependencies: celery, pytest-timeout

Please run:
python -m pip install -r requirements.lock.txt
```

`python scripts/verify_delivery.py --full --ci-fast` and `--full --smoke` are fast-mode aliases. They print a warning banner and may skip expensive checks, so they are not full release verification.
