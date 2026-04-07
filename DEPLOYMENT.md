# AI 自動影片上字幕與剪輯工具 - 部署教學文件

本文件引導完成環境配置與服務啟動。此為**後端純 API 版本**，不包含前端。

## 1. 系統環境要求
*   **作業系統**: Linux (Ubuntu 22.04+)、macOS 或 Windows WSL2
*   **Python 版本**: 3.10+
*   **硬體建議**: 
    *   **CPU**: 4 核心以上
    *   **RAM**: 8GB 以上 (Whisper 模型載入需要)
    *   **GPU**: NVIDIA GPU (選配，辨識速度提升 5-10 倍)
*   **外部工具**: 
    *   `ffmpeg`: 用於聲音分離、切片、驗證、字幕燒錄
    *   `ffprobe`: 用於驗證上傳檔案有效性  
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

### Windows (with WSL2)
```bash
# 在 WSL2 Ubuntu 中執行 Ubuntu 指令
```

## 3. 專案環境設定

### 1. 建立虛擬環境
```bash
cd ai_subtitle_tool
python3 -m venv venv
source venv/bin/activate
# Windows: venv\Scripts\activate
```

### 2. 安裝 Python 套件
```bash
pip install --upgrade pip
pip install -r requirements.txt

# 若需要說話者偵測功能（選配），另安裝：
# pip install -r requirements-diarization.txt
```

### 3. 設定環境變數
在專案根目錄建立 `.env` 檔案：
```ini
# 必需
OPENAI_API_KEY=your_openai_api_key_here
REDIS_URL=redis://localhost:6379/0
UPLOAD_DIR=./backend/uploads

# 選配
HF_TOKEN=your_huggingface_token_here    # 若使用說話者偵測
TRANSLATE_MODEL=gpt-4o-mini              # 翻譯模型，預設值已設
CORS_ALLOWED_ORIGINS=*                   # 若設 *, 則 allow_credentials 必須為 false
CORS_ALLOW_CREDENTIALS=false              # 若使用 *, 需設為 false
```

## 4. 啟動服務

在專案根目錄分別執行以下指令（建議在不同終端機視窗執行）。

### 1. 確保 Redis 運行中
```bash
# Linux/macOS
redis-server

# 或檢查服務狀態
sudo service redis-server status
```

### 2. 啟動 Celery Worker (核心處理單元)
```bash
celery -A backend.celery_app:celery_app worker --loglevel=info
```

### 3. 啟動 Celery Beat (定時清理任務，每小時執行)
```bash
celery -A backend.celery_app:celery_app beat --loglevel=info
```

### 4. 啟動 FastAPI Server (API 接口)
```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

### 5. 啟動 Flower 監控介面（選配）
```bash
celery -A backend.celery_app:celery_app flower --port=5555
```

## 5. API 端點

### 上傳與處理

- **POST /upload** - 上傳影片，返回 task_id
  - **參數** (Form multipart data):
    - `file`: 影片檔案 (必填)
    - `target_langs`: 目標語言 (必填)
    - `burn_subtitles`: 是否燒印字幕 (預設: true)
    - `subtitle_format`: 字幕格式 (預設: "ass", 允許: "ass" 或 "srt")
    - `remove_silence`: 是否移除靜音段落 (預設: false)
    - `parallel`: 是否平行處理 (預設: true)

### 查詢與下載

- **GET /status/{task_id}** - 查詢任務進度
- **GET /results/{task_id}** - 查詢結果檔案清單
- **GET /subtitle/{task_id}?lang=LANG[&format=FORMAT]** - 查詢字幕
  - `lang`: 語言代碼 (必填)
  - `format`: 字幕格式 (選填，"ass" 或 "srt")
- **GET /download/{task_id}?lang=LANG[&format=FORMAT]** - 下載字幕或影片
  - `lang`: 語言代碼 (選填)
  - `format`: 字幕格式 (選填，"ass" 或 "srt")
  - 若無 `lang`: 下載原始影片
  - 若有 `lang`: 下載燒印字幕的影片或字幕檔案
- **WS /ws/status/{task_id}** - WebSocket 即時進度推送

### 字幕編輯

- **GET /subtitle/{task_id}?lang=LANG[&format=FORMAT]** - 查詢完整字幕
- **PUT /subtitle/{task_id}?lang=LANG** - 編輯字幕
  - **Body** (JSON):
    ```json
    {
      "content": "字幕內容",
      "format": "ass"
    }
    ```
  - **注意**: 編輯後舊的 final.mp4 將被刪除，重新下載時會重新生成

**注意**: 
- 所有 `task_id` 必須為合法 UUID
- `lang` 只允許英數、底線、連字號
- `subtitle_format` 和 `format` 只允許 "ass" 或 "srt"
- 不支援通過 URL 傳遞 `hf_token`
- CSV/字幕格式隔離: .ass 和 .srt 的字幕分別存放，互不影響

## 6. 生產環境建議

### 1. 使用 Systemd 管理服務
撰寫 Systemd service 檔案以確保服務持久化。

### 2. Nginx 反向代理
```nginx
# 設置 SSL、反向代理、上傳大小限制
server {
    client_max_body_size 2G;
    # ... 其他配置
}
```

### 3. GPU 支援驗證
啟動 Worker 後，檢查日誌是否顯示 `Using device: cuda`。

## 7. 常見問題排除

| 問題 | 解決方案 |
|------|--------|
| **ImportError** | 確保在專案根目錄執行，已安裝 requirements.txt |
| **任務超時** | 調整 `backend/celery_app.py` 中的 `task_time_limit` |
| **FFmpeg/ffprobe 未找到** | 確保已安裝系統 ffmpeg 套件 |
| **Redis 連線失敗** | 確認 Redis 服務已啟動，URL 配置正確 |
| **OpenAI 金鑰無效** | 驗證 OPENAI_API_KEY 環境變數已設置 |
