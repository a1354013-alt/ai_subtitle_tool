# Deployment Guide

This project supports local development, Docker demo deployment, and release zip verification.

## Runtime URLs

- Local backend: `http://localhost:8000`
- Docker backend: `http://localhost:9091`
- Frontend: `http://localhost:5173`

## Prerequisites

- Python 3.11
- Node.js 20
- Redis
- `ffmpeg` and `ffprobe`

## Local Development

1. Copy backend env:

```bash
cp backend/.env.example backend/.env
```

2. Install Python dependencies:

```bash
python -m venv venv
# Windows: venv\Scripts\activate
# macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
```

3. Start services in separate terminals:

```bash
redis-server
celery -A backend.celery_app:celery_app worker --loglevel=info
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

4. Start frontend:

```bash
cd frontend
npm ci
npm run dev
```

5. If the frontend is cross-origin, set `VITE_API_BASE_URL=http://localhost:8000`.

## Docker Demo Deployment

`docker-compose.yml` already references `backend/.env.example`, so this works without copying env files:

```bash
docker compose up --build
```

Services:

- Frontend: `http://localhost:5173`
- Backend API: `http://localhost:9091`
- Backend health: `http://localhost:9091/healthz`

If you want custom secrets, override environment variables or edit a local copy before starting containers.

## Batch Metadata Paths

- Local workspace path: `backend/uploads/batches/{batch_id}.json`
- Docker container path: `/app/uploads/batches/{batch_id}.json`

## Verification

Fast delivery check:

```bash
python scripts/verify_delivery.py --zip-only
```

Full reproducibility check:

```bash
python scripts/verify_delivery.py --full
```

`--full` runs:

- `python -m pytest -q`
- `cd frontend && npm ci`
- `cd frontend && npm run typecheck`
- `cd frontend && npm run lint`
- `cd frontend && npm run test:ci`
- `cd frontend && npm run build`
