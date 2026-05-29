#!/usr/bin/env python3
"""
Development environment bootstrap script.
Ensures all dependencies and prerequisites are in place before starting development.
Windows-first, cross-platform implementation.
"""
import os
import subprocess
import sys
from pathlib import Path
import shutil
import platform

ROOT_DIR = Path(__file__).parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"
VENV_DIR = ROOT_DIR / ".venv"
ENV_FILE = BACKEND_DIR / ".env"
ENV_EXAMPLE = BACKEND_DIR / ".env.example"


def info(msg: str):
    print(f"[INFO] {msg}", flush=True)


def success(msg: str):
    print(f"[✓] {msg}", flush=True)


def warn(msg: str):
    print(f"[⚠] {msg}", flush=True)


def error(msg: str):
    print(f"[✗] {msg}", flush=True, file=sys.stderr)


def run_cmd(cmd: list[str], label: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run a command and return result. Optionally check result."""
    info(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=ROOT_DIR)
    if check and result.returncode != 0:
        error(f"{label} failed (exit code {result.returncode})")
        return result
    return result


def check_python_version():
    """Verify Python 3.11+."""
    info("Checking Python version...")
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 11):
        error(f"Python 3.11+ required, found {version.major}.{version.minor}")
        sys.exit(1)
    success(f"Python {version.major}.{version.minor}.{version.micro}")


def create_venv():
    """Create virtual environment if needed."""
    info("Checking virtual environment...")
    if VENV_DIR.exists():
        success(f"Virtual environment already exists: {VENV_DIR}")
        return
    
    info(f"Creating virtual environment at {VENV_DIR}...")
    subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)
    success("Virtual environment created")


def get_python_exe() -> str:
    """Get the Python executable path for the venv."""
    if os.name == "nt":  # Windows
        return str(VENV_DIR / "Scripts" / "python.exe")
    else:  # macOS/Linux
        return str(VENV_DIR / "bin" / "python")


def install_backend_deps():
    """Install backend dependencies."""
    info("Installing backend dependencies...")
    py_exe = get_python_exe()
    
    if not (VENV_DIR / ("Scripts" if os.name == "nt" else "bin") / ("pip" if os.name != "nt" else "pip.exe")).exists():
        error("Python executable not found in venv")
        sys.exit(1)
    
    requirements_file = ROOT_DIR / "requirements.txt"
    if not requirements_file.exists():
        error(f"requirements.txt not found at {requirements_file}")
        sys.exit(1)
    
    result = subprocess.run(
        [py_exe, "-m", "pip", "install", "-q", "-r", str(requirements_file)],
        cwd=ROOT_DIR
    )
    if result.returncode != 0:
        error("Backend dependencies installation failed")
        return False
    success("Backend dependencies installed")
    return True


def check_node_npm():
    """Verify Node.js and npm are installed."""
    info("Checking Node.js and npm...")
    
    npm_path = shutil.which("npm")
    if not npm_path:
        error("npm not found. Please install Node.js from https://nodejs.org/")
        return False
    
    node_path = shutil.which("node")
    if not node_path:
        error("node not found. Please install Node.js from https://nodejs.org/")
        return False
    
    success(f"npm found: {npm_path}")
    success(f"node found: {node_path}")
    return True


def install_frontend_deps():
    """Install frontend dependencies."""
    info("Installing frontend dependencies...")
    
    node_modules = FRONTEND_DIR / "node_modules"
    if node_modules.exists():
        success("Frontend dependencies already installed")
        return True
    
    result = subprocess.run(
        ["npm", "ci"],
        cwd=FRONTEND_DIR
    )
    if result.returncode != 0:
        error("Frontend dependencies installation failed")
        return False
    success("Frontend dependencies installed")
    return True


def create_env_file():
    """Create .env file from .env.example if needed."""
    info("Checking environment configuration...")
    
    if ENV_FILE.exists():
        success(f"Environment file exists: {ENV_FILE}")
        return True
    
    if not ENV_EXAMPLE.exists():
        error(f"Template file not found: {ENV_EXAMPLE}")
        return False
    
    info(f"Creating {ENV_FILE} from {ENV_EXAMPLE}...")
    shutil.copy(ENV_EXAMPLE, ENV_FILE)
    success(f"Environment file created: {ENV_FILE}")
    return True


def check_ffmpeg():
    """Check if ffmpeg and ffprobe are available."""
    info("Checking FFmpeg...")
    
    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")
    
    if ffmpeg_path and ffprobe_path:
        success(f"ffmpeg found: {ffmpeg_path}")
        success(f"ffprobe found: {ffprobe_path}")
        return True
    
    warn("FFmpeg or ffprobe not found in PATH")
    if os.name == "nt":  # Windows
        warn("To install on Windows, use: choco install ffmpeg")
    elif sys.platform == "darwin":  # macOS
        warn("To install on macOS, use: brew install ffmpeg")
    else:  # Linux
        warn("To install on Linux, use: sudo apt-get install ffmpeg")
    
    warn("Development will proceed, but video processing may fail without FFmpeg")
    return False


def check_redis():
    """Check if Redis is available (Docker or local)."""
    info("Checking Redis...")
    
    redis_path = shutil.which("redis-server")
    if redis_path:
        success(f"Redis found locally: {redis_path}")
        return True
    
    # Check if Docker is available for running Redis
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


def check_openai_key():
    """Check if OpenAI API key is configured."""
    info("Checking OpenAI API Key...")
    
    if not ENV_FILE.exists():
        warn("Environment file not created yet, skipping OpenAI check")
        return True
    
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        env_content = f.read()
    
    if "OPENAI_API_KEY=" in env_content:
        # Extract the value
        for line in env_content.split("\n"):
            if line.startswith("OPENAI_API_KEY="):
                key = line.split("=", 1)[1].strip()
                if key and not key.startswith("#"):
                    success("OpenAI API Key is configured")
                    return True
    
    warn("OpenAI API Key not configured")
    warn("Translation features will not work without it")
    warn("Set OPENAI_API_KEY in backend/.env to enable translation")
    return True  # Not fatal


def compile_check():
    """Check that Python files compile."""
    info("Checking Python syntax...")
    py_exe = get_python_exe()
    
    result = subprocess.run(
        [py_exe, "-m", "compileall", "-q", "backend", "scripts"],
        cwd=ROOT_DIR
    )
    if result.returncode != 0:
        error("Python syntax check failed")
        return False
    success("Python syntax check passed")
    return True


def main():
    print("=" * 60)
    print("AI Subtitle Tool - Development Bootstrap")
    print("=" * 60)
    print()
    
    all_ok = True
    
    # Required checks
    try:
        check_python_version()
    except Exception as e:
        error(f"Python version check failed: {e}")
        sys.exit(1)
    
    try:
        create_venv()
    except Exception as e:
        error(f"Virtual environment setup failed: {e}")
        sys.exit(1)
    
    try:
        if not install_backend_deps():
            all_ok = False
    except Exception as e:
        error(f"Backend dependency installation failed: {e}")
        all_ok = False
    
    try:
        if not check_node_npm():
            all_ok = False
    except Exception as e:
        error(f"Node.js check failed: {e}")
        all_ok = False
    
    try:
        if not install_frontend_deps():
            all_ok = False
    except Exception as e:
        error(f"Frontend dependency installation failed: {e}")
        all_ok = False
    
    try:
        if not create_env_file():
            all_ok = False
    except Exception as e:
        error(f"Environment file creation failed: {e}")
        all_ok = False
    
    # Optional checks (warn only)
    try:
        check_ffmpeg()
    except Exception as e:
        warn(f"FFmpeg check failed: {e}")
    
    try:
        check_redis()
    except Exception as e:
        warn(f"Redis check failed: {e}")
    
    try:
        check_openai_key()
    except Exception as e:
        warn(f"OpenAI check failed: {e}")
    
    try:
        compile_check()
    except Exception as e:
        warn(f"Compile check failed: {e}")
    
    # Summary
    print()
    print("=" * 60)
    print("Bootstrap Summary")
    print("=" * 60)
    print()
    print(f"Python version: ✓ ({sys.version_info.major}.{sys.version_info.minor})")
    print(f"Virtual environment: ✓ ({VENV_DIR})")
    print(f"Backend dependencies: {'✓' if all_ok else '✗'}")
    print(f"Frontend dependencies: {'✓' if all_ok else '✗'}")
    print(f"Environment file (.env): {'✓' if ENV_FILE.exists() else '✗'}")
    print(f"FFmpeg: {'✓' if shutil.which('ffmpeg') else '✗ (optional, required for video processing)'}")
    print(f"Redis: {'✓' if shutil.which('redis-server') else '✗ (required for task queue)'}")
    print(f"OpenAI Key: {'✓' if os.environ.get('OPENAI_API_KEY') else '✗ (optional, required for translation)'}")
    print()
    
    if all_ok:
        success("Bootstrap completed successfully!")
        print()
        print("Next steps:")
        print("1. Press F5 in VS Code to start the full development stack")
        print("   OR run: python scripts/dev_start.py")
        print()
        print("2. Frontend will be available at: http://localhost:5173")
        print("3. Backend API will be available at: http://localhost:8000")
        print("4. API docs at: http://localhost:8000/api/docs")
        print()
    else:
        error("Bootstrap completed with errors. Please check the output above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
