#!/usr/bin/env python3
"""
Development stack starter script.
Manages all subprocesses (backend, frontend, worker, Redis) in a single process.
Handles graceful shutdown on Ctrl+C.

Automatically runs bootstrap if prerequisites are missing.
Automatically starts Redis via Docker or falls back to Celery eager mode.
"""
import os
import subprocess
import sys
import signal
import time
import argparse
import threading
import shutil
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional, List

from runtime_requirements import is_supported_node_version, node_version_error_message

ROOT_DIR = Path(__file__).parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"
VENV_DIR = ROOT_DIR / ".venv"
ENV_FILE = BACKEND_DIR / ".env"
FRONTEND_ENV_FILE = FRONTEND_DIR / ".env"
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8891
FRONTEND_HOST = "127.0.0.1"
FRONTEND_PORT = 5173
BACKEND_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}"
FRONTEND_URL = f"http://{FRONTEND_HOST}:{FRONTEND_PORT}"


def info(msg: str):
    print(f"[DEV] {msg}", flush=True)


def success(msg: str):
    print(f"[OK] {msg}", flush=True)


def error(msg: str):
    print(f"[ERROR] {msg}", flush=True, file=sys.stderr)


def warn(msg: str):
    print(f"[WARN] {msg}", flush=True)


def get_python_exe() -> str:
    """Get the Python executable path for the venv."""
    if os.name == "nt":  # Windows
        return str(VENV_DIR / "Scripts" / "python.exe")
    else:  # macOS/Linux
        return str(VENV_DIR / "bin" / "python")


def get_npm_exe() -> str:
    """Use the Windows command shim so subprocess can launch npm reliably."""
    return shutil.which("npm.cmd") or shutil.which("npm") or "npm"


def check_node_version() -> bool:
    node_exe = shutil.which("node")
    if not node_exe:
        error("Node.js is not available on PATH.")
        error("Node.js 20.x is required. Run: python scripts/dev_bootstrap.py")
        return False
    try:
        result = subprocess.run(
            [node_exe, "--version"],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception as exc:
        error(f"Failed to check Node.js version: {exc}")
        return False
    version_text = result.stdout.strip()
    if result.returncode != 0 or not is_supported_node_version(version_text):
        error(node_version_error_message(version_text))
        error("VS Code F5 requires Node.js 20.x even when frontend/node_modules already exists.")
        return False
    return True


def _python_version(python_exe: str) -> tuple[int, int] | None:
    try:
        result = subprocess.run(
            [python_exe, "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    try:
        major, minor = result.stdout.strip().split(".", 1)
        return int(major), int(minor)
    except ValueError:
        return None


def _supported_python(python_exe: str) -> bool:
    version = _python_version(python_exe)
    return version is not None and version[0] == 3 and version[1] in (11, 12)


def get_bootstrap_python_exe() -> str:
    """Choose a supported Python for bootstrap, even if the existing venv is stale."""
    if _supported_python(sys.executable):
        return sys.executable
    if os.name == "nt":
        for launcher_arg in ("-3.11", "-3.12"):
            try:
                result = subprocess.run(
                    ["py", launcher_arg, "-c", "import sys; print(sys.executable)"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            except Exception:
                continue
            if result.returncode == 0:
                candidate = result.stdout.strip()
                if candidate and _supported_python(candidate):
                    return candidate
    error("Python 3.11 or 3.12 is required for first-run bootstrap.")
    error("Install Python 3.11 or 3.12, or make it available through the Windows py launcher as py -3.11 or py -3.12.")
    sys.exit(1)


def backend_deps_available() -> bool:
    """Return True when the venv can import the modules needed for F5 startup."""
    py_exe = get_python_exe()
    if not Path(py_exe).exists():
        return False
    if not _supported_python(py_exe):
        return False
    result = subprocess.run(
        [py_exe, "-c", "import fastapi, uvicorn, celery, redis"],
        cwd=ROOT_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


class ProcessManager:
    """Manages multiple subprocesses with coordinated shutdown."""
    
    def __init__(self):
        self.processes: dict[str, subprocess.Popen] = {}
        self.stopped = False
        self.failures: dict[str, int] = {}
        
        # Register signal handlers
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)
    
    def _handle_signal(self, signum, frame):
        """Handle Ctrl+C and termination signals."""
        info("Shutting down development stack...")
        self.shutdown()
        sys.exit(0)
    
    def add_process(
        self,
        name: str,
        cmd: List[str],
        cwd: Optional[Path] = None,
        env_vars: Optional[dict] = None
    ) -> bool:
        """Start a subprocess and track it."""
        info(f"Starting {name}...")
        
        try:
            env = os.environ.copy()
            if env_vars:
                env.update(env_vars)
            
            if os.name == "nt":
                # Windows-specific subprocess handling
                creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                creation_flags = 0
            
            process = subprocess.Popen(
                cmd,
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                creationflags=creation_flags if os.name == "nt" else 0
            )
            
            self.processes[name] = process
            success(f"{name} started (PID: {process.pid})")
            
            # Start a thread to monitor and print output in real-time
            thread = threading.Thread(target=self._stream_output, args=(name,), daemon=True)
            thread.start()
            
            return True
        except Exception as e:
            error(f"Failed to start {name}: {e}")
            return False
    
    def _stream_output(self, name: str):
        """Stream output from a process in real-time."""
        if name not in self.processes:
            return
        
        process = self.processes[name]
        try:
            for line in process.stdout:
                if line.strip():
                    print(f"[{name}] {line.rstrip()}", flush=True)
        except Exception:
            pass
        finally:
            return_code = process.wait()
            if return_code != 0 and not self.stopped:
                self.failures[name] = return_code
                error(f"{name} exited with code {return_code}")
    
    def monitor_process(self, name: str):
        """Monitor a single process and print its output."""
        if name not in self.processes:
            return
        
        process = self.processes[name]
        try:
            for line in process.stdout:
                if line.strip():
                    print(f"[{name}] {line.rstrip()}", flush=True)
        except:
            pass
        finally:
            return_code = process.wait()
            if return_code != 0 and not self.stopped:
                self.failures[name] = return_code
                error(f"{name} exited with code {return_code}")
    
    def shutdown(self):
        """Gracefully shutdown all processes."""
        self.stopped = True
        info("Terminating all processes...")
        
        # Try graceful shutdown first
        for name, process in self.processes.items():
            if process.poll() is None:  # Still running
                info(f"Terminating {name} (PID: {process.pid})...")
                try:
                    process.terminate()
                except Exception as e:
                    error(f"Failed to terminate {name}: {e}")
        
        # Wait for processes to shutdown
        time.sleep(2)
        
        # Force kill if still running
        for name, process in self.processes.items():
            if process.poll() is None:
                info(f"Force killing {name} (PID: {process.pid})...")
                try:
                    process.kill()
                except Exception as e:
                    error(f"Failed to kill {name}: {e}")
        
        # Wait for all to exit
        for name, process in self.processes.items():
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                error(f"{name} did not exit in time")


def check_prerequisites() -> bool:
    """Check if all prerequisites are met."""
    info("Checking prerequisites...")
    
    # Check venv
    if not VENV_DIR.exists():
        error(f"Virtual environment not found at {VENV_DIR}")
        error("Run: python scripts/dev_bootstrap.py")
        return False
    
    # Check .env
    if not ENV_FILE.exists():
        error(f"Environment file not found at {ENV_FILE}")
        error("Run: python scripts/dev_bootstrap.py")
        return False

    if not FRONTEND_ENV_FILE.exists():
        error(f"Frontend environment file not found at {FRONTEND_ENV_FILE}")
        error("Run: python scripts/dev_bootstrap.py")
        return False

    if not check_node_version():
        return False
    
    # Check node_modules
    if not (FRONTEND_DIR / "node_modules").exists():
        error(f"Frontend dependencies not installed")
        error("Run: python scripts/dev_bootstrap.py")
        return False
    
    success("All prerequisites met")
    return True


def check_redis_running() -> bool:
    """Check if Redis is already running."""
    try:
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('127.0.0.1', 6379))
        sock.close()
        return result == 0
    except:
        return False


def check_docker_available() -> bool:
    """Check if Docker is available."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except:
        return False


def start_redis_with_docker() -> bool:
    """Start Redis using Docker if not already running."""
    container_name = "ai-subtitle-tool-redis-dev"
    # Check if redis container already exists
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", f"name={container_name}", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if container_name in result.stdout:
            success("Redis container already running")
            return True

        exited = subprocess.run(
            ["docker", "ps", "-a", "--filter", f"name={container_name}", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if container_name in exited.stdout:
            subprocess.run(["docker", "start", container_name], capture_output=True, timeout=20)
            time.sleep(2)
            return check_redis_running()
        
        # Start new Redis container
        info("Starting Redis container...")
        result = subprocess.run(
            ["docker", "run", "-d", "--name", container_name, "-p", "6379:6379", "redis:7-alpine"],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode != 0:
            warn(result.stderr.strip() or "docker run failed")
            return False
        time.sleep(2)  # Wait for Redis to start
        return check_redis_running()
    except Exception as e:
        warn(f"Failed to start Redis via Docker: {e}")
        return False


def ensure_prerequisites():
    """Ensure all prerequisites are met, running bootstrap if needed."""
    needs_bootstrap = False
    
    # Check venv
    if not VENV_DIR.exists():
        error(f"Virtual environment not found at {VENV_DIR}")
        needs_bootstrap = True
    
    # Check .env
    if not ENV_FILE.exists():
        error(f"Environment file not found at {ENV_FILE}")
        needs_bootstrap = True

    if not FRONTEND_ENV_FILE.exists():
        error(f"Frontend environment file not found at {FRONTEND_ENV_FILE}")
        needs_bootstrap = True

    if not check_node_version():
        needs_bootstrap = True

    # Check backend dependencies
    if not backend_deps_available():
        error("Backend dependencies are missing from .venv")
        needs_bootstrap = True
    
    # Check node_modules
    if not (FRONTEND_DIR / "node_modules").exists():
        error(f"Frontend dependencies not installed")
        needs_bootstrap = True
    
    if needs_bootstrap:
        info("Running bootstrap to set up missing prerequisites...")
        bootstrap_script = ROOT_DIR / "scripts" / "dev_bootstrap.py"
        bootstrap_python = get_bootstrap_python_exe()
        result = subprocess.run([bootstrap_python, str(bootstrap_script)], cwd=ROOT_DIR)
        if result.returncode != 0:
            error("Bootstrap failed. Please fix the errors above and try again.")
            sys.exit(1)
        success("Bootstrap completed successfully")
    
    # Re-check after bootstrap
    if not VENV_DIR.exists():
        error(f"Virtual environment still not found after bootstrap")
        sys.exit(1)
    
    if not (FRONTEND_DIR / "node_modules").exists():
        error(f"Frontend dependencies still not installed after bootstrap")
        sys.exit(1)

    if not FRONTEND_ENV_FILE.exists():
        error(f"Frontend environment file still not found after bootstrap")
        sys.exit(1)

    if not check_node_version():
        sys.exit(1)

    missing_media_tools = [name for name in ("ffmpeg", "ffprobe") if shutil.which(name) is None]
    if missing_media_tools:
        warn(f"Missing media tools on PATH: {', '.join(missing_media_tools)}")
        warn("Backend and frontend startup will continue; video processing will fail until FFmpeg is installed.")


def setup_redis_mode(redis_mode: str) -> tuple[bool, dict]:
    """
    Setup Redis based on mode. Returns (redis_available, env_vars).
    
    Modes:
    - "auto": Try Docker first, fallback to eager
    - "docker": Use Docker for Redis
    - "eager": Use Celery eager mode
    - "external": Assume Redis is running externally
    """
    env_vars = {}
    
    if redis_mode == "eager":
        info("Using Celery eager mode (no Redis required)")
        env_vars["CELERY_TASK_ALWAYS_EAGER"] = "true"
        env_vars["CELERY_TASK_EAGER_PROPAGATES"] = "true"
        return False, env_vars
    
    if redis_mode == "external":
        if check_redis_running():
            success("Redis is running externally")
            return True, env_vars
        else:
            error("Redis mode is 'external' but Redis is not running on localhost:6379")
            sys.exit(1)
    
    if redis_mode == "docker":
        if check_docker_available():
            if start_redis_with_docker():
                success("Redis started via Docker")
                return True, env_vars
            else:
                error("Failed to start Redis via Docker")
                sys.exit(1)
        else:
            error("Docker not available but --redis docker was specified")
            sys.exit(1)
    
    # Auto mode: try Docker first, fallback to eager
    if check_redis_running():
        success("Redis is already running")
        return True, env_vars
    
    if check_docker_available():
        if start_redis_with_docker():
            success("Redis started via Docker")
            return True, env_vars
        else:
            warn("Failed to start Redis via Docker, falling back to eager mode")
    
    # Fallback to eager mode
    info("[dev] Redis unavailable; using Celery eager dev mode.")
    env_vars["CELERY_TASK_ALWAYS_EAGER"] = "true"
    env_vars["CELERY_TASK_EAGER_PROPAGATES"] = "true"
    return False, env_vars


def check_port_available(port: int) -> bool:
    """Check if a port is available."""
    try:
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('127.0.0.1', port))
        sock.close()
        return result != 0
    except:
        return True


def _process_exited(manager: ProcessManager, required_names: tuple[str, ...]) -> str | None:
    for name in required_names:
        process = manager.processes.get(name)
        if process is not None and process.poll() is not None:
            return name
    return None


def wait_for_http(url: str, manager: ProcessManager, required_names: tuple[str, ...], timeout_seconds: int) -> bool:
    deadline = time.time() + timeout_seconds
    last_error = ""
    while time.time() < deadline:
        failed_name = _process_exited(manager, required_names)
        if failed_name:
            error(f"{failed_name} exited before {url} became ready.")
            return False
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if 200 <= response.status < 500:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = str(exc)
        time.sleep(1)
    error(f"Timed out waiting for {url}. Last error: {last_error or 'no response'}")
    return False


def wait_for_tcp(host: str, port: int, manager: ProcessManager, required_names: tuple[str, ...], timeout_seconds: int) -> bool:
    import socket

    deadline = time.time() + timeout_seconds
    last_error = ""
    while time.time() < deadline:
        failed_name = _process_exited(manager, required_names)
        if failed_name:
            error(f"{failed_name} exited before {host}:{port} became ready.")
            return False
        try:
            with socket.create_connection((host, port), timeout=2):
                return True
        except OSError as exc:
            last_error = str(exc)
        time.sleep(1)
    error(f"Timed out waiting for {host}:{port}. Last error: {last_error or 'no response'}")
    return False


def main():
    parser = argparse.ArgumentParser(description="AI Subtitle Tool - Development Stack Starter")
    parser.add_argument(
        "--redis",
        choices=["auto", "docker", "eager", "external"],
        default="auto",
        help="Redis mode: auto (default), docker, eager, or external"
    )
    args = parser.parse_args()
    
    print("=" * 70)
    print("AI Subtitle Tool - Development Stack Starter")
    print("=" * 70)
    print()
    
    # Ensure prerequisites (auto-run bootstrap if needed)
    ensure_prerequisites()
    
    # Setup Redis
    redis_available, redis_env_vars = setup_redis_mode(args.redis)
    
    print()
    info("Starting full development stack...")
    print()
    
    manager = ProcessManager()
    
    # Check if ports are available
    if not check_port_available(BACKEND_PORT):
        error(f"Port {BACKEND_PORT} is already in use. Is the backend already running?")
        sys.exit(1)
    
    if not check_port_available(FRONTEND_PORT):
        warn(f"Port {FRONTEND_PORT} is already in use. Frontend may fail to start.")
    
    print()
    
    py_exe = get_python_exe()
    
    # Start backend
    if not manager.add_process(
        "BACKEND",
        [py_exe, "-m", "uvicorn", "backend.main:app", "--host", BACKEND_HOST, "--port", str(BACKEND_PORT), "--reload"],
        cwd=ROOT_DIR,
        env_vars={"PYTHONUNBUFFERED": "1", "ENVIRONMENT": "development", "API_PORT": str(BACKEND_PORT), **redis_env_vars}
    ):
        manager.shutdown()
        sys.exit(1)
    
    # Start frontend
    if not manager.add_process(
        "FRONTEND",
        [get_npm_exe(), "run", "dev", "--", "--host", FRONTEND_HOST, "--port", str(FRONTEND_PORT)],
        cwd=FRONTEND_DIR,
        env_vars={"VITE_API_BASE_URL": BACKEND_URL}
    ):
        manager.shutdown()
        sys.exit(1)
    
    # Start Celery worker only if Redis is available (not in eager mode)
    if redis_available:
        if not manager.add_process(
            "WORKER",
            [py_exe, "-m", "celery", "-A", "backend.celery_app:celery_app", "worker", "--loglevel=info"],
            cwd=ROOT_DIR,
            env_vars={"PYTHONUNBUFFERED": "1", "ENVIRONMENT": "development", **redis_env_vars}
        ):
            manager.shutdown()
            sys.exit(1)
    else:
        info("[DEV] Skipping Celery worker because eager mode is enabled.")

    required_processes = ("BACKEND", "FRONTEND", "WORKER") if redis_available else ("BACKEND", "FRONTEND")

    info("Waiting for backend health check and frontend dev server...")
    if not wait_for_http(f"{BACKEND_URL}/healthz", manager, required_processes, 60):
        manager.shutdown()
        sys.exit(1)
    success(f"Backend health check ready: {BACKEND_URL}/healthz")

    if not wait_for_tcp(FRONTEND_HOST, FRONTEND_PORT, manager, required_processes, 60):
        manager.shutdown()
        sys.exit(1)
    success(f"Frontend dev server ready: {FRONTEND_URL}")

    if redis_available:
        info("Celery worker is running with Redis broker.")
    else:
        info("Celery eager mode is enabled; no worker process is running.")
    
    print()
    print("=" * 70)
    success("Development stack is ready.")
    print()
    print("Services:")
    print(f"  Frontend: {FRONTEND_URL}")
    print(f"  API Docs: {BACKEND_URL}/docs")
    print(f"  Health:   {BACKEND_URL}/healthz")
    print()
    if not redis_available:
        print("Note: Running in Celery eager mode (no Redis)")
    print("To stop: Press Ctrl+C")
    print("=" * 70)
    print()
    
    # Monitor processes
    try:
        while True:
            for name in list(manager.processes.keys()):
                process = manager.processes[name]
                if process.poll() is not None:
                    error(f"{name} exited. Check the output above for errors.")
                    manager.shutdown()
                    sys.exit(process.returncode or 1)
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        manager.shutdown()


if __name__ == "__main__":
    main()
