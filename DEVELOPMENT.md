# Development

## VS Code F5

1. Open the repository root in VS Code.
2. Press F5.
3. Select `Run Full Stack Dev`.

The compound launch starts the FastAPI backend, Vite frontend, Celery worker, and checks Redis first. On Windows, the VS Code tasks call `scripts/start-dev.cmd`, which delegates to PowerShell.

## First Run

Run:

```powershell
python scripts/dev_bootstrap.py
```

The F5 tasks also create `backend/.env` from `backend/.env.example` when it is missing. Redis is checked on `127.0.0.1:6379`; if Docker is available, `docker compose up -d redis` is used.

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
