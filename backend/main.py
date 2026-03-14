import os
import uuid
import asyncio
from fastapi import FastAPI, UploadFile, File, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict
from tasks import process_video_task
from celery.result import AsyncResult
from celery_app import celery_app

app = FastAPI(title="AI Video Subtitle Tool")

# CORS 設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "/home/ubuntu/ai_subtitle_tool/backend/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

class TaskStatus(BaseModel):
    task_id: str
    status: str
    progress: int
    result_url: Optional[str] = None

class TaskOptions(BaseModel):
    target_langs: list = ["Traditional Chinese"]
    burn_subtitles: bool = True
    subtitle_format: str = "ass"
    remove_silence: bool = False
    hf_token: Optional[str] = None

class SubtitleEdit(BaseModel):
    content: str # 新的 SRT 內容

@app.post("/upload", response_model=TaskStatus)
async def upload_video(
    file: UploadFile = File(...),
    target_langs: str = "Traditional Chinese", # 接收逗號分隔字串
    burn_subtitles: bool = True,
    subtitle_format: str = "ass",
    remove_silence: bool = False,
    hf_token: Optional[str] = None
):
    if not file.filename.endswith((".mp4", ".mkv", ".avi", ".mov")):
        raise HTTPException(status_code=400, detail="Unsupported file format")
    
    task_id = str(uuid.uuid4())
    file_extension = os.path.splitext(file.filename)[1]
    file_path = os.path.join(UPLOAD_DIR, f"{task_id}{file_extension}")
    
    with open(file_path, "wb") as buffer:
        content = await file.read()
        buffer.write(content)
    
    options = {
        "target_langs": target_langs.split(","),
        "burn_subtitles": burn_subtitles,
        "subtitle_format": subtitle_format,
        "remove_silence": remove_silence,
        "hf_token": hf_token
    }
    
    # 啟動 Celery 任務
    task = process_video_task.delay(file_path, options)
    
    return TaskStatus(task_id=task.id, status="PENDING", progress=0)

@app.get("/status/{task_id}", response_model=TaskStatus)
async def get_status(task_id: str):
    task_result = AsyncResult(task_id, app=celery_app)
    
    status = task_result.status
    progress = 0
    result_url = None
    
    if status == "PROGRESS":
        progress = task_result.info.get("progress", 0)
    elif status == "SUCCESS":
        progress = 100
        result_url = f"/download/{task_id}"
    elif status == "FAILURE":
        progress = 0
        
    return TaskStatus(
        task_id=task_id,
        status=status,
        progress=progress,
        result_url=result_url
    )

@app.websocket("/ws/status/{task_id}")
async def websocket_status(websocket: WebSocket, task_id: str):
    await websocket.accept()
    try:
        while True:
            task_result = AsyncResult(task_id, app=celery_app)
            status = task_result.status
            progress = 0
            
            if status == "PROGRESS":
                progress = task_result.info.get("progress", 0)
            elif status == "SUCCESS":
                progress = 100
            
            await websocket.send_json({
                "task_id": task_id,
                "status": status,
                "progress": progress
            })
            
            if status in ["SUCCESS", "FAILURE", "REVOKED"]:
                break
                
            await asyncio.sleep(1) # 每秒推送一次
    except WebSocketDisconnect:
        print(f"Client disconnected from task {task_id}")
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        await websocket.close()

@app.get("/subtitle/{task_id}")
async def get_subtitle(task_id: str):
    # 尋找該任務對應的 SRT 檔案
    srt_path = os.path.join(UPLOAD_DIR, f"{task_id}_bilingual.srt")
    if not os.path.exists(srt_path):
        srt_path = os.path.join(UPLOAD_DIR, f"{task_id}.srt")
        
    if not os.path.exists(srt_path):
        raise HTTPException(status_code=404, detail="Subtitle not found")
        
    with open(srt_path, "r", encoding="utf-8") as f:
        return {"content": f.read()}

@app.put("/subtitle/{task_id}")
async def update_subtitle(task_id: str, edit: SubtitleEdit):
    srt_path = os.path.join(UPLOAD_DIR, f"{task_id}_bilingual.srt")
    if not os.path.exists(srt_path):
        srt_path = os.path.join(UPLOAD_DIR, f"{task_id}.srt")
        
    if not os.path.exists(srt_path):
        raise HTTPException(status_code=404, detail="Subtitle not found")
        
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(edit.content)
        
    return {"status": "updated"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
