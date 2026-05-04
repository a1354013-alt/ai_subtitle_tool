import os


def _read_float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default

    try:
        value = float(raw)
    except ValueError:
        return default

    if value <= 0:
        return default
    return value


AUTO_SEGMENT_THRESHOLD_SECONDS = _read_float_env("AUTO_SEGMENT_THRESHOLD_SECONDS", 60.0)

# Translation Settings
TRANSLATE_PROVIDER = os.getenv("TRANSLATE_PROVIDER", "openai").lower()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")
TRANSLATE_MODEL = os.getenv("TRANSLATE_MODEL", "gpt-4o-mini")
