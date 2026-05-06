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


REQUIRED_FILES = {
    "README.md",
    "DEPLOYMENT.md",
    "docker-compose.yml",
    "backend/.env.example",
    "backend/Dockerfile",
    "frontend/.env.example",
    "frontend/Dockerfile",
    "frontend/package.json",
    "requirements.txt",
}

REQUIRED_ENV_REFERENCES = {
    "README.md": ["backend/.env.example", "frontend/.env.example"],
    "DEPLOYMENT.md": ["backend/.env.example"],
}

FORBIDDEN_ZIP_MARKERS = (
    ".git/",
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


def _run_command(command: list[str], cwd: Path) -> None:
    resolved = list(command)
    if os.name == "nt" and resolved and resolved[0] == "npm":
        resolved[0] = shutil.which("npm.cmd") or shutil.which("npm") or "npm.cmd"

    print(f"$ {' '.join(command)}")
    completed = subprocess.run(resolved, cwd=cwd)
    if completed.returncode != 0:
        raise SystemExit(f"command failed ({completed.returncode}): {' '.join(command)}")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


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
    for required_script in ("build", "typecheck", "test"):
        if required_script not in scripts:
            raise SystemExit(f"frontend/package.json missing required script: {required_script}")


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
    _verify_docker_contract(repo_root)

    out_path = repo_root / "release.zip"
    build_release_zip(repo_root, out_path)
    _verify_zip_contents(out_path)
    print(str(out_path))
    print("delivery verification passed")
    return out_path


def run_full(repo_root: Path) -> None:
    run_zip_only(repo_root)
    _run_command([sys.executable, "-m", "pytest", "-q"], repo_root)
    _run_command(["npm", "ci"], repo_root / "frontend")
    if "lint" in json.loads(_read_text(repo_root / "frontend" / "package.json")).get("scripts", {}):
        _run_command(["npm", "run", "lint"], repo_root / "frontend")
    _run_command(["npm", "run", "typecheck"], repo_root / "frontend")
    _run_command(["npm", "run", "test"], repo_root / "frontend")
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
