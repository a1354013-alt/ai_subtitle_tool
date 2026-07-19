from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse

import httpx
import redis


def _run(cmd: list[str], *, timeout: int = 600, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


def _wait_for_ready(base_url: str, *, timeout: int = 120, headers: dict[str, str] | None = None) -> dict[str, Any]:
    deadline = time.time() + timeout
    last_error: str | None = None
    with httpx.Client(timeout=10.0, headers=headers) as client:
        while time.time() < deadline:
            try:
                response = client.get(f"{base_url}/readyz")
                if response.status_code == 200:
                    return response.json()
                last_error = response.text
            except Exception as exc:  # pragma: no cover - exercised in live integration only
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
    upload_name: str,
    parallel: bool,
) -> str:
    with video_path.open("rb") as handle:
        response = client.post(
            f"{base_url}/upload",
            files={"file": (upload_name, handle, "video/mp4")},
            data={
                "target_langs": "Original",
                "burn_subtitles": "false",
                "subtitle_format": "ass",
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


def _batch_upload(client: httpx.Client, base_url: str, video_paths: list[tuple[Path, str]]) -> dict[str, Any]:
    handles = [path.open("rb") for path, _name in video_paths]
    try:
        files = [("files", (name, handle, "video/mp4")) for handle, (_path, name) in zip(handles, video_paths)]
        response = client.post(
            f"{base_url}/batch/upload",
            files=files,
            data={
                "target_langs": "Original",
                "burn_subtitles": "false",
                "subtitle_format": "ass",
                "remove_silence": "false",
                "parallel": "false",
            },
        )
    finally:
        for handle in handles:
            handle.close()
    response.raise_for_status()
    return response.json()


def _poll_status(
    client: httpx.Client,
    base_url: str,
    task_id: str,
    *,
    allowed_terminal: set[str],
    timeout: int,
    allow_processing: bool = False,
) -> dict[str, Any]:
    deadline = time.time() + timeout
    last_payload: dict[str, Any] | None = None
    while time.time() < deadline:
        response = client.get(f"{base_url}/status/{task_id}")
        response.raise_for_status()
        payload = response.json()
        last_payload = payload
        status = str(payload.get("status"))
        if allow_processing and status == "PROCESSING":
            return payload
        if status in allowed_terminal:
            return payload
        time.sleep(2)
    raise RuntimeError(f"Timed out waiting for {task_id}. Last payload: {last_payload}")


def _poll_batch_success(client: httpx.Client, base_url: str, batch_id: str, *, timeout: int = 1800) -> dict[str, Any]:
    deadline = time.time() + timeout
    last_payload: dict[str, Any] | None = None
    while time.time() < deadline:
        response = client.get(f"{base_url}/batch/{batch_id}/status")
        response.raise_for_status()
        payload = response.json()
        last_payload = payload
        if int(payload.get("completed", 0)) == int(payload.get("total", 0)):
            return payload
        if int(payload.get("failed", 0)) > 0:
            raise RuntimeError(f"Batch {batch_id} failed: {payload}")
        time.sleep(2)
    raise RuntimeError(f"Timed out waiting for batch {batch_id}. Last payload: {last_payload}")


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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _task_paths(upload_dir: Path, task_id: str) -> dict[str, Path]:
    return {
        "input": upload_dir / f"{task_id}.mp4",
        "segments": upload_dir / f"{task_id}_segments",
        "lock": upload_dir / f"{task_id}.lock",
        "final_video": upload_dir / f"{task_id}_final.mp4",
        "error": upload_dir / f"{task_id}_error.json",
    }


def _read_subtitle(client: httpx.Client, base_url: str, task_id: str, lang: str) -> dict[str, Any]:
    response = client.get(f"{base_url}/subtitle/{task_id}", params={"lang": lang, "format": "srt"})
    response.raise_for_status()
    return response.json()


def _mutate_srt(content: str) -> str:
    lines = content.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not stripped.isdigit() and "-->" not in stripped:
            lines[index] = f"{line} [integration-edit]"
            return "\n".join(lines) + ("\n" if content.endswith("\n") else "")
    raise RuntimeError("Could not find subtitle dialogue line to edit")


def _start_auth_backend(
    repo_root: Path,
    base_url: str,
    *,
    upload_dir: Path,
    output_dir: Path,
    temp_dir: Path,
    log_path: Path,
    auth_token: str,
) -> tuple[subprocess.Popen[str], str]:
    parsed = urlparse(base_url)
    host = parsed.hostname or "127.0.0.1"
    port = (parsed.port or 8891) + 1
    auth_url = f"{parsed.scheme or 'http'}://{host}:{port}"

    env = os.environ.copy()
    env.update(
        {
            "API_HOST": host,
            "API_PORT": str(port),
            "UPLOAD_DIR": str(upload_dir),
            "OUTPUT_DIR": str(output_dir),
            "TEMP_DIR": str(temp_dir),
            "REQUIRE_AUTH_TOKEN": "true",
            "AUTH_TOKEN": auth_token,
            "INTEGRATION_TEST_MODE": env.get("INTEGRATION_TEST_MODE", "true"),
        }
    )

    log_path.parent.mkdir(parents=True, exist_ok=True)
    handle = log_path.open("w", encoding="utf-8", newline="\n")
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", host, "--port", str(port)],
        cwd=str(repo_root),
        env=env,
        stdout=handle,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        _wait_for_ready(auth_url, timeout=120)
    except Exception:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
        raise
    finally:
        handle.close()
    return process, auth_url


def _stop_process(process: subprocess.Popen[str] | None) -> None:
    if process is None:
        return
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def _ticket_url_for_path(client: httpx.Client, base_url: str, path: str) -> dict[str, Any]:
    response = client.get(f"{base_url}/download-ticket", params={"path": path})
    response.raise_for_status()
    return response.json()


def _build_expired_ticket_url(download_url: str, auth_token: str) -> str:
    import backend.main as backend_main

    parsed = urlparse(download_url)
    query_params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query_params.pop("ticket", None)
    backend_main.settings.AUTH_TOKEN = auth_token
    canonical = backend_main._canonical_download_path(parsed.path, query_params)
    expired_ticket = backend_main._sign_download_ticket(canonical, int(time.time()) - 5)
    expired_query = {**query_params, "ticket": expired_ticket}
    return parsed._replace(query=urlencode(expired_query)).geturl()


def _print_logs(log_paths: list[Path]) -> None:
    for path in log_paths:
        if not path.exists():
            print(f"--- log missing: {path} ---", file=sys.stderr)
            continue
        print(f"--- begin log: {path} ---", file=sys.stderr)
        try:
            print(path.read_text(encoding="utf-8", errors="replace")[-8000:], file=sys.stderr)
        except OSError as exc:
            print(f"Failed to read log {path}: {exc}", file=sys.stderr)
        print(f"--- end log: {path} ---", file=sys.stderr)


def _cleanup_task_artifacts(upload_dir: Path, output_dir: Path, task_id: str) -> None:
    prefixes = [f"{task_id}.", f"{task_id}_", task_id]
    for directory in (upload_dir, output_dir):
        if not directory.exists():
            continue
        for path in directory.iterdir():
            if any(path.name == prefix or path.name.startswith(prefix) for prefix in prefixes):
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    path.unlink(missing_ok=True)


def _verify_release_zip_determinism(repo_root: Path, summary: dict[str, Any]) -> None:
    release_a = repo_root / "release-integration-a.zip"
    release_b = repo_root / "release-integration-b.zip"
    try:
        _run([sys.executable, "scripts/make_release_zip.py", "--out", str(release_a), "--check"], timeout=900)
        source_paths = []
        for path in repo_root.rglob("*"):
            if not path.is_file():
                continue
            if ".git" in path.parts or path.suffix == ".zip":
                continue
            if ".github" in path.parts:
                continue
            source_paths.append(path)
        for path in source_paths:
            os.utime(path, (978307200, 978307200))
        _run([sys.executable, "scripts/make_release_zip.py", "--out", str(release_b), "--check"], timeout=900)
        hash_a = _sha256(release_a)
        hash_b = _sha256(release_b)
        if hash_a != hash_b:
            raise RuntimeError(f"Release zip hashes differed: {hash_a} != {hash_b}")
        summary["checks"]["release_zip_determinism"] = {
            "first_zip": str(release_a),
            "second_zip": str(release_b),
            "first_sha256": hash_a,
            "second_sha256": hash_b,
        }
    finally:
        release_a.unlink(missing_ok=True)
        release_b.unlink(missing_ok=True)


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

    repo_root = Path(__file__).resolve().parents[1]
    upload_dir = Path(os.getenv("UPLOAD_DIR", repo_root / "backend" / "uploads")).resolve()
    output_dir = Path(os.getenv("OUTPUT_DIR", repo_root / "backend" / "outputs")).resolve()
    temp_dir = Path(os.getenv("TEMP_DIR", repo_root / "backend" / "tmp")).resolve()
    work_dir = Path(args.work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    upload_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)

    log_paths = [
        Path(item).resolve()
        for item in os.getenv("INTEGRATION_LOG_PATHS", "").split(os.pathsep)
        if item.strip()
    ]
    auth_log_path = work_dir / "auth-backend.log"
    created_task_ids: list[str] = []
    auth_process: subprocess.Popen[str] | None = None

    summary: dict[str, Any] = {
        "base_url": args.base_url,
        "redis_result_backend": args.redis_result_backend,
        "work_dir": str(work_dir),
        "upload_dir": str(upload_dir),
        "output_dir": str(output_dir),
        "temp_dir": str(temp_dir),
        "checks": {},
    }

    if os.getenv("INTEGRATION_TEST_MODE", "").strip().lower() not in {"1", "true", "yes", "on"}:
        raise RuntimeError("INTEGRATION_TEST_MODE=true is required for deterministic blocking and failure coverage.")

    concurrency = int(os.getenv("CELERY_WORKER_CONCURRENCY", "1"))
    if concurrency != 1:
        raise RuntimeError(
            "CELERY_WORKER_CONCURRENCY must be 1 for deterministic cancellation coverage in real integration smoke."
        )

    short_video = work_dir / "short.mp4"
    long_video = work_dir / "long.mp4"
    batch_video = work_dir / "batch.mp4"
    blocking_video = work_dir / "blocking.mp4"
    rebuild_cancel_video = work_dir / "rebuild-cancel.mp4"

    _make_video(short_video, duration_seconds=3)
    _make_video(long_video, duration_seconds=65)
    _make_video(batch_video, duration_seconds=3)
    _make_video(blocking_video, duration_seconds=3)
    _make_video(rebuild_cancel_video, duration_seconds=3)

    try:
        summary["checks"]["readyz"] = _wait_for_ready(args.base_url)

        with httpx.Client(timeout=90.0) as client:
            success_task_id = _upload_video(
                client,
                args.base_url,
                short_video,
                upload_name="normal-success.mp4",
                parallel=False,
            )
            created_task_ids.append(success_task_id)
            success_status = _poll_status(client, args.base_url, success_task_id, allowed_terminal={"SUCCESS"}, timeout=1800)
            results_response = client.get(f"{args.base_url}/results/{success_task_id}")
            results_response.raise_for_status()
            results_payload = results_response.json()
            if results_payload.get("task_status") != "SUCCESS" or not results_payload.get("has_video"):
                raise RuntimeError(f"Unexpected results payload for {success_task_id}: {results_payload}")

            final_video_download = client.get(f"{args.base_url}/download/{success_task_id}")
            final_video_download.raise_for_status()
            if not final_video_download.content:
                raise RuntimeError(f"Downloaded final video for {success_task_id} is empty")

            available_files = results_payload.get("available_files") or []
            if not available_files:
                raise RuntimeError(f"No subtitle files were recorded for task {success_task_id}")
            primary_lang = str(available_files[0]["lang"])
            subtitle_downloads: dict[str, int] = {}
            for fmt in ("ass", "srt", "vtt"):
                response = client.get(
                    f"{args.base_url}/download/{success_task_id}",
                    params={"lang": primary_lang, "format": fmt},
                )
                response.raise_for_status()
                subtitle_downloads[fmt] = len(response.content)
                if not response.content:
                    raise RuntimeError(f"Downloaded {fmt} subtitle for {success_task_id} is empty")

            success_paths = _task_paths(upload_dir, success_task_id)
            if success_paths["lock"].exists():
                raise RuntimeError(f"Normal success task left a stale lock: {success_paths['lock']}")

            summary["checks"]["normal_task_processing"] = {
                "task_id": success_task_id,
                "status": success_status["status"],
                "primary_lang": primary_lang,
                "subtitle_download_sizes": subtitle_downloads,
            }

            blocking_task_id = _upload_video(
                client,
                args.base_url,
                blocking_video,
                upload_name="blocking__integration_block_20s.mp4",
                parallel=False,
            )
            created_task_ids.append(blocking_task_id)
            blocking_processing = _poll_status(
                client,
                args.base_url,
                blocking_task_id,
                allowed_terminal={"SUCCESS"},
                timeout=120,
                allow_processing=True,
            )
            if blocking_processing.get("status") != "PROCESSING":
                raise RuntimeError(f"Blocking task did not enter PROCESSING: {blocking_processing}")

            canceled_task_id = _upload_video(
                client,
                args.base_url,
                short_video,
                upload_name="cancel-target.mp4",
                parallel=False,
            )
            created_task_ids.append(canceled_task_id)
            cancel_response = client.post(f"{args.base_url}/tasks/{canceled_task_id}/cancel")
            cancel_response.raise_for_status()
            canceled_status = _poll_status(
                client,
                args.base_url,
                canceled_task_id,
                allowed_terminal={"CANCELED"},
                timeout=120,
            )
            if canceled_status.get("error_code") != "task_canceled":
                raise RuntimeError(f"Unexpected canceled status payload: {canceled_status}")
            blocking_terminal = _poll_status(
                client,
                args.base_url,
                blocking_task_id,
                allowed_terminal={"SUCCESS"},
                timeout=1800,
            )
            summary["checks"]["task_cancellation"] = {
                "blocking_task_id": blocking_task_id,
                "blocking_terminal_status": blocking_terminal["status"],
                "canceled_task_id": canceled_task_id,
                "canceled_status": canceled_status["status"],
                "worker_concurrency": concurrency,
            }

            parallel_task_id = _upload_video(
                client,
                args.base_url,
                long_video,
                upload_name="parallel-success.mp4",
                parallel=True,
            )
            created_task_ids.append(parallel_task_id)
            parallel_status = _poll_status(client, args.base_url, parallel_task_id, allowed_terminal={"SUCCESS"}, timeout=2400)
            parallel_results = client.get(f"{args.base_url}/results/{parallel_task_id}")
            parallel_results.raise_for_status()
            parallel_results_payload = parallel_results.json()
            parallel_paths = _task_paths(upload_dir, parallel_task_id)
            if parallel_results_payload.get("task_status") != parallel_status["status"]:
                raise RuntimeError("Parallel success status/result disagreement detected")
            if not parallel_paths["final_video"].exists():
                raise RuntimeError(f"Parallel success final video missing: {parallel_paths['final_video']}")
            if parallel_paths["segments"].exists():
                raise RuntimeError(f"Parallel success left temp segment directory: {parallel_paths['segments']}")
            if parallel_paths["lock"].exists():
                raise RuntimeError(f"Parallel success left task lock: {parallel_paths['lock']}")
            summary["checks"]["parallel_processing_success"] = {
                "task_id": parallel_task_id,
                "status": parallel_status["status"],
                "final_video": str(parallel_paths["final_video"]),
            }

            parallel_failure_task_id = _upload_video(
                client,
                args.base_url,
                long_video,
                upload_name="parallel-failure__integration_fail_segment_1.mp4",
                parallel=True,
            )
            created_task_ids.append(parallel_failure_task_id)
            parallel_failure_status = _poll_status(
                client,
                args.base_url,
                parallel_failure_task_id,
                allowed_terminal={"FAILURE"},
                timeout=2400,
            )
            parallel_failure_paths = _task_paths(upload_dir, parallel_failure_task_id)
            if parallel_failure_status.get("status") != "FAILURE":
                raise RuntimeError(f"Parallel failure task not terminal FAILURE: {parallel_failure_status}")
            if not parallel_failure_status.get("error_code") or not parallel_failure_status.get("message"):
                raise RuntimeError(f"Parallel failure payload missing error details: {parallel_failure_status}")
            if parallel_failure_paths["segments"].exists():
                raise RuntimeError(f"Parallel failure left temp segment directory: {parallel_failure_paths['segments']}")
            if parallel_failure_paths["lock"].exists():
                raise RuntimeError(f"Parallel failure left task lock: {parallel_failure_paths['lock']}")
            summary["checks"]["parallel_processing_failure"] = {
                "task_id": parallel_failure_task_id,
                "status": parallel_failure_status["status"],
                "error_code": parallel_failure_status["error_code"],
                "message": parallel_failure_status["message"],
                "error_artifact_exists": parallel_failure_paths["error"].exists(),
            }

            subtitle_response = _read_subtitle(client, args.base_url, success_task_id, primary_lang)
            edited_subtitle = _mutate_srt(str(subtitle_response["content"]))
            update_response = client.put(
                f"{args.base_url}/subtitle/{success_task_id}",
                params={"lang": primary_lang},
                json={"format": "srt", "content": edited_subtitle},
            )
            update_response.raise_for_status()
            update_payload = update_response.json()
            rebuild_enqueue = client.post(
                f"{args.base_url}/tasks/{success_task_id}/rebuild-final",
                params={"lang": primary_lang, "format": "srt"},
            )
            rebuild_enqueue.raise_for_status()
            rebuild_task_id = str(rebuild_enqueue.json()["rebuild_task_id"])
            created_task_ids.append(rebuild_task_id)
            rebuild_status = _poll_status(client, args.base_url, rebuild_task_id, allowed_terminal={"SUCCESS"}, timeout=1800)
            original_status_after_rebuild = client.get(f"{args.base_url}/status/{success_task_id}")
            original_status_after_rebuild.raise_for_status()
            rebuilt_results = client.get(f"{args.base_url}/results/{rebuild_task_id}")
            rebuilt_results.raise_for_status()
            if rebuild_status.get("result_task_id") != success_task_id:
                raise RuntimeError(f"Rebuild did not point back to original task: {rebuild_status}")
            if original_status_after_rebuild.json().get("status") != "SUCCESS":
                raise RuntimeError("Original successful task lost SUCCESS after rebuild")
            if not success_paths["final_video"].exists():
                raise RuntimeError("Rebuild did not restore the final video artifact")
            summary["checks"]["rebuild_success"] = {
                "original_task_id": success_task_id,
                "rebuild_task_id": rebuild_task_id,
                "update_status": update_payload["status"],
                "rebuild_status": rebuild_status["status"],
                "result_task_id": rebuild_status.get("result_task_id"),
            }

            rebuild_cancel_source_task_id = _upload_video(
                client,
                args.base_url,
                rebuild_cancel_video,
                upload_name="rebuild-cancel__integration_block_20s.mp4",
                parallel=False,
            )
            created_task_ids.append(rebuild_cancel_source_task_id)
            rebuild_cancel_source_status = _poll_status(
                client,
                args.base_url,
                rebuild_cancel_source_task_id,
                allowed_terminal={"SUCCESS"},
                timeout=1800,
            )
            rebuild_cancel_results = client.get(f"{args.base_url}/results/{rebuild_cancel_source_task_id}")
            rebuild_cancel_results.raise_for_status()
            rebuild_cancel_lang = str(rebuild_cancel_results.json()["available_files"][0]["lang"])
            rebuild_cancel_subtitle = _read_subtitle(client, args.base_url, rebuild_cancel_source_task_id, rebuild_cancel_lang)
            rebuild_cancel_edit = _mutate_srt(str(rebuild_cancel_subtitle["content"]))
            put_cancel_subtitle = client.put(
                f"{args.base_url}/subtitle/{rebuild_cancel_source_task_id}",
                params={"lang": rebuild_cancel_lang},
                json={"format": "srt", "content": rebuild_cancel_edit},
            )
            put_cancel_subtitle.raise_for_status()
            rebuild_cancel_enqueue = client.post(
                f"{args.base_url}/tasks/{rebuild_cancel_source_task_id}/rebuild-final",
                params={"lang": rebuild_cancel_lang, "format": "srt"},
            )
            rebuild_cancel_enqueue.raise_for_status()
            rebuild_cancel_task_id = str(rebuild_cancel_enqueue.json()["rebuild_task_id"])
            created_task_ids.append(rebuild_cancel_task_id)
            rebuild_processing = _poll_status(
                client,
                args.base_url,
                rebuild_cancel_task_id,
                allowed_terminal={"CANCELED"},
                timeout=120,
                allow_processing=True,
            )
            if rebuild_processing.get("status") != "PROCESSING":
                raise RuntimeError(f"Rebuild cancel task did not enter PROCESSING: {rebuild_processing}")
            rebuild_cancel_response = client.post(f"{args.base_url}/tasks/{rebuild_cancel_task_id}/cancel")
            rebuild_cancel_response.raise_for_status()
            rebuild_canceled_status = _poll_status(
                client,
                args.base_url,
                rebuild_cancel_task_id,
                allowed_terminal={"CANCELED"},
                timeout=120,
            )
            original_after_rebuild_cancel = client.get(f"{args.base_url}/status/{rebuild_cancel_source_task_id}")
            original_after_rebuild_cancel.raise_for_status()
            if original_after_rebuild_cancel.json().get("status") != "SUCCESS":
                raise RuntimeError("Original task lost SUCCESS after rebuild cancellation")
            if (upload_dir / f"{rebuild_cancel_source_task_id}_error.json").exists():
                raise RuntimeError("Original task unexpectedly received a rebuild cancellation error artifact")
            summary["checks"]["rebuild_cancellation"] = {
                "original_task_id": rebuild_cancel_source_task_id,
                "original_status": rebuild_cancel_source_status["status"],
                "rebuild_task_id": rebuild_cancel_task_id,
                "rebuild_status": rebuild_canceled_status["status"],
            }

            deleted_keys = _delete_result_backend_state(success_task_id, args.redis_result_backend)
            recovered_status = _poll_status(client, args.base_url, success_task_id, allowed_terminal={"SUCCESS"}, timeout=30)
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

            batch_payload = _batch_upload(client, args.base_url, [(batch_video, "batch-success.mp4")])
            batch_id = str(batch_payload["batch_id"])
            batch_task_id = str(batch_payload["tasks"][0]["task_id"])
            created_task_ids.append(batch_task_id)
            batch_status = _poll_batch_success(client, args.base_url, batch_id)
            summary["checks"]["batch_processing"] = {
                "batch_id": batch_id,
                "task_id": batch_task_id,
                "completed": batch_status["completed"],
            }

        auth_token = "integration-secret-token"
        auth_process, auth_url = _start_auth_backend(
            repo_root,
            args.base_url,
            upload_dir=upload_dir,
            output_dir=output_dir,
            temp_dir=temp_dir,
            log_path=auth_log_path,
            auth_token=auth_token,
        )
        auth_headers = {"X-API-Token": auth_token}

        with httpx.Client(timeout=60.0, headers=auth_headers) as auth_client:
            unauthorized = httpx.get(f"{auth_url}/download/{success_task_id}", timeout=30.0)
            if unauthorized.status_code != 401:
                raise RuntimeError(f"Protected direct download should reject without auth: {unauthorized.status_code}")

            subtitle_paths: dict[str, str] = {
                "final_video": f"/download/{success_task_id}",
                "ass": f"/download/{success_task_id}?lang={primary_lang}&format=ass",
                "srt": f"/download/{success_task_id}?lang={primary_lang}&format=srt",
                "vtt": f"/download/{success_task_id}?lang={primary_lang}&format=vtt",
                "batch_zip": f"/batch/{batch_id}/download",
            }
            ticketed_sizes: dict[str, int] = {}
            for label, path in subtitle_paths.items():
                ticket_payload = _ticket_url_for_path(auth_client, auth_url, path)
                ticket_response = httpx.get(f"{auth_url}{ticket_payload['url']}", timeout=60.0)
                ticket_response.raise_for_status()
                ticketed_sizes[label] = len(ticket_response.content)
                if not ticket_response.content:
                    raise RuntimeError(f"Ticketed download returned no content for {label}")

            valid_ticket_payload = _ticket_url_for_path(auth_client, auth_url, subtitle_paths["final_video"])
            tampered_url = f"{auth_url}{valid_ticket_payload['url'][:-1]}0"
            tampered_response = httpx.get(tampered_url, timeout=30.0)
            if tampered_response.status_code != 401:
                raise RuntimeError(f"Invalid ticket should reject with 401, got {tampered_response.status_code}")

            expired_url = _build_expired_ticket_url(valid_ticket_payload["url"], auth_token)
            expired_response = httpx.get(f"{auth_url}{expired_url}", timeout=30.0)
            if expired_response.status_code != 401:
                raise RuntimeError(f"Expired ticket should reject with 401, got {expired_response.status_code}")

            summary["checks"]["protected_downloads"] = {
                "auth_url": auth_url,
                "unauthorized_status": unauthorized.status_code,
                "ticketed_sizes": ticketed_sizes,
                "tampered_status": tampered_response.status_code,
                "expired_status": expired_response.status_code,
            }

        stale_lock = upload_dir / "stale-integration.lock"
        stale_lock.write_text(json.dumps({"business_id": "stale-integration", "pid": 999999, "timestamp": 1}), encoding="utf-8")
        expired_upload = upload_dir / "cleanup-old-integration.mp4"
        expired_upload.write_bytes(b"old")
        preserved_upload = upload_dir / "cleanup-active_final.mp4"
        preserved_upload.write_bytes(b"keep")
        active_lock = upload_dir / "cleanup-active.lock"
        active_lock.write_text(json.dumps({"business_id": "cleanup-active", "timestamp": time.time()}), encoding="utf-8")
        batch_meta_dir = upload_dir / "batches"
        batch_meta_dir.mkdir(exist_ok=True)
        expired_batch_meta = batch_meta_dir / "cleanup-old-batch.json"
        expired_batch_meta.write_text("{}", encoding="utf-8")
        expired_output_zip = output_dir / "cleanup-old-batch.zip"
        expired_output_zip.write_bytes(b"zip")
        recent_output_zip = output_dir / "cleanup-recent-batch.zip"
        recent_output_zip.write_bytes(b"zip")
        stale_temp = temp_dir / "cleanup-old.tmp"
        stale_temp.write_text("temp", encoding="utf-8")
        recent_temp = temp_dir / "cleanup-recent.tmp"
        recent_temp.write_text("temp", encoding="utf-8")

        old_time = time.time() - (10 * 24 * 3600)
        for path in (stale_lock, expired_upload, expired_batch_meta, expired_output_zip, stale_temp):
            os.utime(path, (old_time, old_time))

        from backend.celery_app import celery_app

        cleanup_result = celery_app.send_task("backend.tasks.cleanup_old_files")
        cleanup_payload = cleanup_result.get(timeout=60)
        if Path(stale_lock).exists():
            raise RuntimeError("Cleanup task did not remove stale lock")
        if expired_upload.exists():
            raise RuntimeError("Cleanup task did not remove expired upload")
        if expired_batch_meta.exists():
            raise RuntimeError("Cleanup task did not remove expired batch metadata")
        if expired_output_zip.exists():
            raise RuntimeError("Cleanup task did not remove expired output ZIP")
        if stale_temp.exists():
            raise RuntimeError("Cleanup task did not remove expired temp artifact")
        if not preserved_upload.exists():
            raise RuntimeError("Cleanup task removed active locked artifact")
        if not recent_output_zip.exists() or not recent_temp.exists():
            raise RuntimeError("Cleanup task removed recent artifacts that should be preserved")
        summary["checks"]["cleanup_via_celery"] = cleanup_payload

        _verify_release_zip_determinism(repo_root, summary)
        print(json.dumps(summary, indent=2))
        return 0
    except Exception:
        summary["task_ids"] = created_task_ids
        print(json.dumps(summary, indent=2), file=sys.stderr)
        all_logs = list(log_paths)
        if auth_log_path.exists():
            all_logs.append(auth_log_path)
        _print_logs(all_logs)
        raise
    finally:
        for task_id in created_task_ids:
            try:
                _cleanup_task_artifacts(upload_dir, output_dir, task_id)
            except Exception:
                pass
        _stop_process(auth_process)
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
