# Deployment Guide

This document covers local development, Docker startup, and release packaging for the current `ai_subtitle_tool` delivery contract.

## Local Development

### Backend

```bash
python -m venv venv
# Windows: venv\Scripts\activate
# macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
cp backend/.env.example backend/.env
```

Recommended local overrides in `backend/.env`:

```ini
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
UPLOAD_DIR=./backend/uploads
OUTPUT_DIR=./backend/outputs
TEMP_DIR=./backend/tmp
```

Run services:

```bash
redis-server
celery -A backend.celery_app:celery_app worker --loglevel=info
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm ci
cp .env.example .env
npm run dev
```

Default local frontend env:

```ini
VITE_API_BASE_URL=http://localhost:8000
VITE_APP_TITLE=AI Subtitle Tool
```

## Docker Startup

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
docker compose config
docker compose up --build
```

Expected URLs:

- Frontend: `http://localhost:5173`
- Backend: `http://localhost:9091`
- Health: `http://localhost:9091/healthz`

Contract notes:

- `docker-compose.yml` points backend services at `backend/.env.example`.
- The frontend Docker build uses `VITE_API_BASE_URL=http://localhost:9091`.
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
python scripts/verify_delivery.py --full
```
