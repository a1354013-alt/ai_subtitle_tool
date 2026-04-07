# AI 自動影片上字幕與剪輯工具 v2.0

專業級的自動化影片處理後端，集成 Faster-Whisper、GPT-4o-mini 與 Celery 並行架構。

## ✨ 核心特性
- **秒速轉錄**: Faster-Whisper + Celery 並行處理，長影片加速 3-5 倍
- **智能分段**: 含重疊去重機制，避免字幕邊界遺漏或重複
- **多語翻譯**: 批次翻譯降低成本，一次支援多國語言
- **說話者偵測**: 整合 pyannote 辨識不同發言者（選配）
- **字幕燒錄**: ASS/SRT 格式支援，FFmpeg 無重編碼高效分割
- **安全設計**: 路徑驗證、Token 環境隔離、Stale Lock 自動回收
- **生產級架構**: WebSocket 即時進度、任務鎖定、自動檔案清理

## 🚀 快速啟動

### 1. 安裝依賴
```bash
# 系統依賴
# Ubuntu: sudo apt install ffmpeg redis-server
# macOS: brew install ffmpeg redis

# Python 環境
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 若需說話者偵測（選配）
# pip install -r requirements-diarization.txt
```

### 2. 環境配置
建立 `.env` 檔案:
```ini
OPENAI_API_KEY=sk-...your-api-key
REDIS_URL=redis://localhost:6379/0
UPLOAD_DIR=./backend/uploads
HF_TOKEN=hf_...your-huggingface-token  # 選配，用於說話者偵測
CORS_ALLOWED_ORIGINS=*
```

### 3. 啟動服務（分別在不同終端機）
```bash
# 終端 1: Redis
redis-server

# 終端 2: Celery Worker
celery -A backend.celery_app:celery_app worker --loglevel=info

# 終端 3: Celery Beat (定時清理)
celery -A backend.celery_app:celery_app beat --loglevel=info

# 終端 4: FastAPI 伺服器
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

訪問 **http://localhost:8000/docs** 查看 API 互動式文件。

## API 快速參考

### 上傳並開始處理（Form 型別）
```bash
curl -X POST http://localhost:8000/upload \
  -F "file=@video.mp4" \
  -F "target_langs=Traditional Chinese" \
  -F "subtitle_format=ass" \
  -F "burn_subtitles=true" \
  -F "remove_silence=false" \
  -F "parallel=true"
```

**支援的參數：**
- `target_langs`: 目標語言清單（逗號分隔，預設: Traditional Chinese）
- `subtitle_format`: 字幕格式 `ass` 或 `srt`（預設: ass）
- `burn_subtitles`: 是否燒錄字幕到影片（預設: true）
- `remove_silence`: 是否移除靜音段落（預設: false）
- `parallel`: 長影片是否使用並行處理（預設: true）

### 查詢進度
```bash
curl http://localhost:8000/status/{task_id}
```

### 獲取字幕內容（支援 format 指定）
```bash
# 優先 ass，否則 srt
curl "http://localhost:8000/subtitle/{task_id}?lang=Traditional_Chinese"

# 指定格式
curl "http://localhost:8000/subtitle/{task_id}?lang=Traditional_Chinese&format=srt"
```

### 編輯字幕（需明確指定格式）
```bash
curl -X PUT http://localhost:8000/subtitle/{task_id} \
  -H "Content-Type: application/json" \
  -d '{
    "content": "編輯後的字幕內容",
    "format": "ass"
  }' \
  -G --data-urlencode "lang=Traditional_Chinese"
```

**行為說明：**
- 編輯字幕檔案（.ass 或 .srt）
- 若已存在 final.mp4，會被刪除以避免包含舊字幕
- **不會自動重新燒錄影片**。若要應用新字幕到影片，應創建新任務或使用專門的 burn endpoint（未來功能）

### 下載結果（支援 format 指定）
```bash
# 下載最終燒錄影片（不指定 lang）
curl http://localhost:8000/download/{task_id} -o result.mp4

# 下載字幕（優先 ass，否則 srt）
curl "http://localhost:8000/download/{task_id}?lang=Traditional_Chinese" -o subtitle.ass

# 下載指定格式字幕
curl "http://localhost:8000/download/{task_id}?lang=Traditional_Chinese&format=srt" -o subtitle.srt
```

**行為說明：**
- 若 final.mp4 不存在則回傳 404
- 本端點只負責下載，不會自動重建影片

### WebSocket 即時進度
```javascript
const ws = new WebSocket('ws://localhost:8000/ws/status/{task_id}');
ws.onmessage = (e) => console.log(JSON.parse(e.data));
```

## 📚 詳細文件

| 文件 | 說明 |
|------|------|
| [DEPLOYMENT.md](DEPLOYMENT.md) | 完整部署步驟與環境配置 |
| [architecture.md](architecture.md) | 系統架構、流程、安全機制 |
| [TEST_PLAN.md](TEST_PLAN.md) | 測試計畫與驗證方式 |

## ✅ 測試

```bash
python -m unittest
```

也可用 pytest（與 unittest 共用同一套測試檔）：

```bash
pytest
```

## 🖥️ 前端（Vue 3 SPA）

前端專案位於 `frontend/`，使用 Vue 3 + Vite + TypeScript + Vue Router + Pinia。

```bash
cd frontend
npm install
npm run dev
```

前後端不同源（不同網域/port）部署時，請設定 `VITE_API_BASE_URL` 指向 FastAPI（此設定同時影響 API request 與下載連結）。詳見 `frontend/README.md`。

## ⚠️ Warnings

後端的 `GET /status/{task_id}` 回應包含 `warnings: string[]`（非致命問題）。前端會在任務狀態頁以列表方式顯示 warnings，但不會把 warnings 當成 error。

## 📥 Download URL（字幕需要明確 lang）

下載字幕時必須提供 `lang`（例如 `Traditional_Chinese`）；前端不會在 API 層用 localStorage 等隱性狀態來推導下載 URL。

## 🔒 安全性

- **路徑驗證**: task_id 必須為 UUID，lang 白名單驗證，防止 path traversal
- **Token 隔離**: HF_TOKEN、OPENAI_API_KEY 只從環境變數讀取，不在 URL 中傳遞
- **CORS 驗證**: 啟動時檢查 allow_origins + allow_credentials 組合合法性
- **檔案驗證**: MIME 僅做初篩（允許 `video/*`、空值、`application/octet-stream`），最終以 ffprobe 判定；大小限制 2GB
- **Stale Lock 回收**: 自動清除 1 小時以上或對應 PID 不存在的鎖定檔

## ⚙️ 環境變數說明

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `OPENAI_API_KEY` | (必需) | OpenAI API 金鑰 |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis 連線位址 |
| `UPLOAD_DIR` | `./backend/uploads` | 檔案上傳與暫存目錄 |
| `HF_TOKEN` | (選配) | 說話者偵測的 Hugging Face token |
| `TRANSLATE_MODEL` | `gpt-4o-mini` | 翻譯使用的模型 |
| `CORS_ALLOWED_ORIGINS` | `*` | 允許的 CORS 來源 |
| `CORS_ALLOW_CREDENTIALS` | `false` | 是否允許 credentials（與 `*` 衝突） |

## 📊 性能指標

- **影片驗證**: <5 秒 (ffprobe)
- **短影片轉錄** (<60s): ~5-10 分鐘
- **長影片加速** (>60s): 3-5 倍平行加速
- **翻譯批次**: 30 句/批，降低 API 成本
- **任務超時**: 30 分鐘 soft，35 分鐘 hard

## 🗂️ 專案結構
```
ai_subtitle_tool/
├── backend/
│   ├── main.py                    # FastAPI 應用入口
│   ├── celery_app.py              # Celery 配置與 Beat 定時任務
│   ├── tasks.py                   # 核心異步任務定義
│   └── utils/
│       ├── subtitle_utils.py      # Whisper 轉錄
│       ├── translate_utils.py     # OpenAI 翻譯（lazy init）
│       ├── split_utils.py         # 影片分段與去重
│       ├── diarization_utils.py   # 說話者偵測（選配）
│       ├── ass_utils.py           # ASS 格式生成
│       ├── video_utils.py         # FFmpeg 操作
│       ├── model_loader.py        # Whisper 模型選擇
│       └── audio_utils.py         # 音訊處理
├── DEPLOYMENT.md                  # 部署指南
├── architecture.md                # 架構文件
├── TEST_PLAN.md                   # 測試計畫
├── requirements.txt               # Python 依賴（含 psutil）
└── requirements-diarization.txt   # 說話者偵測依賴（選配）
```

## 🛣️ 已知限制 & 改進空間

- **無前端**: 本版本為純 API，建議搭配自定義客戶端
- **無資料庫**: 狀態存於 Redis，結果存於檔案系統
- **單機部署**: 未配置分佈式高可用 (HA)
- **無身份驗證**: 建議在 Nginx/LB 層添加認證

## 📝 更新日誌

### v2.0 (current)
- ✅ 修正 diarization 邏輯縮排與控制流
- ✅ 字幕編輯 API 格式隔離（.ass 與 .srt 分別編輯）
- ✅ 路徑安全驗證（UUID、lang 白名單、traversal 防護）
- ✅ CORS 配置驗證（避免非法 credentials 組合）
- ✅ 移除 query string hf_token，改用環境變數
- ✅ split_utils 加入 overlap 去重（時間接近 + 簡單 normalize）
- ✅ Stale lock 自動回收（1 小時或 PID 不存在）
- ✅ 任務提交失敗時清理已上傳檔案
- ✅ 檔案上傳驗證加強 (ffprobe、大小限制)
- ✅ translate_utils OpenAI client lazy init
- ✅ warnings 保序去重 (dict.fromkeys)

## 📞 支援與反饋

如遇問題，請檢查 [DEPLOYMENT.md](DEPLOYMENT.md) 的常見問題排除章節或查閱 [architecture.md](architecture.md)。

---

**本專案為純後端 API 實作，採用生產級設計，致力於穩定、安全、高效的影片字幕自動化處理。**
