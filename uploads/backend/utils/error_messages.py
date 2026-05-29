ERROR_MESSAGES = {
    "ffmpeg_not_found": {
        "message": "找不到 ffmpeg，請確認已安裝 ffmpeg 並加入 PATH。",
        "suggestion": "請安裝 ffmpeg：https://ffmpeg.org/"
    },
    "openai_api_key_missing": {
        "message": "尚未設定 OpenAI API Key。",
        "suggestion": "請在 .env 設定 OPENAI_API_KEY。"
    },
    "redis_not_running": {
        "message": "Redis 尚未啟動。",
        "suggestion": "請先啟動 Redis 服務。"
    },
    "unsupported_file_format": {
        "message": "不支援的檔案格式。",
        "suggestion": "請上傳 mp4、mov、mkv 或 avi 檔案。"
    },
    "no_audio_stream": {
        "message": "影片沒有音軌，無法產生字幕。",
        "suggestion": "請確認影片包含音訊。"
    },
    "whisper_failed": {
        "message": "語音辨識失敗。",
        "suggestion": "請確認影片音訊正常，或重新上傳影片。"
    },
    "unknown_error": {
        "message": "發生未知錯誤。",
        "suggestion": "請檢查系統日誌或稍後再試。"
    }
}
