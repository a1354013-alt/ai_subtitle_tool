from __future__ import annotations

import re
import sys
from pathlib import Path


ENV_KEY_RE = re.compile(r"^\s{6,}([A-Z][A-Z0-9_]*):", re.MULTILINE)


def _read_env_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        keys.add(stripped.split("=", 1)[0])
    return keys


def verify(repo_root: Path) -> None:
    compose_path = repo_root / "docker-compose.yml"
    backend_env_path = repo_root / "backend" / ".env.example"
    frontend_env_path = repo_root / "frontend" / ".env.example"

    required_files = (
        compose_path,
        backend_env_path,
        frontend_env_path,
        repo_root / "backend" / "Dockerfile",
        repo_root / "frontend" / "Dockerfile",
    )
    for required in required_files:
        if not required.exists():
            raise SystemExit(f"required Docker delivery file missing: {required.relative_to(repo_root).as_posix()}")

    compose = compose_path.read_text(encoding="utf-8")
    required_tokens = (
        "services:",
        "redis:",
        "backend:",
        "worker:",
        "frontend:",
        "backend/.env.example",
        "VITE_API_BASE_URL",
    )
    for token in required_tokens:
        if token not in compose:
            raise SystemExit(f"docker-compose.yml missing required token: {token}")

    backend_env_keys = _read_env_keys(backend_env_path)
    compose_env_keys = {key for key in ENV_KEY_RE.findall(compose) if not key.startswith("VITE_")}
    missing_backend = sorted(compose_env_keys - backend_env_keys)
    if missing_backend:
        raise SystemExit(f"backend/.env.example missing compose environment keys: {', '.join(missing_backend)}")

    frontend_env_keys = _read_env_keys(frontend_env_path)
    if "VITE_API_BASE_URL" not in frontend_env_keys:
        raise SystemExit("frontend/.env.example missing VITE_API_BASE_URL")

    print("docker config verification passed")


def main(argv: list[str]) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    verify(repo_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

