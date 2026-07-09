# Development

## VS Code F5 One-Click Startup

1. Open the repository root in VS Code.
2. Press F5.
3. The default launch, `Run Full Stack Dev`, starts the backend API, Celery worker when Redis is available, and the Vite frontend.

The `Run Full Stack Dev` launch runs `scripts/dev_start.py`. It creates or verifies `.venv`, installs backend dependencies from `requirements.lock.txt`, runs `npm ci` when `frontend/node_modules` is missing, creates local `.env` files when missing, checks ffmpeg/ffprobe, checks Redis, starts the FastAPI backend, starts the Vite frontend, and starts a Celery worker when Redis is available.

Local endpoints:

- Frontend page: [http://127.0.0.1:5173](http://127.0.0.1:5173)
- Backend API docs: [http://127.0.0.1:8891/docs](http://127.0.0.1:8891/docs)
- Backend health: [http://127.0.0.1:8891/healthz](http://127.0.0.1:8891/healthz)

Python 3.11 or 3.12 is required.
Recommended: Python 3.11
Supported: Python 3.11-3.12
Unsupported: Python 3.13+

Node.js 20.x is required.

Use a full repository clone for F5 development. Release zips intentionally exclude `.vscode` and the local development helper scripts, so they are for deployment packaging rather than VS Code launch workflows.

## First Run

F5 is the preferred first-run path. It tries the selected VS Code Python first when it is supported, then Windows `py -3.11`, then `py -3.12`. If no supported Python is available, startup fails with a clear message instead of creating a bad virtual environment.

You can run bootstrap directly:

```powershell
python scripts/dev_bootstrap.py
```

The first-run bootstrap uses `.venv` consistently. `backend/.env` is created from `backend/.env.example` with host-friendly defaults such as `REDIS_URL=redis://127.0.0.1:6379/0`, `UPLOAD_DIR=backend/uploads`, `OUTPUT_DIR=backend/outputs`, `TEMP_DIR=backend/tmp`, and `RATE_LIMIT_PER_IP=0`. `frontend/.env` is created from `frontend/.env.example` and normalized to `VITE_API_BASE_URL=http://127.0.0.1:8891` for F5.

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

After processes start, `scripts/dev_start.py` waits for `http://127.0.0.1:8891/healthz` and the Vite dev server on `127.0.0.1:5173` before printing the success summary. If a required process exits early, the launcher reports whether backend or frontend failed and leaves the process output visible.

For local Ollama experiments, set these values in `backend/.env`:

```ini
LLM_PROVIDER=ollama
TRANSLATE_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=gemma3:12b
OPENAI_API_KEY=
```

When `LLM_PROVIDER=ollama`, backend translation does not require `OPENAI_API_KEY`. The backend probes `OLLAMA_BASE_URL/api/tags` for capability status, and the frontend should show the active Ollama model instead of an OpenAI-key warning.

## Stop Services

Use the VS Code task `dev:stop`, or run:

```powershell
scripts/stop-dev.cmd
```

The Windows CMD wrapper calls `scripts/stop-dev.ps1` with execution policy bypass. The stop script targets only processes bound to local dev ports `8891` and `5173`, plus Celery-related commands for this project.

## Common Issues

- Redis is not running: install/start Redis, or run `python scripts/dev_start.py --redis auto` to use the eager fallback when Docker is unavailable.
- ffmpeg or ffprobe is missing: install ffmpeg and ensure both binaries are on `PATH`, or set `FFMPEG_BINARY` and `FFPROBE_BINARY`.
- Frontend port 5173 is occupied: stop the process using the port or let Vite choose another port.
- Backend port 8891 is occupied: stop the existing backend before F5.
- `LLM_PROVIDER=openai` and `OPENAI_API_KEY` is not set: `Original` works, but OpenAI translation targets are rejected until a key is configured.
- `LLM_PROVIDER=ollama` and translation is unavailable: start Ollama and confirm `OLLAMA_BASE_URL`; upload/transcription still work for `Original`.
- Production auth: set `REQUIRE_AUTH_TOKEN=true` and `AUTH_TOKEN`; frontend builds can set `VITE_API_TOKEN` so API requests include `X-API-Token`.
- `python scripts/verify_delivery.py --full --ci-fast` or `--smoke` prints a fast-mode banner and may skip expensive checks; it is not a full release verification.
