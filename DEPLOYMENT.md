# AI 自動影片上字幕與剪輯工具 - 部署教學文件 (v15)

這份文件將引導你完成專案的環境配置與服務啟動。

## 1. 系統環境要求
*   **作業系統**: Linux (推薦 Ubuntu 22.04+) 或 macOS
*   **Python 版本**: 3.10+
*   **硬體建議**: 
    *   **CPU**: 4 核心以上
    *   **RAM**: 8GB 以上 (Whisper 模型載入需要)
    *   **GPU**: NVIDIA GPU (選配，若有 GPU 辨識速度將提升 5-10 倍)
*   **外部工具**: 
    *   `ffmpeg`: 用於多媒體處理
    *   `redis-server`: 用於 Celery 任務隊列

## 2. 安裝系統依賴

### Ubuntu/Debian
```bash
sudo apt update
sudo apt install -y ffmpeg redis-server python3-pip python3-venv
```

### macOS
```bash
brew install ffmpeg redis
brew services start redis
```

## 3. 專案環境設定

### 1. 建立虛擬環境
```bash
cd ai_subtitle_tool
python3 -m venv venv
source venv/bin/activate
```

### 2. 安裝 Python 套件
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. 設定環境變數
在專案根目錄建立 `.env` 檔案，或直接匯出環境變數：
```bash
export OPENAI_API_KEY="your_openai_api_key_here"
export REDIS_URL="redis://localhost:6379/0"
export UPLOAD_DIR="./backend/uploads"
```

## 4. 啟動服務 (請在專案根目錄執行)

為了讓系統正常運作，你需要啟動以下組件。建議在生產環境中使用 `systemd` 管理。

### 1. 啟動 Redis
```bash
sudo service redis-server start
```

### 2. 啟動 Celery Worker (核心處理單元)
```bash
celery -A backend.celery_app:celery_app worker --loglevel=info
```

### 3. 啟動 Celery Beat (定時清理任務)
```bash
celery -A backend.celery_app:celery_app beat --loglevel=info
```

### 4. 啟動 FastAPI Server (API 接口)
```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

### 5. 啟動 Flower (監控介面，選配)
```bash
celery -A backend.celery_app:celery_app flower --port=5555
```

## 5. 生產環境部署建議 (Production)

### 1. 使用 Systemd 管理服務
為 Celery 和 FastAPI 撰寫 Systemd service 檔案，確保伺服器重啟後服務能自動啟動。**請務必確保 `WorkingDirectory` 設定為專案根目錄。**

### 2. Nginx 反向代理
使用 Nginx 作為反向代理，處理 SSL 憑證 (HTTPS) 並轉發請求至 FastAPI 與 Flower。請設定 `client_max_body_size 2G;` 以支援大影片上傳。

### 3. GPU 支援確認
若要確認 GPU 是否被正確使用，啟動 Worker 後觀察日誌，應顯示：
`Using device: cuda`

## 6. 常見問題排除 (FAQ)
*   **ImportError**: 請確保在專案根目錄執行啟動指令，並已安裝 `requirements.txt`。
*   **MoviePy 報錯**: 專案已使用 `moviepy.editor` 以提升相容性。
*   **任務超時**: 預設超時為 30 分鐘，可在 `backend/celery_app.py` 中調整。
