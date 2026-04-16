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
}

EXCLUDED_GLOBS = {
    "*.pyc",
    "*.pyo",
    "*.pyd",
    "*.zip",
    "*.tar.gz",
    "*.tar.bz2",
    "*.log",
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

    for name in names:
        # Forbidden files
        if name.endswith("/.env") or Path(name).name == ".env":
            raise SystemExit(f"release zip contains forbidden file: {name}")

        # Forbidden directories (any depth)
        parts = name.split("/")
        if "uploads" in parts or "segments" in parts or ".cache" in parts:
            raise SystemExit(f"release zip contains forbidden path: {name}")


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
