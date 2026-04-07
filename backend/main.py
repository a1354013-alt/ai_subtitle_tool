import os
import uuid
import asyncio
import shutil
import re
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException, WebSocket, WebSocketDisconnect, Query, Form
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Any
from .tasks import process_video_task
from celery.result import AsyncResult
from .celery_app import celery_app

app = FastAPI(title="AI Video Subtitle Tool")

# CORS 設定 - 支援環境變數配置，並驗證合法性
def configure_cors():
    """驗證並配置 CORS 設定，避免不正確的 wildcards + credentials 組合"""
    allowed_origins_str = os.getenv("CORS_ALLOWED_ORIGINS", "*")
    allow_credentials = os.getenv("CORS_ALLOW_CREDENTIALS", "false").lower() == "true"
    
    origins = [o.strip() for o in allowed_origins_str.split(",") if o.strip()]
    
    # 驗證：不能同時使用 wildcards 和 credentials
    if "*" in origins and allow_credentials:
        raise ValueError(
            "Invalid CORS configuration: cannot use allow_origins=['*'] with allow_credentials=True. "
            "Either: (1) use explicit origin whitelist with credentials, or (2) use '*' without credentials."
        )
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

configure_cors()

# 環境配置
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.getenv("UPLOAD_DIR", os.path.join(BASE_DIR, "uploads"))
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 路徑安全驗證工具
def validate_task_id(task_id: str) -> str:
    """驗證 task_id 為合法 UUID 格式"""
    try:
        uuid.UUID(task_id)
        return task_id
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid task_id format: {task_id}. Must be a valid UUID.")

def validate_lang(lang: str) -> str:
    """驗證 lang 只包含允許的字元（英數、底線、連字號）"""
    if not re.match(r'^[a-zA-Z0-9_-]+$', lang):
        raise HTTPException(status_code=400, detail=f"Invalid lang format: '{lang}'. Only alphanumeric, underscore, and hyphen allowed.")
    return lang

def validate_path_traversal(filepath: str, allowed_root: str) -> str:
    """
    P1.6: 驗證路徑不會超出預期根目錄，並回傳安全的 normalized path。
    這避免同一路徑在不同地方出現不同表示法的問題。
    
    Args:
        filepath: 要驗證的檔案路徑
        allowed_root: 允許的根目錄
    
    Returns:
        安全的 normalized path 字串，用於後續所有檔案操作
    
    Raises:
        HTTPException: 若路徑逃逸或不在允許範圍內
    """
    resolved_path = Path(filepath).resolve()
    resolved_root = Path(allowed_root).resolve()
    
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError:
        raise HTTPException(
            status_code=400, 
            detail=f"Path traversal detected: {filepath} is outside allowed directory."
        )
    
    # 回傳安全的字串表示，避免路徑在不同地方用不同格式
    return str(resolved_path)

class TaskStatus(BaseModel):
    task_id: str
    status: str
    progress: int
    message: Optional[str] = None
    result_url: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)

class SubtitleEditRequest(BaseModel):
    """字幕編輯請求，需要指定編輯格式"""
    content: str
    format: str = Field(..., description="Target subtitle format: 'ass' or 'srt'")

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
    warnings: List[str] = Field(default_factory=list)

@app.post("/upload", response_model=TaskStatus)
async def upload_video(
    file: UploadFile = File(...),
    target_langs: str = Form("Traditional Chinese", description="Comma separated languages"),
    burn_subtitles: bool = Form(True, description="Whether to burn subtitles into video"),
    subtitle_format: str = Form("ass", description="Subtitle format: ass or srt"),
    remove_silence: bool = Form(False, description="Remove silence from video"),
    parallel: bool = Form(True, description="Use parallel processing for long videos")
):
    """
    上傳影片並開始處理任務。
    
    說話者偵測使用環境變數 HF_TOKEN 配置（不通過 URL 傳遞）。
    """
    # 1. P1.7 MIME 初篩：簡單的內容類型檢查
    if file.content_type and not file.content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail=f"Invalid content type: {file.content_type}. Expected video/*")
    
    # 2. 驗證副檔名
    if not file.filename.lower().endswith((".mp4", ".mkv", ".avi", ".mov")):
        raise HTTPException(status_code=400, detail="Unsupported file format. Supported: mp4, mkv, avi, mov")
    
    # 2.5. 驗證 subtitle_format 白名單
    if subtitle_format not in ("ass", "srt"):
        raise HTTPException(status_code=400, detail="subtitle_format must be 'ass' or 'srt'")
    
    # 3. 生成 task_id（自動 UUID）
    task_id = str(uuid.uuid4())
    file_extension = os.path.splitext(file.filename)[1]
    file_path = os.path.join(UPLOAD_DIR, f"{task_id}{file_extension}")
    
    # 4. 驗證檔案大小（限制最大 2GB）
    file.file.seek(0, 2)  # 移到檔案末端
    file_size = file.file.tell()
    file.file.seek(0)  # 重置指標
    
    max_file_size = 2 * 1024 * 1024 * 1024  # 2GB
    if file_size > max_file_size:
        raise HTTPException(status_code=413, detail=f"File too large. Maximum size: 2GB, got: {file_size / (1024*1024):.1f}MB")
    
    # 5. 驗證路徑不超出允許範圍，並取得安全的 normalized path
    file_path = validate_path_traversal(file_path, UPLOAD_DIR)
    
    # 6. 儲存檔案
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        # 清理已上傳的檔案
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
    finally:
        file.file.close()
    
    # 7. 驗證上傳檔案是否為可讀影片（使用 ffprobe 驗證）
    # 真正的格式驗證以 ffprobe 為準，MIME 只是初篩
    try:
        import subprocess
        ffprobe_result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_type", "-of", "csv=p=0", file_path],
            capture_output=True,
            text=True,
            timeout=5
        )
        if ffprobe_result.returncode != 0 or "video" not in ffprobe_result.stdout:
            raise ValueError("Not a valid video file")
    except Exception as e:
        # 驗證失敗，清理檔案
        try:
            os.remove(file_path)
        except:
            pass
        raise HTTPException(status_code=400, detail=f"Invalid video file: {str(e)}")
    
    # 8. 組織選項（hf_token 從環境變數取得，不從 URL 傳遞）
    options = {
        "business_id": task_id,
        "target_langs": [l.strip() for l in target_langs.split(",")],
        "burn_subtitles": burn_subtitles,
        "subtitle_format": subtitle_format,
        "remove_silence": remove_silence,
        "parallel": parallel,
        "hf_token": os.getenv("HF_TOKEN")  # 從環境變數取得
    }
    
    # 9. 提交任務到 Celery
    try:
        process_video_task.apply_async(args=[file_path, options], task_id=task_id)
    except Exception as e:
        # 任務提交失敗，清理上傳的檔案
        try:
            os.remove(file_path)
        except:
            pass
        raise HTTPException(status_code=500, detail=f"Failed to enqueue task: {str(e)}")
    
    return TaskStatus(task_id=task_id, status="PENDING", progress=0)

@app.get("/status/{task_id}", response_model=TaskStatus)
async def get_status(task_id: str):
    task_id = validate_task_id(task_id)
    task_result = AsyncResult(task_id, app=celery_app)
    
    status = task_result.status
    progress = 0
    message = ""
    result_url = None
    warnings = []
    
    # B) 統一 Celery 狀態判斷邏輯
    if status == "PROGRESS":
        info = task_result.info or {}
        progress = info.get("progress", 0)
        message = info.get("status", "")
        if "warnings" in info:
            warnings.extend(info["warnings"])
        status = "PROCESSING"
    elif status == "SUCCESS":
        progress = 100
        message = "Completed"
        result_url = f"/results/{task_id}"
        if isinstance(task_result.result, dict):
            warnings.extend(task_result.result.get("warnings", []))
    elif status == "FAILURE":
        message = str(task_result.result)
    elif status == "PENDING":
        message = "Waiting for worker..."
        
    return TaskStatus(task_id=task_id, status=status, progress=progress, message=message, result_url=result_url, warnings=warnings)

@app.get("/results/{task_id}", response_model=TaskResultManifest)
async def get_results_manifest(task_id: str):
    task_id = validate_task_id(task_id)
    task_result = AsyncResult(task_id, app=celery_app)
    warnings = []
    if task_result.status == "SUCCESS" and isinstance(task_result.result, dict):
        warnings = task_result.result.get("warnings", [])

    final_video_path = os.path.join(UPLOAD_DIR, f"{task_id}_final.mp4")
    final_video_path = validate_path_traversal(final_video_path, UPLOAD_DIR)  # 取得安全路徑
    
    has_video = os.path.exists(final_video_path)
    
    files = [f for f in os.listdir(UPLOAD_DIR) if f.startswith(f"{task_id}_")]
    
    lang_map = {}
    for f in files:
        if f.endswith((".ass", ".srt")):
            # P1.5: 改用 rsplit(".", 1) 更穩定地解析副檔名，避免檔名有多個點時出錯
            parts = f.replace(f"{task_id}_", "", 1).rsplit(".", 1)
            if len(parts) != 2:
                continue
            lang_suffix = parts[0]
            ext = parts[1]
            if lang_suffix not in lang_map:
                lang_map[lang_suffix] = {"ass": False, "srt": False}
            if ext in ("ass", "srt"):
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
async def download_result(
    task_id: str,
    lang: Optional[str] = Query(None, description="Language for subtitle (e.g. Traditional_Chinese)"),
    format: Optional[str] = Query(None, description="Subtitle format: 'ass' or 'srt'. Only used when lang is specified")
):
    """
    下載結果。
    
    若不指定 lang：下載最終燒錄影片
    若指定 lang：下載字幕
    若指定 format：下載指定格式，否則優先 ass > srt
    """
    task_id = validate_task_id(task_id)
    
    # 驗證 format（如果指定）
    if format and format not in ("ass", "srt"):
        raise HTTPException(status_code=400, detail="format must be 'ass' or 'srt'")
    
    # 無 lang 時下載影片
    if not lang:
        final_video = os.path.join(UPLOAD_DIR, f"{task_id}_final.mp4")
        final_video = validate_path_traversal(final_video, UPLOAD_DIR)
        
        if os.path.exists(final_video):
            return FileResponse(final_video, filename=f"video_{task_id}.mp4")
        
        raise HTTPException(status_code=404, detail="Final video not found. Task may still be processing.")
    
    # 指定 lang 時下載字幕
    lang = validate_lang(lang)
    lang_suffix = lang.replace(" ", "_")
    
    # 決定要檢查的格式順序
    if format:
        formats_to_try = [format]
    else:
        formats_to_try = ["ass", "srt"]
    
    for ext in formats_to_try:
        target_file = os.path.join(UPLOAD_DIR, f"{task_id}_{lang_suffix}.{ext}")
        target_file = validate_path_traversal(target_file, UPLOAD_DIR)
        
        if os.path.exists(target_file):
            return FileResponse(target_file, filename=f"subtitle_{task_id}_{lang_suffix}.{ext}")
    
    # 都找不到
    if format:
        raise HTTPException(status_code=404, detail=f"Subtitle '{format}' for language '{lang}' not found")
    else:
        raise HTTPException(status_code=404, detail=f"Subtitle for language '{lang}' not found")

@app.websocket("/ws/status/{task_id}")
async def websocket_status(websocket: WebSocket, task_id: str):
    try:
        task_id = validate_task_id(task_id)
    except HTTPException:
        await websocket.close(code=4000, reason="Invalid task_id")
        return
    
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

@app.get("/subtitle/{task_id}")
async def get_subtitle(
    task_id: str,
    lang: str = Query(..., description="Language for subtitle"),
    format: Optional[str] = Query(None, description="Subtitle format: 'ass' or 'srt'. If not specified, tries ass first, then srt")
):
    """
    獲取字幕檔案內容。
    
    若指定 format，則只嘗試該格式。
    若不指定，則優先使用 ass，否則使用 srt。
    """
    task_id = validate_task_id(task_id)
    lang = validate_lang(lang)
    
    # 驗證 format（如果指定）
    if format and format not in ("ass", "srt"):
        raise HTTPException(status_code=400, detail="format must be 'ass' or 'srt'")
    
    lang_suffix = lang.replace(" ", "_")
    
    # 決定要檢查的格式順序
    if format:
        formats_to_try = [format]  # 只試指定格式
    else:
        formats_to_try = ["ass", "srt"]  # 優先 ass
    
    for ext in formats_to_try:
        filename = f"{task_id}_{lang_suffix}.{ext}"
        path = os.path.join(UPLOAD_DIR, filename)
        path = validate_path_traversal(path, UPLOAD_DIR)
        
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return {"content": f.read(), "format": ext, "filename": filename}
    
    # 都找不到
    if format:
        raise HTTPException(status_code=404, detail=f"Subtitle '{format}' for language '{lang}' not found")
    else:
        raise HTTPException(status_code=404, detail=f"Subtitle for language '{lang}' not found")

@app.put("/subtitle/{task_id}")
async def update_subtitle(
    task_id: str, 
    edit: SubtitleEditRequest, 
    lang: str = Query(..., description="Language for subtitle")
):
    """
    編輯字幕檔案。需要明確指定要編輯的格式（ass 或 srt）。
    只會更新指定格式的檔案，不會污染其他格式。
    
    P0.2: 責任澄清 - 本端點只負責更新字幕檔案。
    - 編輯後字幕檔案被更新
    - 若 final.mp4 存在，可選擇刪除以避免包含舊字幕
    - 若要使用新字幕，應創建新的 burn endpoint 或重新執行任務
    - 不會自動重建影片，那是下載的責任
    """
    task_id = validate_task_id(task_id)
    lang = validate_lang(lang)
    target_format = edit.format.lower()
    
    if target_format not in ("ass", "srt"):
        raise HTTPException(status_code=400, detail="Format must be 'ass' or 'srt'")
    
    lang_suffix = lang.replace(" ", "_")
    filepath = os.path.join(UPLOAD_DIR, f"{task_id}_{lang_suffix}.{target_format}")
    filepath = validate_path_traversal(filepath, UPLOAD_DIR)
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail=f"Subtitle '{target_format}' for language '{lang}' not found")
    
    try:
        # 只更新指定格式的檔案
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(edit.content)
        
        # 編輯後刪除 final video 來避免包含舊字幕的誤用
        # 若要新影片，應重新執行任務或未來新增明確的 rebuild endpoint
        final_video_path = os.path.join(UPLOAD_DIR, f"{task_id}_final.mp4")
        final_video_path = validate_path_traversal(final_video_path, UPLOAD_DIR)
        
        result = {
            "status": "updated",
            "format": target_format,
            "language": lang,
            "message": f"Successfully updated {target_format.upper()} subtitle for {lang}."
        }
        
        if os.path.exists(final_video_path):
            try:
                os.remove(final_video_path)
                result["warning"] = "Final video was deleted to prevent using old subtitles. To apply subtitles to video, create a new task or use a dedicated burn endpoint."
            except Exception as e:
                result["warning"] = f"Subtitle updated but final video could not be deleted: {str(e)}"
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update subtitle: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
