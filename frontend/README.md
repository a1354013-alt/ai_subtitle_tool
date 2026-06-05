# AI Subtitle Tool Frontend

Vue 3 SPA for the AI Subtitle Tool backend.

Main pages:

- Upload: create task (`POST /upload`)
- Task status: poll status (`GET /status/{task_id}`)
- Subtitles: fetch/update (`GET/PUT /subtitle/{task_id}?lang=...&format=...`)
- Downloads: show existing outputs (`GET /results/{task_id}`, `GET /download/{task_id}?...`)

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

## Business Rules (UI)

- Subtitle editing updates only the subtitle file; it does NOT rebuild/burn the video.
- Downloads page only downloads existing outputs; it must not trigger background rebuild.
- Subtitles/download actions always use an explicit `lang` from manifest / selector (localStorage is UI preference only).
- Status warnings are non-fatal and are shown separately from errors.
