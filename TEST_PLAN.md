# AI 自動影片上字幕工具 - 測試計畫

本文件描述「目前版本」可實際驗證的測試方式；未涵蓋的項目一律列在手動整合測試中，避免文件比程式更自信。

## 1. 自動化行為測試（建議）

執行方式：

```bash
pytest
```

測試位置：`tests/test_behavior.py`

### 自動化測試覆蓋範圍

- `finalize_pipeline()` / merge：segment payload 統一格式驗證與「單點」轉換（dict -> SimpleSegment 後才進入 merge）
- 平行分段：`transcribe_segment_task()` 會回傳完整 metadata（`start_offset/end_offset/overlap/segment_idx`）且在成功後主動清理自己的 `temp_srt`
- overlap 去重：`merge_segments_subtitles()` 在 overlap 區使用「時間接近 + 簡單 normalize」去重（空白/大小寫/前後標點）
- 字幕編輯：`PUT /subtitle/{task_id}` 只更新指定格式、不污染其他格式；更新後會刪除 `{task_id}_final.mp4`（若存在）
- 字幕/下載：`GET /subtitle/{task_id}` / `GET /download/{task_id}` 能回對應檔案；`final.mp4` 不存在時 `/download` 回 404
- 上傳驗證：`POST /upload` MIME 僅做初篩（允許 `video/*`、空值、`application/octet-stream`），最終以 `ffprobe` 判定
- 安全性：`validate_path_traversal()` 防止路徑逃逸；`/results/{task_id}` 的 manifest 檔名解析（語言後綴含 `.`）

## 1.1 前端自動化測試（建議）

前端測試使用 Vitest，並假設在乾淨環境中先安裝依賴（release package 不應包含 `node_modules/`）：

```bash
cd frontend
rm -rf node_modules
npm install
npm test
```

前端建置驗證：

```bash
npm run build
```

## 1.2 Release 打包驗證（建議）

Release zip 需由單一 source tree 透過腳本產生（不可內嵌 `node_modules/` 或保留第二份 `release_pkg/` source 副本）。

```bash
# from repo root
powershell -ExecutionPolicy Bypass -File .\\make_release_zip.ps1
```

預設輸出：`release_out/ai_subtitle_tool_release.zip`

建議再做一次內容檢查（避免把 `.git/`、`node_modules/`、`dist/`、`__pycache__/`、測試快取等打進交付包）：

```bash
tar -tf release_out/ai_subtitle_tool_release.zip | rg "(^|/)(\\.git|node_modules|dist|__pycache__|_tmp|_tmp_mplconfig|\\.pytest_cache|htmlcov|\\.coverage)(/|$)"
```

（Windows 若無 `rg`，可用 PowerShell `Select-String` 替代；重點是檢查 forbidden paths 不存在。）

## 1.3 API Smoke Test（建議）

本專案的 API 行為 smoke test 已由 `pytest` 覆蓋（見 `tests/test_behavior.py`）。建議驗收時至少執行：

```bash
python -m pytest -q
```

## 2. 手動整合測試（需要 ffmpeg/redis/celery/模型環境）

以下項目需要實際環境與外部依賴（ffmpeg、redis、celery worker、whisper 模型、OpenAI API），不納入自動化行為測試：

- 長影片平行處理端到端（切片 -> chord -> 合併 -> 產出字幕）
- `burn_subtitles=true` 的影片燒錄結果
- `remove_silence=true` 的剪輯結果
- 翻譯與重試策略（需要可控的網路/外部 API）
- diarization（需要 HF_TOKEN 與額外依賴）

建議至少用 30 秒與 5 分鐘兩種影片各跑一次，並在 `/status/{task_id}` / WebSocket 觀察進度與結果檔案是否正確產出。
