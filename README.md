# AI Subtitle Tool

AI subtitle generation + editing tool with a FastAPI backend (Celery + Redis) and a Vue 3 SPA frontend.

Core workflow (must remain stable):

1. Upload video and options
2. Celery task processes the video
3. Frontend polls task status
4. Results manifest lists available outputs
5. View/edit subtitles (ASS/SRT)
6. Download final video / subtitles

## Tech Stack

- Backend: FastAPI + Uvicorn
- Task queue: Celery + Redis
- Media: ffmpeg / ffprobe
- STT: faster-whisper
- Translation: OpenAI (optional; controlled by env + options)
- Frontend: Vue 3 + Vite + TypeScript + Vue Router + Pinia (SPA)

## Repo Structure

- `backend/`: FastAPI app + Celery tasks
- `frontend/`: Vue 3 SPA
- `tests/`: backend behavior tests (`pytest`)

## Delivery / Clean Package Rules

Do NOT include these in a release package:

- `.git/`
- `frontend/node_modules/`
- `frontend/dist/`
- `tests/_tmp/`
- `__pycache__/` and `*.pyc`
- `backend/uploads/*` (runtime outputs)

This repo includes `make_release_zip.ps1` which stages a clean tree and excludes the above.

## Backend Setup

Requirements:

- Python 3.10–3.12 (recommended)
- `ffmpeg` and `ffprobe`
- Redis

Install:

```bash
python -m venv venv
# Windows: venv\Scripts\activate
# macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
```

Environment variables (example):

```ini
OPENAI_API_KEY=...
REDIS_URL=redis://localhost:6379/0
UPLOAD_DIR=./backend/uploads
HF_TOKEN=...                 # optional
TRANSLATE_MODEL=gpt-4o-mini
CORS_ALLOWED_ORIGINS=*
CORS_ALLOW_CREDENTIALS=false
```

Run services:

```bash
redis-server
celery -A backend.celery_app:celery_app worker --loglevel=info
# optional periodic cleanup
celery -A backend.celery_app:celery_app beat --loglevel=info
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Backend tests:

```bash
pytest
```

## Frontend Setup

The release package must NOT ship with `frontend/node_modules/`.
Always install in a clean environment:

```bash
cd frontend
rm -rf node_modules
npm install
npm run build
npm test
npm run dev
```

### API Base URL

Configure `VITE_API_BASE_URL` (see `frontend/.env.example`).

- If frontend and backend are same-origin: you can omit it.
- If different-origin: set it to the FastAPI origin (e.g. `http://localhost:8000`).

Important: `VITE_API_BASE_URL` affects BOTH:

- API requests (`/upload`, `/status/...`, `/results/...`, `/subtitle/...`)
- Download URLs (`/download/...`)

## Notes

- Subtitle editing updates only the subtitle file; it does NOT rebuild/burn the final video.
- Task status response includes `warnings: string[]` (non-fatal); the frontend shows them separately from errors.
