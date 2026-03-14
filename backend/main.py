import os
import uuid
import asyncio
import shutil
from fastapi import FastAPI, UploadFile, File, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any
from .tasks import process_video_task
from celery.result import AsyncResult
from .celery_app import celery_app

app = FastAPI(title="AI Video Subtitle Tool")

# CORS 設定 - 支援環境變數配置
allowed_origins = os.getenv("CORS_ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
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
    # A) 修復 Pydantic Model 用「可變預設值」[]
    warnings: List[str] = Field(default_factory=list)

class SubtitleEdit(BaseModel):
    content: str

class FileInfo(BaseModel):
    lang: str
    display_name: str
    ass: bool
    srt: bool

class TaskResultManifest(BaseModel):
    task_id: str
    has_video: bool
    subtitle_languages: List[str]
    available_files: List[FileInfo]
    # A) 修復 Pydantic Model 用「可變預設值」[]
    warnings: List[str] = Field(default_factory=list)

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
    warnings = []
    
    if status == "PROGRESS":
        info = task_result.info or {}
        progress = info.get("progress", 0)
        message = info.get("status", "")
    elif status == "SUCCESS":
        progress = 100
        message = "Completed"
        result_url = f"/results/{task_id}"
        if isinstance(task_result.result, dict):
            warnings = task_result.result.get("warnings", [])
    elif status == "FAILURE":
        message = str(task_result.result)
    elif status == "PENDING":
        message = "Waiting for worker..."
        
    return TaskStatus(task_id=task_id, status=status, progress=progress, message=message, result_url=result_url, warnings=warnings)

@app.get("/results/{task_id}", response_model=TaskResultManifest)
async def get_results_manifest(task_id: str):
    task_result = AsyncResult(task_id, app=celery_app)
    warnings = []
    if task_result.status == "SUCCESS" and isinstance(task_result.result, dict):
        warnings = task_result.result.get("warnings", [])

    has_video = os.path.exists(os.path.join(UPLOAD_DIR, f"{task_id}_final.mp4"))
    
    files = [f for f in os.listdir(UPLOAD_DIR) if f.startswith(f"{task_id}_")]
    
    lang_map = {}
    for f in files:
        if f.endswith((".ass", ".srt")):
            parts = f.replace(f"{task_id}_", "").split(".")
            if len(parts) < 2: continue
            lang_suffix = parts[0]
            ext = parts[1]
            if lang_suffix not in lang_map:
                lang_map[lang_suffix] = {"ass": False, "srt": False}
            lang_map[lang_suffix][ext] = True
            
    available_files = []
    for lang_suffix, exts in lang_map.items():
        display_name = lang_suffix.replace("_", " ")
        available_files.append(FileInfo(
            lang=lang_suffix, 
            display_name=display_name,
            ass=exts["ass"], 
            srt=exts["srt"]
        ))
        
    return TaskResultManifest(
        task_id=task_id,
        has_video=has_video,
        subtitle_languages=[f.display_name for f in available_files],
        available_files=available_files,
        warnings=warnings
    )

@app.get("/download/{task_id}")
async def download_result(task_id: str, lang: Optional[str] = Query(None, description="Language for subtitle (e.g. Traditional_Chinese)")):
    final_video = os.path.join(UPLOAD_DIR, f"{task_id}_final.mp4")
    if os.path.exists(final_video) and not lang:
        return FileResponse(final_video, filename=f"video_{task_id}.mp4")
    
    if not lang:
        raise HTTPException(status_code=400, detail="Please specify 'lang' parameter for subtitles")

    lang_suffix = lang.replace(" ", "_")
    for ext in ["ass", "srt"]:
        target_file = os.path.join(UPLOAD_DIR, f"{task_id}_{lang_suffix}.{ext}")
        if os.path.exists(target_file):
            return FileResponse(target_file, filename=f"subtitle_{task_id}_{lang_suffix}.{ext}")
            
    raise HTTPException(status_code=404, detail=f"Result for language '{lang}' not found")

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
    # A) WebSocket finally 一律 close()，在已斷線情境可能丟例外 -> 移除 finally close
    # FastAPI/Starlette 會自動處理

@app.get("/subtitle/{task_id}")
async def get_subtitle(task_id: str, lang: str = Query(..., description="Language for subtitle")):
    lang_suffix = lang.replace(" ", "_")
    for ext in ["ass", "srt"]:
        filename = f"{task_id}_{lang_suffix}.{ext}"
        path = os.path.join(UPLOAD_DIR, filename)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return {"content": f.read(), "format": ext, "filename": filename}
    raise HTTPException(status_code=404, detail=f"Subtitle for language '{lang}' not found")

@app.put("/subtitle/{task_id}")
async def update_subtitle(task_id: str, edit: SubtitleEdit, lang: str = Query(..., description="Language for subtitle")):
    lang_suffix = lang.replace(" ", "_")
    updated = False
    for ext in ["ass", "srt"]:
        filename = f"{task_id}_{lang_suffix}.{ext}"
        path = os.path.join(UPLOAD_DIR, filename)
        if os.path.exists(path):
            with open(path, "w", encoding="utf-8") as file:
                file.write(edit.content)
            updated = True
    if not updated:
        raise HTTPException(status_code=404, detail=f"Subtitle for language '{lang}' not found")
    return {"status": "updated"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
