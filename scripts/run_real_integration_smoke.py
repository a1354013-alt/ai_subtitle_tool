from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import redis


def _run(cmd: list[str], *, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _wait_for_ready(base_url: str, *, timeout: int = 120) -> dict[str, Any]:
    deadline = time.time() + timeout
    last_error: str | None = None
    with httpx.Client(timeout=10.0) as client:
        while time.time() < deadline:
            try:
                response = client.get(f"{base_url}/readyz")
                if response.status_code == 200:
                    return response.json()
                last_error = response.text
            except Exception as exc:  # pragma: no cover - exercised in CI
                last_error = str(exc)
            time.sleep(2)
    raise RuntimeError(f"Backend did not become ready within {timeout}s. Last error: {last_error}")


def _make_video(path: Path, *, duration_seconds: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s=320x180:d={duration_seconds}",
            "-f",
            "lavfi",
            "-i",
            f"sine=f=440:d={duration_seconds}",
            "-shortest",
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(path),
        ],
        timeout=max(600, duration_seconds * 4),
    )


def _upload_video(
    client: httpx.Client,
    base_url: str,
    video_path: Path,
    *,
    parallel: bool,
) -> str:
    with video_path.open("rb") as handle:
        response = client.post(
            f"{base_url}/upload",
            files={"file": (video_path.name, handle, "video/mp4")},
            data={
                "target_langs": "Original",
                "burn_subtitles": "false",
                "subtitle_format": "srt",
                "remove_silence": "false",
                "parallel": "true" if parallel else "false",
            },
        )
    response.raise_for_status()
    payload = response.json()
    task_id = str(payload["task_id"])
    if payload["status"] != "PENDING":
        raise RuntimeError(f"Unexpected upload status for {task_id}: {payload}")
    return task_id


def _poll_status(
    client: httpx.Client,
    base_url: str,
    task_id: str,
    *,
    allowed_terminal: set[str],
    timeout: int,
) -> dict[str, Any]:
    deadline = time.time() + timeout
    last_payload: dict[str, Any] | None = None
    while time.time() < deadline:
        response = client.get(f"{base_url}/status/{task_id}")
        response.raise_for_status()
        payload = response.json()
        last_payload = payload
        status = str(payload.get("status"))
        if status in allowed_terminal:
            return payload
        time.sleep(2)
    raise RuntimeError(f"Timed out waiting for {task_id}. Last payload: {last_payload}")


def _delete_result_backend_state(task_id: str, redis_url: str) -> list[str]:
    client = redis.Redis.from_url(redis_url)
    deleted_keys: list[str] = []
    patterns = [f"celery-task-meta-{task_id}", f"*{task_id}*"]
    seen: set[bytes] = set()
    for pattern in patterns:
        for key in client.scan_iter(match=pattern):
            if key in seen:
                continue
            seen.add(key)
            if client.delete(key):
                deleted_keys.append(key.decode("utf-8", errors="replace"))
    if not deleted_keys:
        raise RuntimeError(f"No Celery result backend keys found for task {task_id}")
    return deleted_keys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run real Redis/Celery/API integration smoke checks.")
    parser.add_argument("--base-url", default=os.getenv("INTEGRATION_BASE_URL", "http://127.0.0.1:8891"))
    parser.add_argument(
        "--redis-result-backend",
        default=os.getenv("CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/1"),
    )
    parser.add_argument(
        "--work-dir",
        default=os.getenv("INTEGRATION_WORK_DIR", "integration-smoke-artifacts"),
    )
    args = parser.parse_args(argv)

    work_dir = Path(args.work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {
        "base_url": args.base_url,
        "redis_result_backend": args.redis_result_backend,
        "work_dir": str(work_dir),
        "checks": {},
    }

    summary["checks"]["readyz"] = _wait_for_ready(args.base_url)

    short_video = work_dir / "short.mp4"
    blocking_video = work_dir / "blocking.mp4"
    canceled_video = work_dir / "canceled.mp4"

    _make_video(short_video, duration_seconds=3)
    _make_video(blocking_video, duration_seconds=75)
    _make_video(canceled_video, duration_seconds=3)

    with httpx.Client(timeout=60.0) as client:
        success_task_id = _upload_video(client, args.base_url, short_video, parallel=False)
        success_status = _poll_status(
            client,
            args.base_url,
            success_task_id,
            allowed_terminal={"SUCCESS"},
            timeout=1800,
        )
        summary["checks"]["normal_task_processing"] = {
            "task_id": success_task_id,
            "status": success_status["status"],
        }

        results_response = client.get(f"{args.base_url}/results/{success_task_id}")
        results_response.raise_for_status()
        results_payload = results_response.json()
        if results_payload.get("task_status") != "SUCCESS" or not results_payload.get("has_video"):
            raise RuntimeError(f"Unexpected results payload for {success_task_id}: {results_payload}")

        download_response = client.get(f"{args.base_url}/download/{success_task_id}")
        download_response.raise_for_status()
        if not download_response.content:
            raise RuntimeError(f"Downloaded final video for {success_task_id} is empty")

        blocking_task_id = _upload_video(client, args.base_url, blocking_video, parallel=False)
        time.sleep(2)
        canceled_task_id = _upload_video(client, args.base_url, canceled_video, parallel=False)

        cancel_response = client.post(f"{args.base_url}/tasks/{canceled_task_id}/cancel")
        cancel_response.raise_for_status()
        cancel_payload = cancel_response.json()
        if cancel_payload.get("status") != "canceled":
            raise RuntimeError(f"Unexpected cancel response: {cancel_payload}")

        canceled_status = _poll_status(
            client,
            args.base_url,
            canceled_task_id,
            allowed_terminal={"CANCELED"},
            timeout=120,
        )
        if canceled_status.get("error_code") != "task_canceled":
            raise RuntimeError(f"Unexpected canceled status payload: {canceled_status}")
        summary["checks"]["task_cancellation"] = {
            "blocking_task_id": blocking_task_id,
            "canceled_task_id": canceled_task_id,
            "status": canceled_status["status"],
        }

        deleted_keys = _delete_result_backend_state(success_task_id, args.redis_result_backend)
        recovered_status = _poll_status(
            client,
            args.base_url,
            success_task_id,
            allowed_terminal={"SUCCESS"},
            timeout=30,
        )
        recovered_results = client.get(f"{args.base_url}/results/{success_task_id}")
        recovered_results.raise_for_status()
        recovered_payload = recovered_results.json()
        if recovered_payload.get("task_status") != "SUCCESS":
            raise RuntimeError(f"Result-state recovery failed: {recovered_payload}")
        summary["checks"]["redis_result_state_loss_recovery"] = {
            "task_id": success_task_id,
            "deleted_keys": deleted_keys,
            "status": recovered_status["status"],
        }

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
