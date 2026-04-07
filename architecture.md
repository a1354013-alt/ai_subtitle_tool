# AI 自動影片上字幕與剪輯工具 - 系統架構

## 1. 技術選型 (Tech Stack)
*   **Backend**: FastAPI + Uvicorn (高效能非同步 API)
*   **Task Queue**: Celery + Redis (異步任務處理、並行辨識)
*   **AI Models**: 
    *   **Faster-Whisper**: 語音轉文字 (離線、快速、支援多語言)
    *   **OpenAI GPT-4o-mini**: 高品質多語言翻譯
    *   **Pyannote (選配)**: 說話者偵測與分類
*   **Multimedia**: FFmpeg (分割、驗證、倍速調整、字幕燒錄)
*   **Infrastructure**: 無資料庫設計（檔案系統存儲狀態與結果）

## 2. 核心處理流程

```
1. 上傳影片 → 驗證格式、大小、ffprobe 確認
                 ↓
2. 產生 task_id (UUID) → 建立 .lock 檔
                 ↓
3. 分析影片時長 → 決定模型規模 (tiny/small/medium/base)
                 ↓
4. 決定執行策略：
   ├─ 短影片 (≤60s): 直接轉錄
   └─ 長影片 (>60s): 
       ├─ 分段 (30s/段，2s overlap) → 平行轉錄
       ├─ 去除重疊字幕
       └─ 合併結果
                 ↓
5. 轉錄字幕 → SimpleSegment(start, end, text) 物件
                 ↓
6. 說話者偵測 (若 HF_TOKEN 有效)
                 ↓
7. 多語種翻譯 (批次 30 句)
                 ↓
8. 生成字幕檔：
   └─ .srt (SRT 格式)
   └─ .ass (進階字幕格式，支援風格化)
                 ↓
9. 字幕燒錄到影片（可選）
                 ↓
10. 清理 .lock，完成任務
```

## 3. 關鍵安全機制

### 路徑安全驗證
```python
- task_id: 必須是合法 UUID
- lang: 只允許 [a-zA-Z0-9_-]
- 所有檔案路徑必須 resolve() 後在 UPLOAD_DIR 內
- 防止 path traversal 攻擊
```

### 認證與授權
```python
- HF_TOKEN: 從環境變數 (非 URL query string)
- OPENAI_API_KEY: 從環境變數
- 不在 URL、Access Log、Proxy Log 中洩露 token
```

### 鎖定與清理
```python
- .lock 檔: 記錄 PID 與 timestamp
- Stale Lock 回收: >1 小時或 PID 不存在 → 自動清除
- 檔案保留: 24 小時後自動刪除
- 任務提交失敗: 立即清理已上傳檔案
```

## 4. 文件與資料結構

### 上傳目錄結構
```
./backend/uploads/
├── {task_id}.mov              # 原始上傳檔案
├── {task_id}.lock             # 任務鎖定檔 (JSON: PID, timestamp)
├── {task_id}_no_silence.mp4   # 去靜音版本（若啟用）
├── {task_id}_segments/        # 分段暫存目錄
│   ├── seg_000_0_30.mp4
│   ├── seg_001_28_60.mp4      # 含 2s overlap
│   └── ...
├── {task_id}.srt              # 轉錄字幕 (STT 結果)
├── {task_id}_Traditional_Chinese.srt
├── {task_id}_Traditional_Chinese.ass
├── {task_id}_final.mp4        # 燒錄後的最終影片
└── ...
```

### Task 狀態流程
```
PENDING → PROGRESS → SUCCESS/FAILURE/REVOKED
```

## 5. 並行化策略

### 單 Worker 的並行分段轉錄 (Celery Chord)
```python
# 任務 DAG:
├─ transcribe_segment_task(seg_0, model)  \
├─ transcribe_segment_task(seg_1, model)  ├─ Chord 並行執行
└─ transcribe_segment_task(seg_n, model)  /
                              ↓
                  merge_and_finalize_task(results)  # 唯一匯聚點
```

### 翻譯批次化
```python
# 30 句一批，5 次重試自動 backoff
for batch in batches(segments, batch_size=30):
    translated = translate_batch(batch, source, target_lang)
    # 若格式錯誤自動重試，最多 5 次
```

## 6. 錯誤恢復與降級

| 情境 | 行為 |
|------|------|
| **Diarization 依賴缺失** | 記錄 warning，跳過 speaker label |
| **說話者偵測失敗** | 保留原字幕，記錄 warning |
| **翻譯 API 失敗** (5 次重試後) | fallback 使用原文，記錄 warning |
| **字幕燒錄失敗** | 複製原影片，不含字幕，記錄 warning |
| **任務提交失敗** | 清理已上傳檔案，回傳錯誤 |
| **Stale lock** | 自動清除，允許重新執行 |

## 7. 性能特性

| 項目 | 目標 | 備註 |
|------|------|------|
| 影片上傳驗證 | <5s | ffprobe 驗證有效性 |
| 分段策略 | 100% 無重編碼 | `-c copy` 高效分割 |
| 並行效率 | ~3-5×加速 | 取決於 CPU 核心數 |
| 翻譯批次 | 30 句/批 | 降低 API 成本 |
| 任務超時 | 30 分鐘 soft, 35 分鐘 hard | 可於 celery_app.py 調整 |
| Lock 回收 | 1 小時 stale | Celery beat 每小時檢查 |

## 8. 依賴關係

### 核心 (必需)
- fastapi, uvicorn, pydantic
- celery, redis
- faster-whisper, openai
- moviepy, ffmpeg

### 可選 (說話者偵測)
- pyannote.audio, librosa
- HuggingFace Hub token

## 9. 已知限制

1. **無前端**: 本版本為純 API，前端需自行實作或使用 API 客戶端
2. **無資料庫**: 依賴檔案系統與 Redis，不支援分佈式存儲
3. **單機 Celery**: 未配置高可用 (HA)，重啟會遺失已發送但未執行的任務
4. **無驗證系統**: API 無身份驗證，建議於 Nginx/Load Balancer 層添加
