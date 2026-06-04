# Development

## VS Code F5

1. Open the repository root in VS Code.
2. Press F5.
3. Select `Run Full Stack Dev`.

The `Run Full Stack Dev` launch runs `scripts/dev_start.py`. It creates or verifies `.venv`, installs backend dependencies from `requirements.lock.txt`, runs `npm ci`, creates local `.env` files when missing, checks ffmpeg/ffprobe, checks Redis, starts the FastAPI backend, starts the Vite frontend, and starts a Celery worker when Redis is available.

Python 3.11 or 3.12 is required.
Recommended: Python 3.11
Supported: Python 3.11-3.12
Unsupported: Python 3.13+

Node.js 20.x is required.

Use a full repository clone for F5 development. Release zips intentionally exclude `.vscode` and the local development helper scripts, so they are for deployment packaging rather than VS Code launch workflows.

## First Run

Run:

```powershell
python scripts/dev_bootstrap.py
```

The first-run bootstrap uses `.venv` consistently. `backend/.env` is created from `backend/.env.example` with host-friendly defaults such as `REDIS_URL=redis://localhost:6379/0`, `UPLOAD_DIR=backend/uploads`, `OUTPUT_DIR=backend/outputs`, `TEMP_DIR=backend/tmp`, and `RATE_LIMIT_PER_IP=0`. Redis is checked on `127.0.0.1:6379`; if Docker is available, the dev scripts try to start Redis before falling back to explicit guidance or eager-mode development.

`scripts/dev_bootstrap.py` fails fast on unsupported Python versions with:

```txt
Python 3.11 or 3.12 is required. Current version: x.y.z
```

Backend tests assume the locked backend dependencies are installed:

```powershell
python -m pip install -r requirements.lock.txt
$env:TESTING="true"; $env:PYTHONPATH="."; .venv\Scripts\python -m pytest -q
```

Frontend dependencies:

```powershell
cd frontend
npm ci
cd ..
```

Full delivery verification:

```powershell
python -m pip install -r requirements.lock.txt
cd frontend
npm ci
cd ..
python scripts/verify_delivery.py --full
```

Production dependency audit:

```powershell
cd frontend
npm audit --omit=dev
```

Full `npm audit` may still report dev dependency advisories. Those are tracked separately and are not production runtime risks unless the vulnerable package becomes a runtime dependency.

Redis behavior in `scripts/dev_start.py --redis auto`:

- Redis available on `127.0.0.1:6379`: backend, frontend, and Celery worker start.
- Redis unavailable but Docker can start it: backend, frontend, and Celery worker start after Redis is available.
- Redis unavailable and Docker unavailable: backend and frontend start in Celery eager dev mode; the worker is skipped.
- Production and Docker deployments should run Redis plus a Celery worker instead of relying on eager mode.

## Stop Services

Use the VS Code task `dev:stop`, or run:

```powershell
scripts/stop-dev.ps1
```

## Common Issues

- Redis is not running: install/start Redis, or run `python scripts/dev_start.py --redis auto` to use the eager fallback when Docker is unavailable.
- ffmpeg or ffprobe is missing: install ffmpeg and ensure both binaries are on `PATH`, or set `FFMPEG_BINARY` and `FFPROBE_BINARY`.
- Frontend port 5173 is occupied: stop the process using the port or let Vite choose another port.
- Backend port 8000 is occupied: stop the existing backend before F5.
- `OPENAI_API_KEY` is not set: transcription for `Original` works, but translation targets are rejected until a key is configured.
- Production auth: set `REQUIRE_AUTH_TOKEN=true` and `AUTH_TOKEN`; frontend builds can set `VITE_API_TOKEN` so API requests include `X-API-Token`.
- `python scripts/verify_delivery.py --full --ci-fast` or `--smoke` prints a fast-mode banner and may skip expensive checks; it is not a full release verification.
