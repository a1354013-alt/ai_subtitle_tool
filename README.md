# AI 自動影片上字幕與剪輯工具 (Ultimate Production Ready v2.0)

這是一個專業級的自動化影片處理工具，整合了 Faster-Whisper、GPT-4o 與 Celery 並行架構。

## 主要功能
*   **極致效能**: Faster-Whisper + Celery Chord 並行處理，長影片辨識速度提升數倍。
*   **專業剪輯**: FFmpeg 原生靜音偵測與剪輯，穩定且高效。
*   **多語種翻譯**: 批次翻譯 (Batch Mode) 降低成本，支援多國語言同步生成。
*   **風格化字幕**: 支援 ASS 格式，提供更佳的視覺體驗。
*   **說話者偵測**: 整合 pyannote.audio 辨識不同說話者。
*   **生產級架構**: 串流上傳、環境變數配置、自動檔案清理、WebSocket 即時進度、任務鎖定機制。

## 快速啟動

### 1. 安裝依賴

為了支援 CPU-only 部署，我們將依賴分為核心功能與選配的說話者偵測功能。

**核心依賴 (Core Dependencies):**
```bash
pip install -r requirements-core.txt
```

**說話者偵測依賴 (Diarization Dependencies - 選配):**
如果您需要啟用說話者偵測功能，請安裝此依賴。此功能需要 Hugging Face Token。
```bash
pip install -r requirements-diarization.txt
```

**CPU-only 部署注意事項:**
`requirements-core.txt` 中包含 `torch` 依賴。如果您在 CPU-only 環境部署，建議參考 PyTorch 官方網站，手動安裝適合您環境的 CPU 版本 `torch`，以避免安裝到不必要的 GPU 相關套件。
例如：`pip install torch==2.1.2 --index-url https://download.pytorch.org/whl/cpu`

### 2. 設定環境變數
建立 `.env` 檔案或直接設定：
- `OPENAI_API_KEY`: 您的 OpenAI API 金鑰
- `REDIS_URL`: Redis 連線位址 (預設: redis://localhost:6379/0)
- `UPLOAD_DIR`: 檔案上傳目錄 (預設: ./backend/uploads)
- `CORS_ALLOWED_ORIGINS`: 允許跨域請求的來源網域，多個請用逗號分隔 (預設: "*")
- `TRANSLATE_MODEL`: 翻譯模型名稱 (預設: gpt-4o-mini)

### 3. 啟動服務 (請在專案根目錄執行)

**啟動 Celery Worker:**
```bash
celery -A backend.celery_app:celery_app worker --loglevel=info
```

**啟動 Celery Beat (定時清理):**
```bash
celery -A backend.celery_app:celery_app beat --loglevel=info
```

**啟動 FastAPI Server:**
```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

**啟動 Flower 監控 (選配):**
```bash
celery -A backend.celery_app:celery_app flower
```

## API 說明
*   `POST /upload`: 上傳影片並開始任務。
*   `GET /status/{task_id}`: 查詢任務進度。
*   `GET /results/{task_id}`: 獲取任務生成的檔案清單。
*   `GET /download/{task_id}?lang=English`: 下載結果檔案。
*   `GET/PUT /subtitle/{task_id}?lang=English`: 獲取或編輯字幕內容。
*   `WS /ws/status/{task_id}`: WebSocket 即時進度推送。
