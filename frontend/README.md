# AI Subtitle Tool Frontend

Vue 3 SPA for the AI Subtitle Tool backend.

Main pages:

- Upload: create task (`POST /upload`)
- Task status: poll status (`GET /status/{task_id}`)
- Subtitles: fetch/update (`GET/PUT /subtitle/{task_id}?lang=...&format=...`)
- Downloads: show existing outputs (`GET /results/{task_id}`, `GET /download/{task_id}?...`) and offer an explicit final-video rebuild action (`POST /tasks/{task_id}/rebuild-final`)

## Requirements

- Node.js 20.x is required

## Install / Run

Important: do NOT ship `node_modules/` in a release package.

```bash
cd frontend
npm ci
npm run dev
```

Build:

```bash
npm audit --omit=dev
npm run build
npm run preview
```

Test:

```bash
npm test
npm run test:ci
```

- `npm test` runs Vitest in watch mode for local iteration.
- `npm run test:ci` runs the non-watch, CI-safe suite and must exit automatically.

## API Base URL (`VITE_API_BASE_URL`)

The frontend uses a single base URL source for BOTH API requests and download URLs.

- Same-origin deployment: omit `VITE_API_BASE_URL` (default: current origin).
- Different-origin deployment: set `VITE_API_BASE_URL` to your FastAPI origin.

Example:

```ini
VITE_API_BASE_URL=http://127.0.0.1:8891
```

`VITE_API_TOKEN`, when set, is added to fetch requests as `X-API-Token`. It is embedded in the browser bundle and is not a protected secret. Download buttons first request a short-lived signed URL from `/download-ticket`, then open that ticketed URL for final videos, subtitle files, and batch ZIPs.

## Business Rules (UI)

- Subtitle editing updates only the subtitle file; it does NOT rebuild/burn the video.
- Downloads page may enqueue a background rebuild only when the user clicks the explicit rebuild action.
- Rebuild status uses the queued rebuild task id, while success actions link back to the original task results.
- Subtitles/download actions always use an explicit `lang` from manifest / selector (localStorage is UI preference only).
- Status warnings are non-fatal and are shown separately from errors.
