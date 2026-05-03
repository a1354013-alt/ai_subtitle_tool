from __future__ import annotations

import sys
import zipfile
from pathlib import Path

from make_release_zip import build_release_zip


FORBIDDEN_PREFIXES = (
    "frontend/.npm-cache/",
    "frontend/dist/",
    "node_modules/",
    "uploads/",
    "backend/uploads/",
    "uploads/test1.mp4",
    "uploads/test2.mp4",
    "uploads/batches/",
    ".git/",
    "__pycache__/",
    ".pytest_cache/",
    ".mypy_cache/",
    ".env",
    ".env.local",
)

FORBIDDEN_SUFFIXES = (
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".webm",
    ".srt",
    ".vtt",
    ".ass",
    ".log",
)

REQUIRED_FILES = (
    "README.md",
    "backend/main.py",
    "frontend/package.json",
    "docker-compose.yml",
)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    out_path = repo_root / "release.zip"

    build_release_zip(repo_root, out_path)

    with zipfile.ZipFile(out_path, "r") as zf:
        names = zf.namelist()

    for name in names:
        normalized = name.lstrip("./")
        if any(normalized == prefix.rstrip("/") or normalized.startswith(prefix) for prefix in FORBIDDEN_PREFIXES):
            raise SystemExit(f"forbidden path found in release zip: {normalized}")
        if normalized.endswith(FORBIDDEN_SUFFIXES):
            raise SystemExit(f"forbidden file type found in release zip: {normalized}")

    for required in REQUIRED_FILES:
        if required not in names:
            raise SystemExit(f"required file missing from release zip: {required}")

    print(out_path)
    print("delivery verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
