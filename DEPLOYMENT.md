# Deployment Guide (Local / Docker / Release)

This repo supports three modes:

- **Local development** (fast iteration; run Redis/worker/API locally, Vite dev server for UI)
- **Docker deployment** (single `docker compose up` for demo/staging environments)
- **Release package** (a clean zip for delivery; no workspace artifacts)

The frontend **polls** task status via `GET /status/{task_id}` (no WebSocket status endpoint).
Short videos are processed as a single Celery task by default, while longer videos are automatically split into segments and merged after parallel transcription.

---

## 0) Prerequisites

- **Python**: 3.11 (this is the version used by CI and Docker)
- **Node.js**: 20 (CI uses Node 20)
- **System deps**: `ffmpeg` + `ffprobe`
- **Redis**: required for Celery broker/backend

---

## 1) Local development (recommended)

### Backend + worker

1) Create env file:

- Copy `backend/.env.example` to `backend/.env`
- Fill in optional keys (e.g. `OPENAI_API_KEY`) if you want translation

2) Install Python deps:

```bash
python -m venv venv
# Windows: venv\Scripts\activate
# macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
```

Locked media dependency note:

- `requirements.lock.txt` pins `faster-whisper==1.0.3` and `av==12.3.0`.
- This combination keeps Python 3.11 installs reproducible in Docker by using the published PyAV Linux wheel instead of compiling `av==11.0.0` from source against host FFmpeg headers.

3) Start Redis + worker + API (in separate terminals):

```bash
redis-server
celery -A backend.celery_app:celery_app worker --loglevel=info --concurrency=1
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Optional processing tuning:

- `AUTO_SEGMENT_THRESHOLD_SECONDS=60` controls when uploads switch from single-task mode to segmented parallel mode.
- `CELERY_WORKER_CONCURRENCY=1` is the conservative default for local/Docker worker startup.
- If duration probing fails, the worker safely falls back to single-task processing instead of failing the whole job.
- Videos at or below the auto-segmentation threshold stay on the single-task path and do not use Celery `chord`.
- Long videos can still consume significant CPU/RAM during transcription, translation, and subtitle burning, so validate with a short clip first.

Health endpoints:

- `GET /healthz` → `{"status":"ok"}`
- `GET /readyz` → checks Redis + `UPLOAD_DIR` write access

- The Celery worker does not provide an HTTP health endpoint; check `docker compose logs worker` or Celery task status instead.

### Frontend

```bash
cd frontend
npm ci
npm run dev
```

Default dev URLs:

- Frontend: `http://localhost:15174` when using Docker, or Vite's local dev URL when running `npm run dev`
- Backend: `http://localhost:8000`

If frontend and backend are different origins, set `VITE_API_BASE_URL` (see `frontend/.env.example`).

---

## 2) Docker deployment

1) (Optional) Create env file:

- `docker-compose.yml` uses `backend/.env.example` by default so `docker compose up` works out-of-the-box.
- If you want to set real secrets (e.g. `OPENAI_API_KEY`), set them as environment variables or edit a local copy.

2) Run:

```bash
docker compose build backend --no-cache --progress=plain
docker compose build frontend --no-cache --progress=plain
docker compose up
```

Services:

- Frontend (nginx): `http://localhost:15174`
- Backend API: `http://localhost:18000`
- Backend health check: `http://localhost:18000/healthz`
- Redis: `localhost:6379` (host-mapped for convenience)

Notes:

- `UPLOAD_DIR` is mounted to `./backend/uploads` for durability across restarts.
- CORS defaults in `docker-compose.yml` are set for local browser usage (`http://localhost:15174` + credentials enabled).
- The shared backend image includes an HTTP `/healthz` `HEALTHCHECK`, but the worker service disables it because Celery does not listen on port `8000`.
- The worker defaults to `CELERY_WORKER_CONCURRENCY=1` to reduce `WorkerLostError` / OOM / SIGKILL risk on smaller hosts.

---

## 3) Release package (zip)

Do not manually zip the repo. Always use the release script so the output is reproducible and clean.

Cross-platform (CI uses this):

```bash
python scripts/make_release_zip.py --out release.zip --check
```

Windows PowerShell convenience wrapper:

```powershell
powershell -ExecutionPolicy Bypass -File .\\make_release_zip.ps1
```

Release requirements:

- The zip must **not** contain `.git/`, `node_modules/`, `dist/`, `__pycache__/`, test caches, runtime outputs (`uploads/`, `segments/`), or local `.env` files.
- The scripts perform a **fail-fast check** on zip contents; CI verifies this too.
