# AI 自動影片上字幕與剪輯工具

這是一個基於 Python 的自動化工具，能夠將影片中的語音轉換為文字，並自動翻譯成中文，生成雙語字幕。

## 主要功能
*   **影片上傳**: 支援多種主流格式。
*   **極致語音辨識 (Faster-Whisper)**: 整合 Faster-Whisper，辨識速度提升 **4 倍以上**，支援 **GPU 加速**與**動態模型切換**。
*   **分段並行處理**: 長影片自動切片並發辨識，大幅縮短處理時間。
*   **音訊預處理**: 自動提取音軌並進行 **FFmpeg 降噪**。
*   **多語種同步翻譯**: 支援一次翻譯成多國語言（如中、英、日、韓），並實作 **Exponential Backoff 重試機制**。
*   **風格化字幕 (ASS)**: 支援生成帶有樣式的 `.ass` 字幕，提供更佳的視覺體驗。
*   **字幕燒錄 (Hardsub)**: 使用 FFmpeg 將字幕直接壓進影片中。
*   **自動靜音剪輯**: 自動偵測並移除影片中的無聲片段。
*   **說話者偵測 (Diarization)**: 支援辨識不同說話者並在字幕中標註。
*   **即時狀態推送 (WebSocket)**: 透過 WebSocket 實作即時進度條。
*   **線上字幕編輯**: 提供 API 獲取與更新字幕內容。
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
