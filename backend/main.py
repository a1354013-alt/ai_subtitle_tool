import os
import uuid
import asyncio
import shutil
from fastapi import FastAPI, UploadFile, File, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, List
from .tasks import process_video_task
from celery.result import AsyncResult
from .celery_app import celery_app

app = FastAPI(title="AI Video Subtitle Tool")

# CORS 設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 環境配置
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.getenv("UPLOAD_DIR", os.path.join(BASE_DIR, "uploads"))
os.makedirs(UPLOAD_DIR, exist_ok=True)

class TaskStatus(BaseModel):
    task_id: str
    status: str
    progress: int
    message: Optional[str] = None
    result_url: Optional[str] = None

class SubtitleEdit(BaseModel):
    content: str

@app.post("/upload", response_model=TaskStatus)
async def upload_video(
    file: UploadFile = File(...),
    target_langs: str = Query("Traditional Chinese", description="Comma separated languages"),
    burn_subtitles: bool = True,
    subtitle_format: str = "ass",
    remove_silence: bool = False,
    parallel: bool = True,
    hf_token: Optional[str] = None
):
    if not file.filename.lower().endswith((".mp4", ".mkv", ".avi", ".mov")):
        raise HTTPException(status_code=400, detail="Unsupported file format")
    
    task_id = str(uuid.uuid4())
    file_extension = os.path.splitext(file.filename)[1]
    file_path = os.path.join(UPLOAD_DIR, f"{task_id}{file_extension}")
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
    finally:
        file.file.close()
    
    options = {
        "business_id": task_id,
        "target_langs": [l.strip() for l in target_langs.split(",")],
        "burn_subtitles": burn_subtitles,
        "subtitle_format": subtitle_format,
        "remove_silence": remove_silence,
        "parallel": parallel,
        "hf_token": hf_token
    }
    
    process_video_task.apply_async(args=[file_path, options], task_id=task_id)
    
    return TaskStatus(task_id=task_id, status="PENDING", progress=0)

@app.get("/status/{task_id}", response_model=TaskStatus)
async def get_status(task_id: str):
    task_result = AsyncResult(task_id, app=celery_app)
    
    status = task_result.status
    progress = 0
    message = ""
    result_url = None
    
    if status == "PROGRESS":
        info = task_result.info or {}
        progress = info.get("progress", 0)
        message = info.get("status", "")
    elif status == "SUCCESS":
        progress = 100
        message = "Completed"
        result_url = f"/download/{task_id}"
    elif status == "FAILURE":
        message = str(task_result.result)
    elif status == "PENDING":
        message = "Waiting for worker..."
        
    return TaskStatus(task_id=task_id, status=status, progress=progress, message=message, result_url=result_url)

@app.get("/download/{task_id}")
async def download_result(task_id: str, lang: Optional[str] = None):
    final_video = os.path.join(UPLOAD_DIR, f"{task_id}_final.mp4")
    if os.path.exists(final_video) and not lang:
        return FileResponse(final_video, filename=f"video_{task_id}.mp4")
    
    for ext in ["ass", "srt"]:
        if lang:
            lang_suffix = lang.replace(" ", "_")
            target_file = os.path.join(UPLOAD_DIR, f"{task_id}_{lang_suffix}.{ext}")
            if os.path.exists(target_file):
                return FileResponse(target_file, filename=f"subtitle_{task_id}_{lang_suffix}.{ext}")
        else:
            files = [f for f in os.listdir(UPLOAD_DIR) if f.startswith(f"{task_id}_") and f.endswith(f".{ext}")]
            if files:
                return FileResponse(os.path.join(UPLOAD_DIR, files[0]), filename=f"subtitle_{task_id}.{ext}")
            
    raise HTTPException(status_code=404, detail="Result not found")

@app.websocket("/ws/status/{task_id}")
async def websocket_status(websocket: WebSocket, task_id: str):
    await websocket.accept()
    try:
        while True:
            res = await get_status(task_id)
            await websocket.send_json(res.dict())
            if res.status in ["SUCCESS", "FAILURE", "REVOKED"]:
                break
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass
    finally:
        await websocket.close()

@app.get("/subtitle/{task_id}")
async def get_subtitle(task_id: str, lang: Optional[str] = None):
    for ext in ["ass", "srt"]:
        pattern = f"{task_id}_"
        if lang: pattern += lang.replace(" ", "_")
        
        files = [f for f in os.listdir(UPLOAD_DIR) if f.startswith(pattern) and f.endswith(f".{ext}")]
        if files:
            path = os.path.join(UPLOAD_DIR, files[0])
            with open(path, "r", encoding="utf-8") as f:
                return {"content": f.read(), "format": ext, "filename": files[0]}
    raise HTTPException(status_code=404, detail="Subtitle not found")

@app.put("/subtitle/{task_id}")
async def update_subtitle(task_id: str, edit: SubtitleEdit, lang: Optional[str] = None):
    updated = False
    for ext in ["ass", "srt"]:
        pattern = f"{task_id}_"
        if lang: pattern += lang.replace(" ", "_")
        
        files = [f for f in os.listdir(UPLOAD_DIR) if f.startswith(pattern) and f.endswith(f".{ext}")]
        for f in files:
            path = os.path.join(UPLOAD_DIR, f)
            with open(path, "w", encoding="utf-8") as file:
                file.write(edit.content)
            updated = True
    if not updated:
        raise HTTPException(status_code=404, detail="Subtitle not found")
    return {"status": "updated"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
