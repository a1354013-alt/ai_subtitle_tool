from __future__ import annotations

import argparse
import fnmatch
import os
import sys
import zipfile
from pathlib import Path


EXCLUDED_DIR_NAMES = {
    ".git",
    "__pycache__",
    "node_modules",
    "dist",
    ".vite",
    ".npm-cache",
    ".cache",
    "uploads",
    "segments",
    "release_out",
    "release_pkg",
    ".release_staging",
    "tmp",
    "temp",
    "data_tmp",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".coverage",
    "htmlcov",
}

EXCLUDED_GLOBS = {
    "*.pyc",
    "*.pyo",
    "*.pyd",
    "*.zip",
    "*.tar.gz",
    "*.tar.bz2",
    "*.log",
    ".coverage",
    "coverage.xml",
}


def _is_env_file(p: Path) -> bool:
    name = p.name
    if name == ".env":
        return True
    if name.startswith(".env.") and name != ".env.example":
        return True
    if name.endswith(".env") and name != ".env.example":
        return True
    return False


def _is_excluded(rel_posix: str) -> bool:
    parts = rel_posix.split("/")
    if any(part in EXCLUDED_DIR_NAMES for part in parts[:-1]):
        return True

    filename = parts[-1]
    for pat in EXCLUDED_GLOBS:
        if fnmatch.fnmatch(filename, pat):
            return True
    return False


def build_release_zip(repo_root: Path, out_path: Path) -> None:
    repo_root = repo_root.resolve()
    out_path = out_path.resolve()

    if out_path.exists():
        out_path.unlink()

    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for abs_path in sorted(repo_root.rglob("*")):
            if abs_path.is_dir():
                continue

            rel_path = abs_path.relative_to(repo_root)
            rel_posix = rel_path.as_posix()

            if rel_posix == out_path.relative_to(repo_root).as_posix():
                continue

            if _is_env_file(abs_path):
                continue

            if _is_excluded(rel_posix):
                continue

            zf.write(abs_path, rel_posix)


def _assert_release_zip_clean(out_path: Path) -> None:
    with zipfile.ZipFile(out_path, "r") as zf:
        names = zf.namelist()

    forbidden_dir_names = {
        ".git",
        "__pycache__",
        "node_modules",
        "dist",
        ".vite",
        ".npm-cache",
        ".cache",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "uploads",
        "segments",
        "release_out",
        "release_pkg",
        ".release_staging",
        "htmlcov",
    }
    forbidden_file_names = {
        ".env",
        ".coverage",
    }
    forbidden_suffixes = {
        ".pyc",
        ".pyo",
        ".pyd",
        ".log",
        ".zip",
        ".tar.gz",
        ".tar.bz2",
        ".tmp",
    }

    for name in names:
        p = Path(name)
        parts = [part for part in p.parts if part not in (".", "")]

        if not parts:
            continue

        # Forbidden directories (any depth)
        if any(part in forbidden_dir_names for part in parts[:-1]):
            raise SystemExit(f"release zip contains forbidden path: {name}")

        # Forbidden files (any depth)
        if parts[-1] in forbidden_file_names:
            raise SystemExit(f"release zip contains forbidden file: {name}")

        # Env files (except .env.example)
        if parts[-1] == ".env.example":
            pass
        elif parts[-1] == ".env" or parts[-1].startswith(".env.") or parts[-1].endswith(".env"):
            raise SystemExit(f"release zip contains forbidden env file: {name}")

        # Forbidden suffix patterns
        if any(str(p).endswith(suf) for suf in forbidden_suffixes):
            raise SystemExit(f"release zip contains forbidden file type: {name}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Build a clean, reproducible release zip for ai_subtitle_tool.")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]), help="Repository root path")
    parser.add_argument("--out", default="release.zip", help="Output zip path (relative to repo root)")
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
