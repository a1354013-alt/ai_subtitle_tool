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
- **One-click development setup** with F5 in VS Code or command-line scripts.

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

## Quick Start: One-Click Development (Recommended)

### Method 1: VS Code F5 (Fastest)

1. **Clone and open** the project in VS Code
2. **Press F5** to launch the full development stack
3. Wait for the terminal to show:
   ```
   [BACKEND] Application startup complete
   [FRONTEND] VITE ready in ...
   [WORKER] ready
   ```
4. Open [http://localhost:5173](http://localhost:5173)

**What happens automatically:**
- Python virtual environment created (`.venv/`)
- Backend and frontend dependencies installed
- `.env` file created from `.env.example`
- Redis, backend API, and frontend dev server started in background
- All subprocesses managed and stopped together with Ctrl+C

### Method 2: Command Line

```bash
# One-time setup
python scripts/dev_bootstrap.py

# Start development stack
python scripts/dev_start.py
```

Then open [http://localhost:5173](http://localhost:5173)

### Method 3: Docker Compose (If Docker Available)

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
docker compose up --build
```

Services:

- Frontend: [http://localhost:5173](http://localhost:5173)
- Backend API: [http://localhost:9091](http://localhost:9091)
- Backend health: [http://localhost:9091/healthz](http://localhost:9091/healthz)

**Notes:**
- `docker-compose.yml` uses `backend/.env.example` as the default backend env source
- The frontend Docker image is built with `VITE_API_BASE_URL=http://localhost:9091`
- Runtime artifacts mounted to `backend/uploads`, `backend/outputs`, `backend/tmp`

## Quick Start: Docker Compose (Legacy)

## Local Development: Backend

## Local Development: Frontend

> **Note:** If using VS Code or `scripts/dev_start.py`, skip this section. It's for advanced users who prefer manual control.

### Backend

Requirements:

- Python 3.11
- Redis (running separately)
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

Run the backend stack (in separate terminals):

```bash
# Terminal 1: Redis
redis-server

# Terminal 2: Celery worker
celery -A backend.celery_app:celery_app worker --loglevel=info

# Terminal 3: Backend API
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Health endpoints:

- `GET /healthz`
- `GET /readyz`
- `GET /api/config`

### Frontend

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

## Local Development: Backend

## Local Development: Frontend

## Testing

Backend:

```bash
python -m pytest -q
python -m compileall backend tests scripts
```

Frontend:

```bash
cd frontend
npm ci
npm audit
npm run lint
npm run typecheck
npm run test:ci
npm run build
```

Notes:

- `npm test` starts Vitest watch mode for local development.
- `npm run test:ci` is the CI-safe, non-watch command and must exit on its own.

Docker contract:

```bash
python scripts/verify_docker_config.py
docker compose config
docker compose up --build
```

Benchmark smoke:

```bash
python benchmarks/run_benchmarks.py --smoke
```

`--smoke` is CI-safe and does not download Whisper models. For local machine-specific measurements, see [benchmarks/performance_report.md](benchmarks/performance_report.md).

## Release Packaging

Use the Python script as the single source of truth:

```bash
python scripts/make_release_zip.py --out release.zip --check
```

End-to-end delivery verification:

```bash
python scripts/verify_delivery.py --zip-only
python scripts/verify_delivery.py --full
```

`--zip-only` validates docs, Docker/release inputs, and the clean release archive.
`--full` additionally runs Python compile checks, backend pytest, frontend `npm ci`, `lint`, `typecheck`, `test:ci`, `build`, then rebuilds and verifies `release.zip`.

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

Backend example: [backend/.env.example](backend/.env.example)

Important variables:

- `APP_ENV`
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
- `FFMPEG_PRESET`
- `STORAGE_BACKEND`
- `S3_ENDPOINT`
- `S3_ACCESS_KEY`
- `S3_SECRET_KEY`
- `S3_REGION`
- `S3_BUCKET`

Frontend example: [frontend/.env.example](frontend/.env.example)

- `VITE_API_BASE_URL`
- `VITE_APP_TITLE`

## Translation & OpenAI Configuration

### Transcribe Mode (Original Language Only)

To generate subtitles in the original language only (no translation):

1. **No OpenAI API Key needed**
2. Leave `OPENAI_API_KEY` empty or unset in `.env`
3. Upload with single target language (e.g., "Original")
4. System will transcribe video to text without translation

### Translate Mode (Requires OpenAI API Key)

To generate subtitles in multiple languages (original + translations):

1. **Get OpenAI API Key** from [https://platform.openai.com/api-keys](https://platform.openai.com/api-keys)
2. Set in `backend/.env`:
   ```ini
   OPENAI_API_KEY=sk-...
   OPENAI_MODEL=gpt-4o-mini
   TRANSLATE_MODEL=gpt-4o-mini
   ```
3. Upload with multiple target languages (e.g., "Traditional Chinese, English")
4. System will transcribe AND translate subtitles

### Configuration Check

Call `/api/config` to check current status:

```bash
curl http://localhost:8000/api/config | jq .
```

Response includes:
- `translationEnabled`: true if `OPENAI_API_KEY` is set
- `openaiConfigured`: true if API key is valid
- `availableModes`: list of available modes (`["transcribe"]` or `["transcribe", "translate"]`)

If translation is not configured, uploading with multiple languages will fail with a clear error message.

## Known Limitations

- End-to-end media processing still depends on local `ffmpeg`, Redis, and a running Celery worker.
- Real transcription and translation are mocked in tests; the default suite does not call external APIs.
- Batch ZIP names include the sanitized original filename, task id, and language suffix to avoid collisions when multiple target languages are generated.
- Batch ZIP includes VTT subtitles generated from SRT using the same conversion path as single-file VTT downloads.
- **S3 storage is experimental**; local file storage is the default and fully supported.

## Portfolio Highlights

- Strong API contract coverage between FastAPI and Vue.
- Delivery verification script checks docs, env examples, Docker config, release ZIP contents, tests, and frontend build steps.
- Stable release packaging uses one Python implementation and a thin PowerShell wrapper, which avoids duplicated exclusion rules.

Batch ZIP naming:

- Subtitle files use `{safe_original_filename}_{task_id}_{language}.srt`
- Subtitle files use `{safe_original_filename}_{task_id}_{language}.ass`
- Subtitle files use `{safe_original_filename}_{task_id}_{language}.vtt`
- Final video uses `{safe_original_filename}_{task_id}.mp4`
