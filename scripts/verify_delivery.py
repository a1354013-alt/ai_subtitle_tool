from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from make_release_zip import build_release_zip
from verify_docker_config import verify as verify_docker_config


REQUIRED_FILES = {
    ".gitattributes",
    "README.md",
    "DEPLOYMENT.md",
    "docker-compose.yml",
    "backend/.env.example",
    "backend/Dockerfile",
    "frontend/.env.example",
    "frontend/Dockerfile",
    "frontend/package.json",
    "requirements.txt",
    "scripts/verify_docker_config.py",
}

REQUIRED_ENV_REFERENCES = {
    "README.md": ["backend/.env.example", "frontend/.env.example"],
    "DEPLOYMENT.md": ["backend/.env.example"],
}

FORBIDDEN_DOC_PATH_MARKERS = (
    "C:/Users/",
    "/C:/Users/",
    "OneDrive/",
    "OneDrive\\",
)

FORBIDDEN_ZIP_MARKERS = (
    ".git/",
    ".github/",
    "node_modules/",
    "dist/",
    "build/",
    "__pycache__/",
    ".pytest_cache/",
    ".venv/",
    "venv/",
    ".env",
    ".env.local",
    "backend/.env",
    "frontend/.env",
    "uploads/",
    "outputs/",
    "temp/",
    "tmp/",
)


def _run_command(command: list[str], cwd: Path, *, label: str) -> None:
    resolved = list(command)
    if os.name == "nt" and resolved and resolved[0] == "npm":
        resolved[0] = shutil.which("npm.cmd") or shutil.which("npm") or "npm.cmd"

    print(f"[{label}] $ {' '.join(command)}", flush=True)
    completed = subprocess.run(resolved, cwd=cwd)
    if completed.returncode != 0:
        raise SystemExit(f"[{label}] command failed ({completed.returncode}): {' '.join(command)}")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _iter_markdown_docs(repo_root: Path) -> list[Path]:
    ignored_parts = {"node_modules", "dist", "build", ".git", "__pycache__"}
    return [
        path
        for path in sorted(repo_root.rglob("*.md"))
        if not ignored_parts.intersection(path.relative_to(repo_root).parts)
    ]


def _verify_required_files(repo_root: Path) -> None:
    missing = sorted(path for path in REQUIRED_FILES if not (repo_root / path).exists())
    if missing:
        raise SystemExit(f"required files missing: {', '.join(missing)}")


def _verify_docs(repo_root: Path) -> None:
    for relative_path, required_tokens in REQUIRED_ENV_REFERENCES.items():
        text = _read_text(repo_root / relative_path)
        missing = [token for token in required_tokens if token not in text]
        if missing:
            raise SystemExit(f"{relative_path} is missing required references: {', '.join(missing)}")

    for doc_path in _iter_markdown_docs(repo_root):
        relative_path = doc_path.relative_to(repo_root).as_posix()
        text = _read_text(doc_path)
        for marker in FORBIDDEN_DOC_PATH_MARKERS:
            if marker in text:
                raise SystemExit(f"{relative_path} contains local absolute path marker: {marker}")

    readme = _read_text(repo_root / "README.md")
    for section in (
        "## Project Overview",
        "## Features",
        "## Architecture",
        "## Quick Start: Docker Compose",
        "## Local Development: Backend",
        "## Local Development: Frontend",
        "## Testing",
        "## Release Packaging",
        "## Environment Variables",
        "## Known Limitations",
        "## Portfolio Highlights",
    ):
        if section not in readme:
            raise SystemExit(f"README.md missing required section: {section}")


def _verify_frontend_scripts(repo_root: Path) -> None:
    package_json = json.loads(_read_text(repo_root / "frontend" / "package.json"))
    scripts = package_json.get("scripts", {})
    for required_script in ("build", "typecheck", "test:ci"):
        if required_script not in scripts:
            raise SystemExit(f"frontend/package.json missing required script: {required_script}")


def _verify_gitattributes(repo_root: Path) -> None:
    attributes = _read_text(repo_root / ".gitattributes")
    for forbidden_rule in (".env.* export-ignore", "backend/.env.* export-ignore", "frontend/.env.* export-ignore"):
        if forbidden_rule in attributes:
            raise SystemExit(f".gitattributes must not broadly export-ignore env examples: {forbidden_rule}")
    for required_rule in ("backend/.env.example -export-ignore", "frontend/.env.example -export-ignore"):
        if required_rule not in attributes:
            raise SystemExit(f".gitattributes missing required rule: {required_rule}")


def _verify_docker_contract(repo_root: Path) -> None:
    compose_text = _read_text(repo_root / "docker-compose.yml")
    for token in ("services:", "backend:", "worker:", "frontend:", "backend/.env.example"):
        if token not in compose_text:
            raise SystemExit(f"docker-compose.yml missing required token: {token}")


def _verify_zip_contents(out_path: Path) -> None:
    with zipfile.ZipFile(out_path, "r") as archive:
        names = archive.namelist()

    for name in names:
        normalized = name.lstrip("./")
        if normalized.endswith((".key", ".pem")) or normalized.startswith("secrets."):
            raise SystemExit(f"sensitive file found in release zip: {normalized}")
        for marker in FORBIDDEN_ZIP_MARKERS:
            if normalized == marker or normalized.startswith(f"{marker}/"):
                raise SystemExit(f"forbidden content found in release zip: {normalized}")

    for required in REQUIRED_FILES:
        if required not in names:
            raise SystemExit(f"required file missing from release zip: {required}")


def run_zip_only(repo_root: Path) -> Path:
    _verify_required_files(repo_root)
    _verify_docs(repo_root)
    _verify_frontend_scripts(repo_root)
    _verify_gitattributes(repo_root)
    _verify_docker_contract(repo_root)
    verify_docker_config(repo_root)

    out_path = repo_root / "release.zip"
    build_release_zip(repo_root, out_path)
    _verify_zip_contents(out_path)
    print(str(out_path))
    print("delivery verification passed")
    return out_path


def run_full(repo_root: Path) -> None:
    run_zip_only(repo_root)
    _run_command(
        [
            sys.executable,
            "-m",
            "compileall",
            "-q",
            "backend",
            "tests",
            "scripts",
            "benchmarks",
            "test_hwaccel.py",
            "test_report.py",
        ],
        repo_root,
        label="python-compile",
    )
    _run_command([sys.executable, "-m", "pytest", "-q"], repo_root, label="pytest")
    frontend_dir = repo_root / "frontend"
    frontend_scripts = json.loads(_read_text(frontend_dir / "package.json")).get("scripts", {})
    if "lint" in frontend_scripts:
        _run_command(["npm", "run", "lint"], frontend_dir, label="frontend-lint")
    _run_command(["npm", "run", "typecheck"], frontend_dir, label="frontend-typecheck")
    _run_command(["npm", "run", "test:ci"], frontend_dir, label="frontend-test-ci")
    _run_command(["npm", "run", "build"], frontend_dir, label="frontend-build")
    _run_command(
        [sys.executable, "scripts/make_release_zip.py", "--out", "release.zip", "--check"],
        repo_root,
        label="release-zip-build-check",
    )
    _run_command(
        [sys.executable, "scripts/verify_release_zip.py", "release.zip"],
        repo_root,
        label="release-zip-verify",
    )
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
