# v1.0.0-rc3 Release Candidate Smoke Checklist

Use this checklist before promoting `1.0.0-rc3` to a stable `v1.0.0` tag. Mocked tests do not prove Faster-Whisper, Redis, Celery, Docker, FFmpeg, GPU, CJK burn-in, downloads, cancellation, cleanup, or S3 behavior.

Record the commit SHA, OS, Python version, Node.js version, Docker version, FFmpeg version, Redis version, model name, and whether GPU acceleration was used.

## Preconditions

- Python 3.11 or 3.12.
- Node.js 20.x.
- Backend dependencies installed with `python -m pip install -r requirements.lock.txt`.
- Frontend dependencies installed with `cd frontend && npm ci`.
- FFmpeg and ffprobe available on `PATH`.
- For CJK burn-in: fontconfig and an exact `SUBTITLE_FONT_NAME` match, default `Noto Sans CJK TC`.
- For Docker smoke: Docker Compose v2 available.

## Validation Steps

| Step | Command or UI action | Expected result | Failure evidence to collect | Relevant logs |
| --- | --- | --- | --- | --- |
| 1. F5 one-click startup | Open the repo in VS Code and press F5. | Backend, frontend, and Celery worker start when Redis is available; eager mode is explicitly reported only when Redis/Docker are unavailable. | VS Code terminal output, Python and Node versions, Redis fallback message. | VS Code launch terminal, backend stdout, frontend Vite stdout. |
| 2. Docker Compose startup | `cp backend/.env.example backend/.env`; `cp frontend/.env.example frontend/.env`; `docker compose up --build` | Redis, backend, worker, beat, and frontend containers become healthy/running. | `docker compose ps`, failing container exit codes, build output. | `docker compose logs redis backend worker beat frontend`. |
| 3. API readiness | `curl -fsS http://127.0.0.1:8891/readyz` locally or `curl -fsS http://127.0.0.1:9091/readyz` in Docker. | Response is `{"status":"ok"}`. | Full JSON error response, environment variables, FFmpeg/font/Redis status. | Backend logs. |
| 4. Frontend readiness | Open `http://127.0.0.1:5173` locally or `http://localhost:5173` in Docker. | Upload page loads and `/api/config` is fetched successfully. | Browser console, network tab, HTTP status and response body. | Browser devtools, frontend logs, backend access logs. |
| 5. Short-video transcription | Upload a short video with `Original`, `burn_subtitles=false`, `parallel=false`. | Task reaches SUCCESS; SRT is available. | Task id, `/status/{task_id}`, `/results/{task_id}`. | Backend logs, worker logs, `backend/uploads/{task_id}_error.json` if present. |
| 6. Long-video parallel transcription | Upload a video long enough to segment with `parallel=true`. | Segment tasks complete and original task reaches SUCCESS. | Segment count, task id, Celery task ids, temp segment directory state. | Worker logs, backend logs, `backend/tmp`, `backend/uploads`. |
| 7. Segment failure handling | Run a controlled failure case with one segment failure, or execute the integration test command for the maintained fixture. | Original task is FAILURE and temp segments/locks are removed. | `/status/{task_id}`, lock files, temp segment listing. | Worker logs, `backend/uploads/{task_id}_error.json`. |
| 8. Normal task cancellation | Start a task, click cancel, or `curl -X POST http://127.0.0.1:8891/tasks/{task_id}/cancel`. | Task becomes CANCELED and remains canceled on repeated polling. | Status responses before and after cancel. | Backend logs, worker logs. |
| 9. Subtitle editing | Open a completed task subtitle page, edit SRT or ASS, and save. | Edited subtitle persists; stale final video is invalidated when applicable. | Before/after subtitle content, API response warnings. | Backend logs, browser network tab. |
| 10. Final-video rebuild | On Downloads, click rebuild for an edited subtitle. | A new `rebuild_task_id` is queued and reaches SUCCESS; original result remains the download owner. | Rebuild task id, original task id, status responses. | Worker logs, backend logs. |
| 11. Rebuild cancellation | Start rebuild and cancel using `/tasks/{rebuild_task_id}/cancel`. | Rebuild becomes CANCELED; original successful task remains SUCCESS. | Both status responses. | Backend logs, worker logs. |
| 12. ASS download | Click ASS download or `curl -f -o out.ass "http://127.0.0.1:8891/download/{task_id}?lang=Traditional_Chinese&format=ass"`. | Download succeeds and file is valid ASS. | HTTP status, response headers, file content. | Backend logs, browser network tab. |
| 13. SRT download | Click SRT download or `curl -f -o out.srt "http://127.0.0.1:8891/download/{task_id}?lang=Traditional_Chinese&format=srt"`. | Download succeeds and file is valid SRT. | HTTP status, response headers, file content. | Backend logs, browser network tab. |
| 14. VTT download | Click VTT download or `curl -f -o out.vtt "http://127.0.0.1:8891/download/{task_id}?lang=Traditional_Chinese&format=vtt"`. | Download succeeds and starts with `WEBVTT`. | HTTP status, response headers, file content. | Backend logs, browser network tab. |
| 15. Final-video download | Click final video download or `curl -f -o final.mp4 "http://127.0.0.1:8891/download/{task_id}"`. | MP4 downloads and plays. | HTTP status, response headers, media probe output. | Backend logs, browser network tab. |
| 16. Batch ZIP download | Upload a batch, wait for at least one success, click batch ZIP download. | ZIP downloads atomically and includes available subtitle/video artifacts plus `failed_tasks.json` when needed. | ZIP listing, batch id, task statuses. | Backend logs, `backend/outputs`. |
| 17. Protected downloads | Set `REQUIRE_AUTH_TOKEN=true` and `AUTH_TOKEN`, rebuild frontend with `VITE_API_TOKEN`, then download files. | Direct unauthenticated download is 401; authenticated ticketed download succeeds. | Unauthorized response, `/download-ticket` response, ticketed URL response. | Backend logs, browser network tab. |
| 18. Redis restart after success | Complete a task, restart Redis, then call `/status/{task_id}` and `/results/{task_id}`. | Persisted SUCCESS still wins. | Redis restart command output and both responses. | Redis logs, backend logs. |
| 19. Redis result metadata loss recovery | Delete/expire Redis result metadata for a successful task, then call `/status/{task_id}` and `/results/{task_id}`. | Durable history/artifacts recover the successful state. | Redis key inspection, API responses. | Redis logs, backend logs. |
| 20. Traditional Chinese, Japanese, and English CJK burn-in | `RUN_CJK_BURNIN_SMOKE=1 python -m pytest -q -m integration tests/test_cjk_burnin_integration.py` and manually inspect a multilingual burn-in output. | Exact configured font resolves and burned subtitles render for Traditional Chinese, Japanese, and English. | Test output, `fc-match` output, generated video sample. | Pytest output, FFmpeg stderr, backend logs. |
| 21. Celery beat cleanup | Run Docker or local beat with `celery -A backend.celery_app:celery_app beat --loglevel=info`. | Scheduled cleanup task runs without using worker `-B`. | Beat startup output, scheduled task dispatch evidence. | Beat logs, worker logs. |
| 22. Expired-file cleanup preserves active tasks | Create old artifacts plus an active lock, run cleanup task or utility. | Expired unlocked files are removed; active task artifacts remain. | Directory listing before/after, cleanup counts. | Worker logs, backend cleanup logs. |

## Release Gates

Run these before marking the repository as `v1.0.0-rc3` ready:

```bash
python -m compileall -q backend tests scripts benchmarks test_hwaccel.py test_report.py
python -m pytest -q --cov=backend --cov=scripts --cov-report=term-missing -ra
cd frontend
npm ci
npm run lint
npm run typecheck
npm run test:ci
npm run build
npm audit --omit=dev
cd ..
python scripts/verify_delivery.py --zip-only
python scripts/make_release_zip.py --out release.zip --check
python scripts/verify_release_zip.py release.zip
python -m pytest -q tests/test_release_zip.py::test_release_zip_is_reproducible_when_source_mtimes_change
python scripts/verify_docker_config.py
docker compose config
```

`docker compose config` is a static Compose validation. It is not a substitute for `docker compose up --build`.
