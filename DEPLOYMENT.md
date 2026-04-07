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
python -m unittest
```

## 6. 發佈/交付建議

- 建議用 `git archive` 或其他方式打包，避免把 `.git/` 一起帶入交付包
- `UPLOAD_DIR` 內的中間檔與輸出（字幕/影片/segments）不應進版控；已由 `.gitignore` 覆蓋常見模式
- 需要長時間運行時，建議把 `UPLOAD_DIR` 指到獨立磁碟/目錄並做定期清理

## 7. 前端（SPA）

前端位於 `frontend/`，建議以靜態檔案方式部署（例如 Nginx）。

```bash
cd frontend
npm install
npm run build
```

前後端不同源部署時，前端需要設定 `VITE_API_BASE_URL` 指向 FastAPI（此設定同時影響 API request 與下載連結 URL）。詳見 `frontend/README.md`。
