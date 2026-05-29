from __future__ import annotations

# Load environment variables from `backend/.env` for local development.
# In Docker/CI, env vars are typically provided via `env_file`/secrets.
# Never override already-set environment variables.
try:
    from pathlib import Path

    from dotenv import load_dotenv

    load_dotenv(Path(__file__).with_name(".env"), override=False)
except Exception:
    # Keep imports resilient in minimal/test environments.
    pass
