# AI 自動影片上字幕與剪輯工具 (Pro Perfect Edition)

這是一個專業級的自動化影片處理工具，整合了 Faster-Whisper、GPT-4o 與 Celery 並行架構。

## 主要功能
*   **極致效能**: Faster-Whisper + Celery Chord 並行處理，長影片辨識速度提升數倍。
*   **專業剪輯**: FFmpeg 原生靜音偵測與剪輯，穩定且高效。
*   **多語種翻譯**: 批次翻譯 (Batch Mode) 降低成本，支援多國語言同步生成。
*   **風格化字幕**: 支援 ASS 格式，提供更佳的視覺體驗。
*   **說話者偵測**: 整合 pyannote.audio 辨識不同說話者。
*   **生產級架構**: 串流上傳、環境變數配置、自動檔案清理、WebSocket 即時進度。

## 快速啟動

### 1. 安裝依賴
```bash
pip install -r requirements.txt
```

### 2. 設定環境變數
```bash
export OPENAI_API_KEY="your_key"
export REDIS_URL="redis://localhost:6379/0"
export UPLOAD_DIR="./backend/uploads"
```

### 3. 啟動服務 (請在專案根目錄執行)

**啟動 Celery Worker:**
```bash
celery -A backend.tasks worker --loglevel=info
```

**啟動 Celery Beat (定時清理):**
```bash
celery -A backend.tasks beat --loglevel=info
```

**啟動 FastAPI Server:**
```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

**啟動 Flower 監控 (選配):**
```bash
celery -A backend.tasks flower
```

## API 說明
*   `POST /upload`: 上傳影片並開始任務。
*   `GET /status/{task_id}`: 查詢任務進度。
*   `GET /download/{task_id}?lang=English`: 下載結果檔案。
*   `WS /ws/status/{task_id}`: WebSocket 即時進度推送。
