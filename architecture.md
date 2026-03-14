# AI 自動影片上字幕與剪輯工具 - 專案架構規劃

## 1. 技術選型 (Tech Stack)
*   **Backend**: FastAPI (高效能、非同步支援)
*   **Frontend**: React (透過 Vite 建立)
*   **Task Queue**: Celery + Redis (處理耗時的影片轉檔與 AI 辨識)
*   **AI Models**: 
    *   **Whisper**: 用於語音轉文字 (STT)
    *   **OpenAI GPT-4o-mini**: 用於高品質的英/日文翻譯
*   **Multimedia Processing**: FFmpeg (影片剪輯、音訊提取、字幕內嵌)
*   **Database**: SQLite (開發階段使用，儲存任務狀態與檔案資訊)

## 2. 系統流程
1.  **上傳階段**: 使用者透過 Web 介面上傳影片。
2.  **任務分發**: FastAPI 接收請求，將任務發送到 Celery 隊列，並回傳 `task_id` 給前端。
3.  **音訊提取**: Celery Worker 使用 FFmpeg 從影片中提取音訊。
4.  **語音辨識**: 使用 Whisper 模型將音訊轉換為帶時間戳的文字。
5.  **翻譯處理**: 若使用者選擇翻譯，則呼叫 LLM 將原始文字翻譯為中文。
6.  **字幕生成**: 產生 `.srt` 檔案，並根據需求合成雙語字幕。
7.  **影片合成 (選配)**: 使用 FFmpeg 將字幕燒錄進影片中。
8.  **完成通知**: 前端透過輪詢 (Polling) 獲取任務進度與下載連結。

## 3. 目錄結構
```text
ai_subtitle_tool/
├── backend/
│   ├── main.py          # FastAPI 入口
│   ├── celery_app.py    # Celery 配置
│   ├── tasks.py         # 具體非同步任務
│   ├── utils/           # 工具函式 (FFmpeg, Whisper, Translation)
│   └── uploads/         # 暫存上傳檔案
├── frontend/            # React 前端專案
├── docker-compose.yml   # 環境部署
└── requirements.txt     # Python 依賴
```
