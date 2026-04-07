# AI Subtitle Tool Frontend (Vue 3 + Vite + TS)

目標：提供一個可直接串接既有 FastAPI 後端的 SPA，完成：
1) 上傳影片與選項 → 建立任務  
2) 輪詢任務狀態  
3) 檢視 / 編輯字幕（ass / srt）  
4) 下載結果（final.mp4 / ass / srt）

## 目錄

- `src/api/`：統一 API 封裝（不要散落呼叫）
- `src/stores/`：所有非同步行為集中在 Pinia store
- `src/pages/`：頁面只負責組裝元件與呼叫 store action
- `src/components/`：小元件各司其職

## 啟動

```bash
cd frontend
rm -rf node_modules
npm install
npm run dev
```

Build：

```bash
npm run build
npm run preview
```

測試：

```bash
npm test
```

## 環境變數

前端使用 `VITE_API_BASE_URL` 作為後端 API base URL（見 `.env.example`）。

重要：此 base URL **同時影響**：
- 所有 API request（例如 `/upload`、`/status/:taskId`、`/subtitle/:taskId`、`/results/:taskId`）
- 下載連結 URL（例如 `/download/:taskId?...`）

- **同網域部署**：不需要設定（留空），前端會用相對路徑呼叫 `/upload`、`/status/...` 等 API
- **分開開發**：建議設成 `http://localhost:8000`（或你的後端位置）

## API Base URL 設定

1. 複製 `.env.example` 成 `.env.local`
2. 設定：

```ini
VITE_API_BASE_URL=http://localhost:8000
```

## 重要業務規則（已在 UI 明確呈現）

- **字幕編輯只更新字幕檔**，不會自動重建影片
- **下載頁只負責下載**已存在的結果，不會做隱性背景工作
- **任務輪詢集中管理**：離開狀態頁會停止輪詢；任務到終態（SUCCESS/FAILURE/REVOKED）也會自動停止
- **Warnings 會顯示但不視為 error**：後端 status response 的 `warnings` 會以列表呈現，方便使用者理解非致命問題

## 假設

- 後端上傳參數與 FastAPI `POST /upload` 對齊（multipart/form-data）
- 字幕/下載需要 `lang`：
  - 語言選項優先來自 `GET /results/{task_id}` 的 manifest（`available_files`）
  - 字幕頁與下載頁都有明確的 Language selector
  - 仍會把使用者選擇寫入 localStorage 作偏好（不是唯一控制來源）

## Download URL 規則

- 下載字幕時，前端會**明確帶上** `lang`（不會在 API 層依賴 localStorage 來拼 URL）
- 下載影片（final.mp4）不需要 `lang`
