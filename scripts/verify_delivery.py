from __future__ import annotations

import argparse
import os
import shutil
import subprocess
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
    "DEPLOYMENT.md",
    "TEST_PLAN.md",
    "backend/main.py",
    "backend/.env.example",
    "frontend/.env.example",
    "frontend/package.json",
    "docker-compose.yml",
)


def _run_command(command: list[str], cwd: Path) -> None:
    resolved_command = list(command)
    if os.name == "nt" and command and command[0] == "npm":
        resolved_command[0] = shutil.which("npm.cmd") or shutil.which("npm") or "npm.cmd"

    print(f"$ {' '.join(command)}")
    completed = subprocess.run(resolved_command, cwd=cwd)
    if completed.returncode != 0:
        raise SystemExit(f"command failed ({completed.returncode}): {' '.join(command)}")


def _verify_repo_examples(repo_root: Path) -> None:
    missing = [path for path in REQUIRED_FILES if not (repo_root / path).exists()]
    if missing:
        raise SystemExit(f"required repo files missing: {', '.join(missing)}")


def _verify_zip_contents(out_path: Path) -> None:
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


def run_zip_only(repo_root: Path) -> Path:
    out_path = repo_root / "release.zip"
    _verify_repo_examples(repo_root)
    build_release_zip(repo_root, out_path)
    _verify_zip_contents(out_path)
    print(out_path)
    print("delivery verification passed")
    return out_path


def run_full(repo_root: Path) -> None:
    run_zip_only(repo_root)
    _run_command([sys.executable, "-m", "pytest", "-q"], repo_root)
    _run_command(["npm", "ci"], repo_root / "frontend")
    _run_command(["npm", "run", "typecheck"], repo_root / "frontend")
    _run_command(["npm", "run", "lint"], repo_root / "frontend")
    _run_command(["npm", "run", "test:ci"], repo_root / "frontend")
    _run_command(["npm", "run", "build"], repo_root / "frontend")
    print("full delivery verification passed")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Verify ai_subtitle_tool delivery artifacts and reproducibility.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--zip-only", action="store_true", help="Only build and validate the clean release zip.")
    mode.add_argument("--full", action="store_true", help="Run zip checks plus backend/frontend test and build commands.")
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]

    if args.full:
        run_full(repo_root)
    else:
        run_zip_only(repo_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
