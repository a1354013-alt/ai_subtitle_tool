from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from typing import Optional

from make_release_zip import build_release_zip
from runtime_requirements import is_supported_python_version, python_version_error_message
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
    ".vscode/launch.json",
    ".vscode/tasks.json",
    ".vscode/extensions.json",
}

RELEASE_REQUIRED_FILES = REQUIRED_FILES - {
    ".vscode/launch.json",
    ".vscode/tasks.json",
    ".vscode/extensions.json",
}

FORBIDDEN_GITIGNORE_PATTERNS = (
    "```",
)

REQUIRED_GITIGNORE_PATTERNS = (
    "!.vscode/launch.json",
    "!.vscode/tasks.json",
    "!.vscode/extensions.json",
)

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
    ".vscode/",
    "scripts/dev_bootstrap.py",
    "scripts/dev_start.py",
    "scripts/start-dev.cmd",
    "scripts/start-dev.ps1",
    "scripts/stop-dev.ps1",
)

EXIT_PYTHON_VERSION_ERROR = 20
EXIT_BACKEND_DEPENDENCY_ERROR = 21

BACKEND_DEPENDENCY_MODULES = (
    ("celery", "celery"),
    ("pytest", "pytest"),
    ("pytest-timeout", "pytest_timeout"),
)


class VerificationError(RuntimeError):
    def __init__(self, message: str, *, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def _run_command(
    command: list[str],
    cwd: Path,
    *,
    label: str,
    timeout_seconds: Optional[int] = None
) -> None:
    resolved = list(command)
    if os.name == "nt" and resolved and resolved[0] == "npm":
        resolved[0] = shutil.which("npm.cmd") or shutil.which("npm") or "npm.cmd"

    start_time = time.time()
    print(f"[{label}] ({cwd}) $ {' '.join(command)}", flush=True)
    if timeout_seconds:
        print(f"[{label}] timeout: {timeout_seconds}s", flush=True)
    
    try:
        completed = subprocess.run(
            resolved,
            cwd=cwd,
            timeout=timeout_seconds
        )
        elapsed = time.time() - start_time
        if completed.returncode != 0:
            raise SystemExit(
                f"[{label}] command failed ({completed.returncode}) after {elapsed:.1f}s in {cwd}: {' '.join(command)}"
            )
        print(f"[{label}] passed in {elapsed:.1f}s", flush=True)
    except subprocess.TimeoutExpired as e:
        elapsed = time.time() - start_time
        raise SystemExit(
            f"[{label}] command timed out after {elapsed:.1f}s in {cwd}: {' '.join(command)}"
        )


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _ensure_supported_python_version(version_info: tuple[int, int, int] | None = None) -> None:
    current_version = version_info or (
        sys.version_info.major,
        sys.version_info.minor,
        sys.version_info.micro,
    )
    if not is_supported_python_version(current_version):
        raise VerificationError(
            f"[python-preflight] {python_version_error_message(current_version)}",
            exit_code=EXIT_PYTHON_VERSION_ERROR,
        )


def _find_missing_backend_dependencies() -> list[str]:
    missing: list[str] = []
    for package_name, module_name in BACKEND_DEPENDENCY_MODULES:
        if importlib.util.find_spec(module_name) is None:
            missing.append(package_name)
    return missing


def _verify_backend_dependency_preflight() -> None:
    missing = _find_missing_backend_dependencies()
    if missing:
        formatted = ", ".join(missing)
        raise VerificationError(
            "[backend-preflight] Missing backend dependencies: "
            f"{formatted}\n\n"
            "Please run:\n"
            "python -m pip install -r requirements.lock.txt",
            exit_code=EXIT_BACKEND_DEPENDENCY_ERROR,
        )


def _print_fast_mode_banner(*, ci_fast: bool, frontend_node_modules_exists: bool) -> None:
    if not ci_fast:
        return

    print("FAST MODE ENABLED:", flush=True)
    print("Some expensive checks may be skipped.", flush=True)
    print("This is not a full release verification.", flush=True)
    print("[fast-mode] Requested with --full and --ci-fast/--smoke.", flush=True)
    print("[fast-mode] Skipped checks:", flush=True)
    print("[fast-mode] - backend pytest", flush=True)
    print("[fast-mode] - frontend test:ci", flush=True)
    if frontend_node_modules_exists:
        print("[fast-mode] - frontend npm ci (existing node_modules detected)", flush=True)
    else:
        print("[fast-mode] - frontend npm ci will still run because node_modules is missing", flush=True)


def _iter_markdown_docs(repo_root: Path) -> list[Path]:
    ignored_parts = {"node_modules", "dist", "build", ".git", "__pycache__"}
    return [
        path
        for path in sorted(repo_root.rglob("*.md"))
        if not ignored_parts.intersection(path.relative_to(repo_root).parts)
    ]


def _verify_gitignore(repo_root: Path) -> None:
    """Verify .gitignore does not contain forbidden patterns and has required patterns."""
    gitignore_path = repo_root / ".gitignore"
    if not gitignore_path.exists():
        raise SystemExit(".gitignore file is missing")
    
    content = _read_text(gitignore_path)
    
    # Check for forbidden patterns (markdown code fences)
    for pattern in FORBIDDEN_GITIGNORE_PATTERNS:
        if pattern in content:
            raise SystemExit(f".gitignore contains forbidden pattern: {pattern}")
    
    # Check for required patterns
    for pattern in REQUIRED_GITIGNORE_PATTERNS:
        if pattern not in content:
            raise SystemExit(f".gitignore missing required pattern: {pattern}")
    
    # Verify .vscode/ is not broadly ignored without exceptions
    lines = content.splitlines()
    vscode_ignore_pattern = False
    for line in lines:
        stripped = line.strip()
        if stripped == ".vscode/*":
            vscode_ignore_pattern = True
        if stripped == ".vscode/":
            raise SystemExit("Do not ignore the entire .vscode/ directory. Use .vscode/* with explicit negations for workspace files.")
    
    if not vscode_ignore_pattern:
        raise SystemExit(".gitignore must ignore .vscode/* but allow specific files via negation patterns")


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
        "## Quick Start: One-Click Development (Recommended)",
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

    for required in RELEASE_REQUIRED_FILES:
        if required not in names:
            raise SystemExit(f"required file missing from release zip: {required}")


def run_zip_only(repo_root: Path) -> Path:
    _verify_gitignore(repo_root)
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


def run_full(repo_root: Path, *, ci_fast: bool = False) -> None:
    _ensure_supported_python_version()
    run_zip_only(repo_root)
    frontend_dir = repo_root / "frontend"
    _print_fast_mode_banner(
        ci_fast=ci_fast,
        frontend_node_modules_exists=(frontend_dir / "node_modules").exists(),
    )
    
    # Backend compilation
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
        timeout_seconds=60,
    )
    
    # Backend tests (skip in --ci-fast mode)
    if not ci_fast:
        _verify_backend_dependency_preflight()
        _run_command(
            [sys.executable, "-m", "pytest", "-q"],
            repo_root,
            label="pytest",
            timeout_seconds=300,
        )
    else:
        print("[pytest] skipped (--ci-fast mode)", flush=True)
    
    # Frontend checks
    frontend_scripts = json.loads(_read_text(frontend_dir / "package.json")).get("scripts", {})
    
    # npm ci (skip in --ci-fast mode if node_modules exists)
    if ci_fast and (frontend_dir / "node_modules").exists():
        print("[frontend-npm-ci] skipped (--ci-fast mode, node_modules exists)", flush=True)
    else:
        _run_command(
            ["npm", "ci"],
            frontend_dir,
            label="frontend-npm-ci",
            timeout_seconds=300,
        )
    
    # Lint (optional)
    if "lint" in frontend_scripts:
        _run_command(
            ["npm", "run", "lint"],
            frontend_dir,
            label="frontend-lint",
            timeout_seconds=120,
        )
    
    # Typecheck
    _run_command(
        ["npm", "run", "typecheck"],
        frontend_dir,
        label="frontend-typecheck",
        timeout_seconds=120,
    )
    
    # Frontend tests (skip in --ci-fast mode)
    if not ci_fast:
        _run_command(
            ["npm", "run", "test:ci"],
            frontend_dir,
            label="frontend-test-ci",
            timeout_seconds=180,
        )
    else:
        print("[frontend-test-ci] skipped (--ci-fast mode)", flush=True)
    
    # Frontend build
    _run_command(
        ["npm", "run", "build"],
        frontend_dir,
        label="frontend-build",
        timeout_seconds=180,
    )

    # Production dependency audit. Full audit may include tracked dev-only
    # Vite/Vitest/esbuild advisories and is not a release gate.
    _run_command(
        ["npm", "audit", "--omit=dev"],
        frontend_dir,
        label="frontend-production-audit",
        timeout_seconds=120,
    )
    
    # Release zip checks
    _run_command(
        [sys.executable, "scripts/make_release_zip.py", "--out", "release.zip", "--check"],
        repo_root,
        label="release-zip-build-check",
        timeout_seconds=120,
    )
    _run_command(
        [sys.executable, "scripts/verify_release_zip.py", "release.zip"],
        repo_root,
        label="release-zip-verify",
        timeout_seconds=60,
    )
    
    print("full delivery verification passed", flush=True)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Verify ai_subtitle_tool delivery artifacts and reproducibility.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--zip-only", action="store_true", help="Only build and validate the clean release zip.")
    mode.add_argument("--full", action="store_true", help="Run zip checks plus backend/frontend test and build commands.")
    parser.add_argument(
        "--ci-fast",
        "--smoke",
        dest="ci_fast",
        action="store_true",
        help="Fast CI mode: skip pytest, frontend tests, and npm ci (if node_modules exists). Alias: --smoke. Use with --full."
    )
    args = parser.parse_args(argv)
    if args.ci_fast and not args.full:
        parser.error("--ci-fast/--smoke can only be used with --full")

    repo_root = Path(__file__).resolve().parents[1]
    try:
        if args.full:
            run_full(repo_root, ci_fast=args.ci_fast)
        else:
            run_zip_only(repo_root)
        return 0
    except VerificationError as exc:
        print(str(exc), file=sys.stderr, flush=True)
        return exc.exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
