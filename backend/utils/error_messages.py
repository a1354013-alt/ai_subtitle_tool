ERROR_MESSAGES = {
    "ffmpeg_not_found": {
        "message": "ffmpeg or ffprobe is not available.",
        "suggestion": "Install ffmpeg and ensure both binaries are available on PATH.",
    },
    "openai_api_key_missing": {
        "message": "OPENAI_API_KEY is missing.",
        "suggestion": "Set OPENAI_API_KEY before enabling translation features.",
    },
    "redis_not_running": {
        "message": "Redis is not reachable.",
        "suggestion": "Start Redis and confirm REDIS_URL, CELERY_BROKER_URL, and CELERY_RESULT_BACKEND are correct.",
    },
    "unsupported_file_format": {
        "message": "Unsupported file format.",
        "suggestion": "Upload one of the supported video formats: .mp4, .mkv, .avi, or .mov.",
    },
    "no_audio_stream": {
        "message": "The uploaded video does not contain an audio stream.",
        "suggestion": "Upload a source video with audio so transcription can run.",
    },
    "whisper_failed": {
        "message": "Speech transcription failed.",
        "suggestion": "Try a shorter or cleaner source file and confirm the Whisper model is available.",
    },
    "task_not_found": {
        "message": "Task not found.",
        "suggestion": "Check the task id or start a new upload if the original task was removed.",
    },
    "task_canceled": {
        "message": "Task canceled by user.",
        "suggestion": "Restart the task if you still need subtitle generation for this file.",
    },
    "unknown_error": {
        "message": "An unexpected error occurred.",
        "suggestion": "Review the backend logs for details and retry once the underlying issue is fixed.",
    },
}
