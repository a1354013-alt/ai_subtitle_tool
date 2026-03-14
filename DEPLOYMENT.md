# AI 自動影片上字幕與剪輯工具 - 部署教學文件

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

### 1. 複製專案並建立虛擬環境
```bash
git clone <your-repo-url>
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
# 若需使用說話者偵測功能
export HF_TOKEN="your_huggingface_token_here" 
```

## 4. 啟動服務

為了讓系統正常運作，你需要啟動四個主要組件。建議在開發環境中使用多個終端機視窗，或在生產環境中使用 `tmux` / `systemd`。

### 1. 啟動 Redis (若尚未啟動)
```bash
redis-server
```

### 2. 啟動 Celery Worker 與 Beat (核心處理單元)
```bash
# --beat 用於執行定時檔案清理任務
source venv/bin/activate
cd backend
celery -A tasks worker --beat --loglevel=info
```

### 3. 啟動 Flower (監控介面)
```bash
source venv/bin/activate
cd backend
celery -A tasks flower --port=5555
```
*啟動後可訪問 `http://localhost:5555` 查看任務狀態。*

### 4. 啟動 FastAPI Server (API 接口)
```bash
source venv/bin/activate
cd backend
python main.py
```
*預設運行於 `http://localhost:8000`。*

## 5. 生產環境部署建議 (Production)

### 1. 使用 Gunicorn 運行 FastAPI
在生產環境中，建議使用 Gunicorn 搭配 Uvicorn worker 以獲得更好的穩定性：
```bash
pip install gunicorn
gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app --bind 0.0.0.0:8000
```

### 2. 使用 Systemd 管理服務
為 Celery 和 FastAPI 撰寫 Systemd service 檔案，確保伺服器重啟後服務能自動啟動。

### 3. Nginx 反向代理
使用 Nginx 作為反向代理，處理 SSL 憑證 (HTTPS) 並轉發請求至 FastAPI 與 Flower。

### 4. GPU 支援確認
若要確認 GPU 是否被正確使用，啟動 Worker 後觀察日誌，應顯示：
`Using device: cuda`

## 6. 常見問題排除 (FAQ)
*   **Whisper 載入太慢**: 第一次執行會下載模型檔，請確保網路暢通。
*   **FFmpeg 報錯**: 請確認 `ffmpeg` 已加入系統路徑 (`PATH`)。
*   **Redis 連線失敗**: 請檢查 Redis 是否已啟動且監聽於預設的 6379 埠。
