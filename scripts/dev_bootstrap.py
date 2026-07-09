#!/usr/bin/env python3
"""
Development environment bootstrap script.
Ensures local prerequisites are installed before starting development.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from runtime_requirements import (
    NODE_REQUIREMENT_TEXT,
    PYTHON_REQUIREMENT_TEXT,
    is_supported_node_version,
    is_supported_python_version,
    node_version_error_message,
    python_version_error_message,
)


ROOT_DIR = Path(__file__).parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"
VENV_DIR = ROOT_DIR / ".venv"
ENV_FILE = BACKEND_DIR / ".env"
ENV_EXAMPLE = BACKEND_DIR / ".env.example"
FRONTEND_ENV_FILE = FRONTEND_DIR / ".env"
FRONTEND_ENV_EXAMPLE = FRONTEND_DIR / ".env.example"
LOCAL_BACKEND_URL = "http://127.0.0.1:8891"
LOCAL_CORS_ORIGINS = (
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://localhost:3000",
)


def info(msg: str) -> None:
    print(f"[INFO] {msg}", flush=True)


def success(msg: str) -> None:
    print(f"[OK] {msg}", flush=True)


def warn(msg: str) -> None:
    print(f"[WARN] {msg}", flush=True)


def error(msg: str) -> None:
    print(f"[ERROR] {msg}", flush=True, file=sys.stderr)


def check_python_version() -> None:
    info("Checking Python version...")
    current_version = (sys.version_info.major, sys.version_info.minor, sys.version_info.micro)
    if not is_supported_python_version(current_version):
        error(python_version_error_message(current_version))
        sys.exit(1)
    success(f"Python {current_version[0]}.{current_version[1]}.{current_version[2]}")
    info(PYTHON_REQUIREMENT_TEXT)


def create_venv() -> None:
    info("Checking virtual environment...")
    if VENV_DIR.exists():
        py_exe = Path(get_python_exe())
        if py_exe.exists():
            result = subprocess.run(
                [
                    str(py_exe),
                    "-c",
                    "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')",
                ],
                cwd=ROOT_DIR,
                capture_output=True,
                text=True,
            )
            version_text = result.stdout.strip()
            if result.returncode == 0:
                parts = tuple(int(part) for part in version_text.split(".")[:3])
                if is_supported_python_version(parts):
                    success(f"Virtual environment already exists: {VENV_DIR}")
                    return
                warn(f"Existing virtual environment uses unsupported Python {version_text}; recreating .venv")
        else:
            warn("Existing virtual environment is missing its Python executable; recreating .venv")
        shutil.rmtree(VENV_DIR)

    info(f"Creating virtual environment at {VENV_DIR}...")
    subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True, cwd=ROOT_DIR)
    success("Virtual environment created")


def get_python_exe() -> str:
    if os.name == "nt":
        return str(VENV_DIR / "Scripts" / "python.exe")
    return str(VENV_DIR / "bin" / "python")


def install_backend_deps() -> bool:
    info("Installing backend dependencies...")
    py_exe = get_python_exe()
    requirements_file = ROOT_DIR / "requirements.lock.txt"

    if not Path(py_exe).exists():
        error(f"Python executable not found in virtual environment: {py_exe}")
        return False
    if not requirements_file.exists():
        error(f"requirements.lock.txt not found at {requirements_file}")
        return False

    result = subprocess.run(
        [py_exe, "-m", "pip", "install", "-q", "-r", str(requirements_file)],
        cwd=ROOT_DIR,
    )
    if result.returncode != 0:
        error("Backend dependencies installation failed")
        return False

    success("Backend dependencies installed")
    return True


def check_node_npm() -> bool:
    info("Checking Node.js and npm...")
    npm_path = shutil.which("npm")
    node_path = shutil.which("node")

    if not npm_path or not node_path:
        error("Node.js and npm are required. Install Node.js 20.x before continuing.")
        return False

    result = subprocess.run([node_path, "--version"], capture_output=True, text=True)
    version_text = result.stdout.strip()
    if result.returncode != 0 or not is_supported_node_version(version_text):
        error(node_version_error_message(version_text))
        return False

    success(f"npm found: {npm_path}")
    success(f"node found: {node_path}")
    success(f"Node.js {version_text}")
    info(NODE_REQUIREMENT_TEXT)
    return True


def install_frontend_deps() -> bool:
    info("Installing frontend dependencies...")
    node_modules = FRONTEND_DIR / "node_modules"
    if node_modules.exists():
        success("Frontend dependencies already installed")
        return True

    npm_exe = shutil.which("npm.cmd") or shutil.which("npm") or "npm"
    result = subprocess.run([npm_exe, "ci"], cwd=FRONTEND_DIR)
    if result.returncode != 0:
        error("Frontend dependencies installation failed")
        return False

    success("Frontend dependencies installed")
    return True


def create_env_file() -> bool:
    info("Checking environment configuration...")
    if ENV_FILE.exists():
        content = ENV_FILE.read_text(encoding="utf-8")
        updated = _ensure_backend_cors_origins(content)
        if updated != content:
            ENV_FILE.write_text(updated, encoding="utf-8")
            success(f"Updated {ENV_FILE} CORS_ORIGINS for local F5 frontend origins")
        else:
            success(f"Environment file exists: {ENV_FILE}")
        return True

    if not ENV_EXAMPLE.exists():
        error(f"Template file not found: {ENV_EXAMPLE}")
        return False

    info(f"Creating {ENV_FILE} from {ENV_EXAMPLE}...")
    content = ENV_EXAMPLE.read_text(encoding="utf-8")
    content = content.replace("UPLOAD_DIR=/app/uploads", "UPLOAD_DIR=backend/uploads")
    content = content.replace("OUTPUT_DIR=/app/outputs", "OUTPUT_DIR=backend/outputs")
    content = content.replace("TEMP_DIR=/app/tmp", "TEMP_DIR=backend/tmp")
    content = content.replace("REDIS_URL=redis://redis:6379/0", "REDIS_URL=redis://127.0.0.1:6379/0")
    content = content.replace("CELERY_BROKER_URL=redis://redis:6379/0", "CELERY_BROKER_URL=redis://127.0.0.1:6379/0")
    content = content.replace("CELERY_RESULT_BACKEND=redis://redis:6379/1", "CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/1")
    ENV_FILE.write_text(_ensure_backend_cors_origins(content), encoding="utf-8")
    success(f"Environment file created: {ENV_FILE}")
    return True


def _ensure_backend_cors_origins(content: str) -> str:
    lines = content.splitlines()
    found = False
    updated: list[str] = []
    for line in lines:
        if line.startswith("CORS_ORIGINS="):
            raw = line.split("=", 1)[1]
            origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
            for origin in LOCAL_CORS_ORIGINS:
                if origin not in origins:
                    origins.append(origin)
            updated.append(f"CORS_ORIGINS={','.join(origins)}")
            found = True
        else:
            updated.append(line)
    if not found:
        updated.insert(0, f"CORS_ORIGINS={','.join(LOCAL_CORS_ORIGINS)}")
    return "\n".join(updated).rstrip() + "\n"


def _ensure_frontend_api_base(content: str) -> str:
    lines = content.splitlines()
    found = False
    updated: list[str] = []
    for line in lines:
        if line.startswith("VITE_API_BASE_URL="):
            updated.append(f"VITE_API_BASE_URL={LOCAL_BACKEND_URL}")
            found = True
        else:
            updated.append(line)
    if not found:
        updated.insert(0, f"VITE_API_BASE_URL={LOCAL_BACKEND_URL}")
    return "\n".join(updated).rstrip() + "\n"


def create_frontend_env_file() -> bool:
    info("Checking frontend environment configuration...")
    if FRONTEND_ENV_FILE.exists():
        content = FRONTEND_ENV_FILE.read_text(encoding="utf-8")
        updated = _ensure_frontend_api_base(content)
        if updated != content:
            FRONTEND_ENV_FILE.write_text(updated, encoding="utf-8")
            success(f"Updated {FRONTEND_ENV_FILE} for local backend {LOCAL_BACKEND_URL}")
        else:
            success(f"Frontend environment file exists: {FRONTEND_ENV_FILE}")
        return True

    if FRONTEND_ENV_EXAMPLE.exists():
        content = FRONTEND_ENV_EXAMPLE.read_text(encoding="utf-8")
    else:
        warn(f"Template file not found: {FRONTEND_ENV_EXAMPLE}; creating a minimal frontend .env")
        content = ""

    FRONTEND_ENV_FILE.write_text(_ensure_frontend_api_base(content), encoding="utf-8")
    success(f"Frontend environment file created: {FRONTEND_ENV_FILE}")
    return True


def check_ffmpeg() -> bool:
    info("Checking FFmpeg...")
    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")

    if ffmpeg_path and ffprobe_path:
        success(f"ffmpeg found: {ffmpeg_path}")
        success(f"ffprobe found: {ffprobe_path}")
        return True

    warn("FFmpeg or ffprobe not found in PATH")
    if os.name == "nt":
        warn("To install on Windows, use: choco install ffmpeg")
    elif sys.platform == "darwin":
        warn("To install on macOS, use: brew install ffmpeg")
    else:
        warn("To install on Linux, use: sudo apt-get install ffmpeg")
    warn("Development will proceed, but video processing may fail without FFmpeg")
    return False


def check_redis() -> bool:
    info("Checking Redis...")
    redis_path = shutil.which("redis-server")
    if redis_path:
        success(f"Redis found locally: {redis_path}")
        return True

    docker_path = shutil.which("docker")
    if docker_path:
        warn("Redis not found locally, but Docker is available")
        warn("You can start Redis with: docker run -d -p 6379:6379 redis:7-alpine")
        return True

    warn("Redis not found. Development will fail without it.")
    warn("Options:")
    warn("  1. Install Redis from https://redis.io/download")
    warn("  2. Install Docker and use: docker run -d -p 6379:6379 redis:7-alpine")
    return False


def check_translation_provider() -> bool:
    info("Checking translation provider configuration...")
    if not ENV_FILE.exists():
        warn("Environment file not created yet, skipping translation provider check")
        return True

    env_content = ENV_FILE.read_text(encoding="utf-8")
    llm_provider = "openai"
    openai_key = ""
    ollama_base_url = ""
    ollama_model = ""
    for line in env_content.splitlines():
        if line.startswith("LLM_PROVIDER="):
            llm_provider = line.split("=", 1)[1].strip() or "openai"
        elif line.startswith("OPENAI_API_KEY="):
            openai_key = line.split("=", 1)[1].strip()
        elif line.startswith("OLLAMA_BASE_URL="):
            ollama_base_url = line.split("=", 1)[1].strip()
        elif line.startswith("OLLAMA_MODEL="):
            ollama_model = line.split("=", 1)[1].strip()

    if llm_provider == "ollama":
        if ollama_base_url and ollama_model:
            success(f"Ollama is configured ({ollama_model} @ {ollama_base_url})")
        else:
            warn("LLM_PROVIDER=ollama but OLLAMA_BASE_URL or OLLAMA_MODEL is missing")
        return True

    if llm_provider == "none":
        warn("LLM_PROVIDER=none - translation is intentionally disabled")
        return True

    if openai_key and not openai_key.startswith("#"):
        success("OpenAI API Key is configured")
        return True

    warn("OpenAI API Key not configured")
    warn("OpenAI translation will not work without it")
    warn("Set OPENAI_API_KEY in backend/.env or switch LLM_PROVIDER to ollama")
    return True


def compile_check() -> bool:
    info("Checking Python syntax...")
    py_exe = get_python_exe()
    result = subprocess.run([py_exe, "-m", "compileall", "-q", "backend", "scripts"], cwd=ROOT_DIR)
    if result.returncode != 0:
        error("Python syntax check failed")
        return False

    success("Python syntax check passed")
    return True


def print_summary(all_ok: bool) -> None:
    print()
    print("=" * 60)
    print("Bootstrap Summary")
    print("=" * 60)
    print()
    print(f"Python version: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    print(f"Python support: {PYTHON_REQUIREMENT_TEXT}")
    print(f"Virtual environment: {'ready' if VENV_DIR.exists() else 'missing'} ({VENV_DIR})")
    print(f"Backend dependencies: {'ready' if all_ok else 'check errors above'}")
    print(f"Frontend dependencies: {'ready' if (FRONTEND_DIR / 'node_modules').exists() else 'missing'}")
    print(f"Environment file (.env): {'ready' if ENV_FILE.exists() else 'missing'}")
    print(f"Frontend environment file: {'ready' if FRONTEND_ENV_FILE.exists() else 'missing'}")
    print(
        "FFmpeg: "
        + ("ready" if shutil.which("ffmpeg") and shutil.which("ffprobe") else "missing (required for video processing)")
    )
    print(
        "Redis: "
        + ("ready" if shutil.which("redis-server") else "not detected locally (Docker or external Redis also works)")
    )
    print(
        "OpenAI Key: "
        + ("configured" if os.environ.get("OPENAI_API_KEY") else "not detected in shell env (only required for LLM_PROVIDER=openai)")
    )
    print()


def main() -> None:
    print("=" * 60)
    print("AI Subtitle Tool - Development Bootstrap")
    print("=" * 60)
    print()

    all_ok = True

    check_python_version()

    try:
        create_venv()
    except Exception as exc:
        error(f"Virtual environment setup failed: {exc}")
        sys.exit(1)

    if not install_backend_deps():
        all_ok = False
    if not check_node_npm():
        all_ok = False
    if not install_frontend_deps():
        all_ok = False
    if not create_env_file():
        all_ok = False
    if not create_frontend_env_file():
        all_ok = False

    try:
        check_ffmpeg()
    except Exception as exc:
        warn(f"FFmpeg check failed: {exc}")

    try:
        check_redis()
    except Exception as exc:
        warn(f"Redis check failed: {exc}")

    try:
        check_translation_provider()
    except Exception as exc:
        warn(f"OpenAI API key check failed: {exc}")

    try:
        if not compile_check():
            all_ok = False
    except Exception as exc:
        warn(f"Compile check failed: {exc}")
        all_ok = False

    print_summary(all_ok)

    if not all_ok:
        error("Bootstrap completed with errors. Please check the output above.")
        sys.exit(1)

    success("Bootstrap completed successfully!")
    print()
    print("Next steps:")
    print("1. Press F5 in VS Code to start the full development stack")
    print("   OR run: python scripts/dev_start.py")
    print("2. Frontend: http://127.0.0.1:5173")
    print("3. Backend API: http://127.0.0.1:8891")
    print("4. API docs: http://127.0.0.1:8891/docs")
    print()


if __name__ == "__main__":
    main()
