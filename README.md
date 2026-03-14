# AI 自動影片上字幕與剪輯工具

這是一個基於 Python 的自動化工具，能夠將影片中的語音轉換為文字，並自動翻譯成中文，生成雙語字幕。

## 主要功能
*   **影片上傳 (優化)**: 支援 **Streaming 串流上傳**，大檔案不爆記憶體。
*   **極致語音辨識 (Faster-Whisper)**: 整合 Faster-Whisper，辨識速度提升 **4 倍以上**，支援 **GPU 加速**與**動態模型切換**。
*   **高效並行架構 (Celery Chord)**: 採用非阻塞式並行架構，長影片自動切片並發處理，效能極致且不阻塞 Worker。
*   **環境配置靈活**: 全面支援環境變數配置（Redis URL, Upload Path），易於 Docker 化部署。
*   **多語種同步翻譯**: 支援一次翻譯成多國語言，並實作 **Exponential Backoff 重試機制**。
*   **風格化字幕 (ASS)**: 支援生成帶有樣式的 `.ass` 字幕。
*   **完整 API 鏈路**: 補全了 `/download` 路由，統一業務 ID 與任務 ID，實現從上傳到下載的完整閉環。
*   **自動靜音剪輯**: 自動偵測並移除影片中的無聲片段。
*   **即時狀態推送 (WebSocket)**: 透過 WebSocket 實作即時進度條與狀態訊息推送。
*   **系統監控 (Flower)**: 整合 Flower 視覺化介面。
*   **自動檔案清理**: 內建 Celery Beat 定時任務。

## 技術棧
*   **後端**: FastAPI
*   **任務隊列**: Celery, Redis
*   **AI 模型**: Whisper (STT), GPT-4o-mini (Translation)
*   **多媒體處理**: FFmpeg

## 快速開始

### 1. 環境設定
確保系統已安裝 `ffmpeg` 與 `redis-server`。

```bash
# 安裝依賴
pip install -r requirements.txt
```

### 2. 啟動服務
需要同時啟動 Redis、Celery Worker 與 FastAPI Server。

```bash
# 啟動 Redis
redis-server

# 啟動 Celery Worker 與 Beat (定時任務)
celery -A tasks worker --beat --loglevel=info

# 啟動 Flower 監控介面 (預設埠號 5555)
celery -A tasks flower

# 啟動 FastAPI
python backend/main.py
```

### 3. 使用 API
*   **上傳影片**: `POST /upload` (Multipart Form Data)
*   **查詢進度**: `GET /status/{task_id}`

## 專案結構
*   `backend/main.py`: API 入口與路由。
*   `backend/tasks.py`: Celery 非同步任務邏輯。
*   `backend/utils/`: 包含 Whisper 辨識與翻譯的工具函式。
