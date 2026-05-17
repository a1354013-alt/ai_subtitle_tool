from pathlib import Path

from fastapi import HTTPException


def validate_path_traversal(filepath: str, allowed_root: str) -> str:
    resolved_path = Path(filepath).resolve()
    resolved_root = Path(allowed_root).resolve()
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Path traversal detected: {filepath} is outside allowed directory.")
    return str(resolved_path)

