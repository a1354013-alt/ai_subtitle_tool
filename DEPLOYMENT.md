# AI 自動影片上字幕工具 - 部署指南

本指南以「可重現、可交付」為目標，描述目前版本的必要依賴與建議操作。

## 1. 需求

- Python 3.10–3.12（建議；部分依賴如 torch/faster-whisper 的 wheel 對更新版 Python 可能不齊）
- `ffmpeg` 與 `ffprobe`（必需）
- Redis（Celery broker / backend）

## 2. 安裝

```bash
python -m venv venv
# Windows: venv\Scripts\activate
# Linux/macOS: source venv/bin/activate
pip install -r requirements.txt
```

## 3. 環境變數（範例）

```ini
OPENAI_API_KEY=...
REDIS_URL=redis://localhost:6379/0
UPLOAD_DIR=./backend/uploads
HF_TOKEN=...                 # 選配：說話者偵測
TRANSLATE_MODEL=gpt-4o-mini
CORS_ALLOWED_ORIGINS=*
CORS_ALLOW_CREDENTIALS=false
```

## 4. 啟動

```bash
# 1) Redis
redis-server

# 2) Celery worker
celery -A backend.celery_app:celery_app worker --loglevel=info

# 3) （選配）Celery beat：定期清理
celery -A backend.celery_app:celery_app beat --loglevel=info

# 4) FastAPI
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

## 5. 測試

```bash
pytest
```

## 6. 發佈/交付建議

- 建議用 `git archive` 或其他方式打包，避免把 `.git/` 一起帶入交付包
- `UPLOAD_DIR` 內的中間檔與輸出（字幕/影片/segments）不應進版控；已由 `.gitignore` 覆蓋常見模式
- 需要長時間運行時，建議把 `UPLOAD_DIR` 指到獨立磁碟/目錄並做定期清理

## 7. 前端（SPA）

前端位於 `frontend/`，建議以靜態檔案方式部署（例如 Nginx）。

```bash
cd frontend
rm -rf node_modules
npm install
npm run build
```

測試：

```bash
npm test
```

前後端不同源部署時，前端需要設定 `VITE_API_BASE_URL` 指向 FastAPI（此設定同時影響 API request 與下載連結 URL）。詳見 `frontend/README.md`。

## Results Manifest 契約（重要）

- `GET /results/{task_id}` 只有在任務狀態為 `SUCCESS` 時才會回傳 `available_files`（可下載輸出清單）。
- 若任務仍在 `PENDING/PROCESSING` 或已 `FAILURE/REVOKED`，manifest 會回傳空的 `available_files`，並用 `task_status` 表示當前狀態，避免用 uploads 目錄殘留檔案誤判為有效輸出。

## 10. 交付包清潔原則 / Release Packaging

- 交付包不包含：`.git/`、`frontend/node_modules/`、`frontend/dist/`、`tests/_tmp/`、`__pycache__/`、`backend/uploads/*` 等中間產物。
- 建議使用乾淨工作樹打包（或用專案內的 `make_release_zip.ps1`）以避免權限/快取污染驗收。
- `make_release_zip.ps1` 會建立暫存 staging 目錄並輸出 zip（預設：`release_out/ai_subtitle_tool_release.zip`），不會在 repo 中留下第二份 source tree。

## 8. Warnings 顯示

後端 status 回應包含 `warnings: string[]`（非致命問題）。前端會在任務狀態頁以列表顯示 warnings，方便除錯與理解處理過程，但不會把 warnings 當成錯誤。

## 9. Download URL（字幕需要明確 lang）

下載字幕時必須提供 `lang` query（例如 `Traditional_Chinese`）。前端會由 UI 的 Language selector 明確傳入 `lang`，不會在 API 層使用 localStorage 等隱性狀態來推導下載 URL。
