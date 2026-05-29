from __future__ import annotations

import argparse
import fnmatch
import os
import sys
import zipfile
from pathlib import Path


EXCLUDED_DIR_NAMES = frozenset({
    ".git",
    ".github",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".vite",
    ".npm-cache",
    ".cache",
    "uploads",
    "outputs",
    "temp",
    "tmp",
    "segments",
    "release_out",
    "release_pkg",
    ".release_staging",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "htmlcov",
    ".venv",
    "venv",
    "env",
})

EXCLUDED_RELATIVE_PATHS = frozenset({
    "backend/uploads",
    "backend/outputs",
    "backend/tmp",
    "frontend/node_modules",
    "frontend/dist",
})

EXCLUDED_GLOBS = frozenset({
    "*.pyc",
    "*.pyo",
    "*.pyd",
    "*.zip",
    "*.tar.gz",
    "*.tar.bz2",
    "*.log",
    "*.tmp",
    "*.key",
    "*.pem",
    "secrets.*",
})

SENSITIVE_ENV_PATHS = frozenset({
    ".env",
    ".env.local",
    "backend/.env",
    "frontend/.env",
})


def _is_env_file(rel_posix: str) -> bool:
    if rel_posix in SENSITIVE_ENV_PATHS:
        return True
    path = Path(rel_posix)
    if path.name == ".env.example":
        return False
    return path.name == ".env" or path.name == ".env.local" or path.name.startswith(".env.")


def _is_excluded(rel_posix: str) -> bool:
    parts = rel_posix.split("/")
    for idx in range(len(parts)):
        sub_path = "/".join(parts[: idx + 1])
        if sub_path in EXCLUDED_RELATIVE_PATHS:
            return True
        if parts[idx] in EXCLUDED_DIR_NAMES:
            return True

    filename = parts[-1]
    return any(fnmatch.fnmatch(filename, pattern) for pattern in EXCLUDED_GLOBS)


def build_release_zip(repo_root: Path, out_path: Path) -> None:
    repo_root = repo_root.resolve()
    out_path = out_path.resolve()
    try:
        out_rel = out_path.relative_to(repo_root).as_posix()
    except ValueError:
        out_rel = None

    if out_path.exists():
        out_path.unlink()

    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        # Use os.walk instead of rglob to prune directories before descending
        for dirpath, dirnames, filenames in os.walk(repo_root):
            # Prune excluded directories in-place to prevent descending into them
            dirnames[:] = [
                d for d in dirnames
                if d not in EXCLUDED_DIR_NAMES
            ]
            
            for filename in filenames:
                abs_path = Path(dirpath) / filename
                rel_path = abs_path.relative_to(repo_root)
                rel_posix = rel_path.as_posix()

                if out_rel is not None and rel_posix == out_rel:
                    continue
                if _is_env_file(rel_posix):
                    continue
                if _is_excluded(rel_posix):
                    continue

                archive.write(abs_path, rel_posix)


def _assert_release_zip_clean(out_path: Path) -> None:
    with zipfile.ZipFile(out_path, "r") as archive:
        names = archive.namelist()

    required = {
        "README.md",
        "DEPLOYMENT.md",
        "docker-compose.yml",
        "backend/.env.example",
        "frontend/.env.example",
        "backend/Dockerfile",
        "frontend/Dockerfile",
        "frontend/package.json",
        "requirements.txt",
        "tests/test_api_contracts.py",
    }

    for name in names:
        normalized = name.lstrip("./")
        if _is_env_file(normalized) or _is_excluded(normalized):
            raise SystemExit(f"release zip contains forbidden content: {normalized}")

    missing = sorted(required - set(names))
    if missing:
        raise SystemExit(f"release zip is missing required files: {', '.join(missing)}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Build a clean, reproducible release zip for ai_subtitle_tool.")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]), help="Repository root path")
    parser.add_argument("--out", default="release.zip", help="Output zip path (relative to repo root unless absolute)")
    parser.add_argument("--check", action="store_true", help="Fail if the produced zip contains forbidden paths/files")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    out_path = (repo_root / args.out).resolve()

    build_release_zip(repo_root, out_path)
    if args.check:
        _assert_release_zip_clean(out_path)

    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
