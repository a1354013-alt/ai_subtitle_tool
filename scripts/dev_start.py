#!/usr/bin/env python3
"""
Development stack starter script.
Manages all subprocesses (backend, frontend, worker, Redis) in a single process.
Handles graceful shutdown on Ctrl+C.
"""
import os
import subprocess
import sys
import signal
import time
from pathlib import Path
from typing import Optional, List

ROOT_DIR = Path(__file__).parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"
VENV_DIR = ROOT_DIR / ".venv"
ENV_FILE = BACKEND_DIR / ".env"


def info(msg: str):
    print(f"[DEV] {msg}", flush=True)


def success(msg: str):
    print(f"[✓] {msg}", flush=True)


def error(msg: str):
    print(f"[✗] {msg}", flush=True, file=sys.stderr)


def get_python_exe() -> str:
    """Get the Python executable path for the venv."""
    if os.name == "nt":  # Windows
        return str(VENV_DIR / "Scripts" / "python.exe")
    else:  # macOS/Linux
        return str(VENV_DIR / "bin" / "python")


class ProcessManager:
    """Manages multiple subprocesses with coordinated shutdown."""
    
    def __init__(self):
        self.processes: dict[str, subprocess.Popen] = {}
        self.stopped = False
        
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
            return True
        except Exception as e:
            error(f"Failed to start {name}: {e}")
            return False
    
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
                    if os.name == "nt":
                        # Windows: use CTRL_C_EVENT
                        os.kill(process.pid, signal.CTRL_C_EVENT)
                    else:
                        # Unix: use SIGTERM
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
                    if os.name == "nt":
                        os.kill(process.pid, signal.SIGKILL)
                    else:
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


def main():
    print("=" * 70)
    print("AI Subtitle Tool - Development Stack Starter")
    print("=" * 70)
    print()
    
    # Check prerequisites
    if not check_prerequisites():
        sys.exit(1)
    
    print()
    info("Starting full development stack...")
    print()
    
    manager = ProcessManager()
    
    # Check if Redis is running
    redis_running = check_redis_running()
    if not redis_running:
        warn("Redis not running on localhost:6379")
        info("You can start Redis with: docker run -d -p 6379:6379 redis:7-alpine")
        info("Or: redis-server")
        print()
        response = input("Start without Redis? (y/n): ").strip().lower()
        if response != "y":
            info("Aborted.")
            sys.exit(1)
    else:
        success("Redis is running")
    
    # Check if ports are available
    if not check_port_available(8000):
        error("Port 8000 is already in use. Is the backend already running?")
        sys.exit(1)
    
    if not check_port_available(5173):
        warn("Port 5173 is already in use. Frontend may fail to start.")
    
    print()
    
    py_exe = get_python_exe()
    
    # Start background services first
    if redis_running:
        info("Redis already running, skipping")
    else:
        info("Note: Redis should be running separately")
    
    # Start backend
    manager.add_process(
        "BACKEND",
        [py_exe, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000", "--reload"],
        cwd=ROOT_DIR,
        env_vars={"PYTHONUNBUFFERED": "1", "ENVIRONMENT": "development"}
    )
    
    # Start frontend
    manager.add_process(
        "FRONTEND",
        ["npm", "run", "dev"],
        cwd=FRONTEND_DIR,
        env_vars={"VITE_API_BASE_URL": "http://127.0.0.1:8000"}
    )
    
    # Start Celery worker
    manager.add_process(
        "WORKER",
        [py_exe, "-m", "celery", "-A", "backend.celery_app:celery_app", "worker", "--loglevel=info"],
        cwd=ROOT_DIR,
        env_vars={"PYTHONUNBUFFERED": "1", "ENVIRONMENT": "development"}
    )
    
    print()
    print("=" * 70)
    success("Development stack is starting...")
    print()
    print("Services:")
    print("  Frontend: http://localhost:5173")
    print("  Backend:  http://localhost:8000")
    print("  API Docs: http://localhost:8000/api/docs")
    print()
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
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        manager.shutdown()


def warn(msg: str):
    print(f"[⚠] {msg}", flush=True)


if __name__ == "__main__":
    main()
