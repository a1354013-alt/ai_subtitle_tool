from .error_messages import ERROR_MESSAGES

def handle_known_error(err: Exception) -> str:
    error_text = str(err).lower()

    if "ffmpeg" in error_text or "ffprobe" in error_text:
        return "ffmpeg_not_found"

    if ("openai" in error_text and "api key" in error_text) or "api_key" in error_text:
        return "openai_api_key_missing"

    if "redis" in error_text or "connection error" in error_text:
        return "redis_not_running"

    if "no audio" in error_text or "audio stream" in error_text:
        return "no_audio_stream"
        
    if "unsupported" in error_text and "format" in error_text:
        return "unsupported_file_format"

    if "whisper" in error_text:
        return "whisper_failed"

    return "unknown_error"

def get_error_response(error_code: str):
    info = ERROR_MESSAGES.get(error_code, ERROR_MESSAGES["unknown_error"])
    return {
        "error_code": error_code,
        "message": info["message"],
        "suggestion": info["suggestion"]
    }
