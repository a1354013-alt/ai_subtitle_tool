#!/usr/bin/env python3
"""
System dependencies checker for development.
Verifies FFmpeg, Redis, and other critical tools.
"""
import shutil
import subprocess
import sys


def check_ffmpeg() -> bool:
    """Check if ffmpeg and ffprobe are in PATH."""
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    
    if ffmpeg and ffprobe:
        print(f"✓ ffmpeg: {ffmpeg}")
        print(f"✓ ffprobe: {ffprobe}")
        return True
    
    if not ffmpeg:
        print("✗ ffmpeg not found in PATH")
    if not ffprobe:
        print("✗ ffprobe not found in PATH")
    
    return False


def check_redis() -> bool:
    """Check if Redis is running."""
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, socket_connect_timeout=2)
        r.ping()
        print("✓ Redis running at localhost:6379")
        return True
    except ImportError:
        print("⚠ redis-py not installed (should be in requirements)")
        return False
    except Exception as e:
        print(f"✗ Redis not running: {e}")
        print("  Start with: redis-server")
        print("  Or: docker run -d -p 6379:6379 redis:7-alpine")
        return False


def check_docker() -> bool:
    """Check if Docker is available."""
    docker = shutil.which("docker")
    if docker:
        print(f"✓ Docker: {docker}")
        return True
    print("⚠ Docker not found (optional)")
    return False


def check_npm() -> bool:
    """Check if npm is available."""
    npm = shutil.which("npm")
    if npm:
        print(f"✓ npm: {npm}")
        return True
    print("✗ npm not found")
    return False


def main():
    print("System Dependencies Check")
    print("=" * 40)
    
    all_ok = True
    
    if not check_ffmpeg():
        all_ok = False
    
    print()
    
    if not check_redis():
        all_ok = False
    
    print()
    
    if not check_npm():
        all_ok = False
    
    print()
    check_docker()
    
    print()
    print("=" * 40)
    if all_ok:
        print("All required dependencies are available")
        return 0
    else:
        print("Some dependencies are missing")
        return 1


if __name__ == "__main__":
    sys.exit(main())
