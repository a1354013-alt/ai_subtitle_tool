# AI Subtitle Tool Frontend

Vue 3 SPA for the AI Subtitle Tool backend.

Main pages:

- Upload: create task (`POST /upload`)
- Task status: poll status (`GET /status/{task_id}`)
- Subtitles: fetch/update (`GET/PUT /subtitle/{task_id}?lang=...&format=...`)
- Downloads: show existing outputs (`GET /results/{task_id}`, `GET /download/{task_id}?...`)

## Requirements

- Node.js 18+ recommended

## Install / Run

Important: do NOT ship `node_modules/` in a release package.

```bash
cd frontend
npm ci
npm run dev
```

Build:

```bash
npm run build
npm run preview
```

Test:

```bash
npm run test:ci
```

## API Base URL (`VITE_API_BASE_URL`)

The frontend uses a single base URL source for BOTH API requests and download URLs.

- Same-origin deployment: omit `VITE_API_BASE_URL` (default: current origin).
- Different-origin deployment: set `VITE_API_BASE_URL` to your FastAPI origin.

Example:

```ini
VITE_API_BASE_URL=http://localhost:8000
```

## Business Rules (UI)

- Subtitle editing updates only the subtitle file; it does NOT rebuild/burn the video.
- Downloads page only downloads existing outputs; it must not trigger background rebuild.
- Subtitles/download actions always use an explicit `lang` from manifest / selector (localStorage is UI preference only).
- Status warnings are non-fatal and are shown separately from errors.
