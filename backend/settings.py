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
