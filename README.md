# AI Subtitle Tool

## Project Overview

AI Subtitle Tool is a delivery-focused subtitle workflow for video uploads. It provides a FastAPI backend, Celery worker, Redis queue, and a Vue 3 frontend for upload, status polling, subtitle editing, batch processing, and result download.

## Features

- Single-file upload with task polling.
- Batch upload with ZIP download of completed results.
- Subtitle editing for `srt` and `ass`.
- Explicit final-video rebuild after subtitle edits.
- Frontend-safe task status contract with `warnings`, `error_code`, and `suggestion`.
- Release packaging script that excludes local secrets and runtime artifacts.

## Architecture

```mermaid
flowchart LR
  U["Browser"] -->|HTTP| F["Vue 3 Frontend"]
  F -->|HTTP| B["FastAPI Backend"]
  B -->|enqueue| R["Redis"]
  W["Celery Worker"] -->|consume| R
  B -->|read/write| S["Upload Storage"]
  W -->|read/write| S
```

## Quick Start: Docker Compose

Docker Compose is the fastest way to run the full stack locally.

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
docker compose config
docker compose up --build
```

Services:

- Frontend: [http://localhost:5173](http://localhost:5173)
- Backend API: [http://localhost:9091](http://localhost:9091)
- Backend health: [http://localhost:9091/healthz](http://localhost:9091/healthz)

Notes:

- `docker-compose.yml` uses `backend/.env.example` as the default backend env source so `docker compose up` works out of the box.
- The frontend Docker image is built with `VITE_API_BASE_URL=http://localhost:9091` so browser requests hit the mapped backend port.
- Runtime artifacts are mounted to `backend/uploads`, `backend/outputs`, and `backend/tmp`.

## Local Development: Backend

Requirements:

- Python 3.11
- Redis
- `ffmpeg` and `ffprobe`

Setup:

```bash
python -m venv venv
# Windows: venv\Scripts\activate
# macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
cp backend/.env.example backend/.env
```

Recommended local overrides inside `backend/.env`:

```ini
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
UPLOAD_DIR=./backend/uploads
OUTPUT_DIR=./backend/outputs
TEMP_DIR=./backend/tmp
```

Run the backend stack:

```bash
redis-server
celery -A backend.celery_app:celery_app worker --loglevel=info
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Health endpoints:

- `GET /healthz`
- `GET /readyz`
- `GET /api/config`

## Local Development: Frontend

```bash
cd frontend
npm ci
cp .env.example .env
npm run dev
```

Frontend env:

```ini
VITE_API_BASE_URL=http://localhost:8000
VITE_APP_TITLE=AI Subtitle Tool
```

## Testing

Backend:

```bash
python scripts/verify_delivery.py --full
cd backend
python -m pytest -q
```

Frontend:

```bash
cd frontend
npm ci
npm run lint
npm run typecheck
npm run test
npm run build
```

Docker contract:

```bash
docker compose config
docker compose up --build
```

## Release Packaging

Use the Python script as the single source of truth:

```bash
python scripts/make_release_zip.py --out release.zip --check
```

PowerShell wrapper:

```powershell
powershell -ExecutionPolicy Bypass -File .\make_release_zip.ps1
```

The release ZIP keeps:

- `backend/.env.example`
- `frontend/.env.example`
- `README.md`
- `DEPLOYMENT.md`
- `docker-compose.yml`
- `backend/Dockerfile`
- `frontend/Dockerfile`
- test files

The release ZIP excludes:

- `.git/`
- `node_modules/`
- `dist/`
- `build/`
- `__pycache__/`
- `.pytest_cache/`
- `.venv/`
- `venv/`
- `.env`
- `.env.local`
- `backend/.env`
- `frontend/.env`
- `*.key`
- `*.pem`
- `secrets.*`
- `uploads/`
- `outputs/`
- `temp/`
- `tmp/`

## Environment Variables

Backend example: [backend/.env.example](/C:/Users/whois/OneDrive/文件/GitHub/ai_subtitle_tool/backend/.env.example)

Important variables:

- `ENVIRONMENT`
- `API_HOST`
- `API_PORT`
- `CORS_ORIGINS`
- `UPLOAD_DIR`
- `OUTPUT_DIR`
- `TEMP_DIR`
- `MAX_UPLOAD_SIZE_MB`
- `MAX_BATCH_FILES`
- `REDIS_URL`
- `CELERY_BROKER_URL`
- `CELERY_RESULT_BACKEND`
- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `TRANSLATE_MODEL`
- `WHISPER_MODEL`
- `FFMPEG_BINARY`
- `FFPROBE_BINARY`

Frontend example: [frontend/.env.example](/C:/Users/whois/OneDrive/文件/GitHub/ai_subtitle_tool/frontend/.env.example)

- `VITE_API_BASE_URL`
- `VITE_APP_TITLE`

## Known Limitations

- End-to-end media processing still depends on local `ffmpeg`, Redis, and a running Celery worker.
- Real transcription and translation are mocked in tests; the default suite does not call external APIs.
- Batch ZIP names include the sanitized original filename, task id, and language suffix to avoid collisions when multiple target languages are generated.

## Portfolio Highlights

- Strong API contract coverage between FastAPI and Vue.
- Delivery verification script checks docs, env examples, release ZIP contents, tests, and frontend build steps.
- Stable release packaging uses one Python implementation and a thin PowerShell wrapper, which avoids duplicated exclusion rules.

Batch ZIP naming:

- Subtitle files use `{safe_original_filename}_{task_id}_{language}.srt`
- Subtitle files use `{safe_original_filename}_{task_id}_{language}.ass`
- Subtitle files use `{safe_original_filename}_{task_id}_{language}.vtt`
- Final video uses `{safe_original_filename}_{task_id}.mp4`
