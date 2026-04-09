# AI 自動影片上字幕工具 - 架構說明

本文件描述目前程式碼的真實行為與責任邊界（偏保守）。

## 1. 技術棧

- Backend：FastAPI + Uvicorn
- 任務隊列：Celery + Redis
- 影音處理：FFmpeg / ffprobe
- STT：faster-whisper
- 翻譯：OpenAI（由 `TRANSLATE_MODEL` 決定）
- （選配）說話者偵測：pyannote（需 HF_TOKEN 與額外依賴）

## 2. Pipeline 概覽

1. `POST /upload`
   - 先做「弱」MIME 初篩（允許 `video/*`、空值、`application/octet-stream`）
   - 再用 `ffprobe` 做最終影片有效性判定
   - 檔案寫入 `UPLOAD_DIR` 後，enqueue Celery 任務

2. `process_video_task()`
   - 依影片長度與設定決定平行或非平行流程
   - 平行流程：`split_video()` 產生切片資訊 -> `transcribe_segment_task()` 並行 -> `merge_and_finalize_task()`
   - 非平行流程：直接轉錄整段 -> 進入 `finalize_pipeline()`

3. `finalize_pipeline()`
   - **只接受統一的 segment payload（dict 結構）**，不在內部默默相容多種格式
   - 進入 `merge_segments_subtitles()` 前，在單一地方把 segment 轉為 `SimpleSegment`
   - 上層以 try/finally 對 `segments_dir` 做保底清理；清理失敗只記 log

## 3. 統一的 Segment Payload 格式

任務間交換資料一律使用 dict；`finalize_pipeline()` 只接受下列格式：

```python
{
  "start_offset": float,
  "end_offset": float,
  "overlap": float,
  "segment_idx": int,
  "segments": [
    {"start": float, "end": float, "text": str},
    ...
  ]
}
```

- 平行流程由 `transcribe_segment_task()` 產生此格式
- 非平行流程也會用同一格式包裝後再呼叫 `finalize_pipeline()`

## 4. Overlap 去重策略（保守且可預測）

`merge_segments_subtitles()` 在 overlap 區段做去重：

- 條件：時間接近（< 0.5s）
- 文字比對：使用簡單 normalize（strip、空白壓縮、lower、去掉前後標點）後再做相等比較
- 不做模糊比對、不做複雜 NLP，以避免誤刪

## 5. 暫存檔清理策略（局部清理 + 全域保底）

- `transcribe_segment_task()`：成功後主動刪除自己的 `temp_srt`
- `finalize_pipeline()`：仍保留對整個 `segments_dir` 的保底清理（清理失敗只記 log）

## 6. 字幕編輯責任邊界

`PUT /subtitle/{task_id}` 只負責更新指定格式的字幕檔案：

- 成功寫入字幕後，若 `{task_id}_final.mp4` 存在會嘗試刪除以避免舊字幕被誤用
- 不會自動重建影片；若要將新字幕燒錄進影片，需重新執行任務或另外提供明確的 burn/rebuild endpoint
