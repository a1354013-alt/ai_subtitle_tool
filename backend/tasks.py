import logging
import os
import re
import shutil
import time
from pathlib import Path

try:
    from celery import chord
    from celery.signals import task_failure, task_revoked
except ImportError:
    chord = None
    task_failure = None
    task_revoked = None

from .celery_app import celery_app

from .pipeline_segments import (
    SimpleSegment,
    prepare_segment_results_for_merge,
    transcribe_segment,
    build_full_video_payload,
)
from . import settings
from .services.upload_validation import normalize_lang_suffix
from .services.llm_capabilities import ensure_translation_available
from .utils.cleanup_utils import create_task_lock, remove_task_lock, cleanup_old_files as cleanup_old_files_impl
from .utils.media_process import run_media_command
from .utils.storage_utils import get_storage_backend

logger = logging.getLogger(__name__)
_INTEGRATION_FILENAME_TOKEN_RE = re.compile(r"__integration_(?P<token>[a-z0-9_]+)")


def _integration_mode_enabled() -> bool:
    return os.getenv("INTEGRATION_TEST_MODE", "").strip().lower() in {"1", "true", "yes", "on"}


def _integration_filename_tokens(filename: str | None) -> set[str]:
    if not filename:
        return set()
    return {match.group("token") for match in _INTEGRATION_FILENAME_TOKEN_RE.finditer(filename.lower())}


def _task_source_filename(task_id: str | None) -> str:
    if not task_id:
        return ""
    entry = _task_history().get(task_id)
    return entry.filename if entry else ""


def _integration_block_seconds(filename: str | None) -> int:
    if not filename:
        return 0
    match = re.search(r"__integration_block_(\d+)s", filename.lower())
    if not match:
        return 0
    try:
        return max(0, int(match.group(1)))
    except ValueError:
        return 0


def _integration_fail_segment_index(filename: str | None) -> int | None:
    if not filename:
        return None
    match = re.search(r"__integration_fail_segment_(\d+)", filename.lower())
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _integration_block_task(task_id: str | None, filename: str | None) -> None:
    if not _integration_mode_enabled():
        return
    block_seconds = _integration_block_seconds(filename)
    if block_seconds <= 0:
        return

    from .utils.task_control_utils import is_task_canceled

    upload_dir = settings.get_upload_dir()
    deadline = time.time() + block_seconds
    logger.info(
        "Integration test blocking enabled for task %s using filename %s for %ss",
        task_id,
        filename,
        block_seconds,
    )
    while time.time() < deadline:
        if task_id and is_task_canceled(upload_dir, task_id):
            raise RuntimeError("Task canceled")
        time.sleep(1)


def _integration_maybe_fail_segment(segment_data: dict) -> None:
    if not _integration_mode_enabled():
        return
    source_filename = str(segment_data.get("source_filename") or "")
    requested_index = _integration_fail_segment_index(source_filename)
    if requested_index is None:
        return
    actual_index = int(segment_data.get("segment_idx", -1))
    if actual_index == requested_index:
        raise RuntimeError(
            f"Integration test requested deterministic failure for segment {actual_index} via {source_filename}"
        )


def _task_history():
    from .storage.task_history import TaskHistoryStore

    return TaskHistoryStore(Path(settings.get_upload_dir()) / "task_history.sqlite3")


def _record_task_state(
    task_id: str | None,
    status: str,
    *,
    progress: int | None = None,
    message: str | None = None,
    warnings: list[str] | None = None,
    error_code: str | None = None,
    suggestion: str | None = None,
    result_task_id: str | None = None,
) -> None:
    if not task_id:
        return
    try:
        store = _task_history()
        duration_seconds = None
        if status in {"SUCCESS", "FAILURE", "CANCELED"}:
            from .storage.task_history import duration_seconds_since

            duration_seconds = duration_seconds_since(store.get_created_at(task_id))
        store.update_status(
            task_id,
            status,
            duration_seconds=duration_seconds,
            progress=progress,
            message=message,
            warnings=warnings,
            error_code=error_code,
            suggestion=suggestion,
            result_task_id=result_task_id,
        )
    except Exception:
        logger.warning("Failed to persist worker task state: %s", task_id, exc_info=True)


def _update_worker_state(task, task_id: str | None, *, state: str, meta: dict) -> None:
    if hasattr(task, "update_state"):
        task.update_state(state=state, meta=meta)
    status = "PROCESSING" if state == "PROGRESS" else state
    _record_task_state(
        task_id,
        status,
        progress=int(meta.get("progress", 0) or 0),
        message=str(meta.get("status") or meta.get("message") or ""),
        warnings=meta.get("warnings") if isinstance(meta.get("warnings"), list) else None,
        error_code=meta.get("error_code"),
        suggestion=meta.get("suggestion"),
        result_task_id=meta.get("result_task_id"),
    )


def _record_storage_upload(storage, local_path: str, remote_path: str, warnings: list[str]) -> None:
    ok = storage.upload_file(local_path, remote_path)
    if ok:
        return
    message = f"Object storage upload failed for {remote_path}"
    if settings.STORAGE_BACKEND == "s3" and settings.S3_UPLOAD_REQUIRED:
        raise RuntimeError(message)
    warnings.append(message)


def _terminal_failure_payload(exc: BaseException | str):
    from .utils.error_handler import handle_known_error, get_error_response
    from .utils.task_control_utils import build_task_failure_payload

    error_code = handle_known_error(exc if isinstance(exc, BaseException) else Exception(str(exc)))
    error_info = get_error_response(error_code)
    return build_task_failure_payload(
        error_code=error_code,
        message=error_info["message"],
        suggestion=error_info["suggestion"],
    )


def _persist_parallel_failure(business_id: str | None, exc: BaseException | str, segments_dir: str | None = None) -> None:
    if not business_id:
        return
    from .utils.task_control_utils import write_task_error_artifact

    failure_payload = _terminal_failure_payload(exc)
    upload_dir = settings.get_upload_dir()
    write_task_error_artifact(business_id, upload_dir, failure_payload)
    _record_task_state(
        business_id,
        "FAILURE",
        progress=0,
        message=failure_payload["message"],
        warnings=[],
        error_code=failure_payload["error_code"],
        suggestion=failure_payload["suggestion"],
    )
    try:
        remove_task_lock(business_id, upload_dir)
    except Exception:
        logger.warning("Failed to remove task lock after parallel failure: %s", business_id, exc_info=True)
    if segments_dir and os.path.exists(segments_dir):
        try:
            shutil.rmtree(segments_dir)
        except Exception:
            logger.warning("Failed to remove segment directory after parallel failure: %s", segments_dir, exc_info=True)


def finalize_pipeline(segment_results, video_path, options, update_state_func=None, segments_dir=None):
    """Finalize the pipeline after transcription (parallel or non-parallel).

    Notes (keep responsibilities clear):
    - Segment payloads are validated/converted once via prepare_segment_results_for_merge().
    - Cleanup is best-effort and logged; do not rely on finally to return warnings.
    """

    # Lazy imports to keep this module importable in lightweight test environments.
    from .utils.translate_utils import (
        translate_segments,
        generate_bilingual_srt,
        should_translate,
    )
    from .utils.ass_utils import generate_ass
    from .utils.split_utils import merge_segments_subtitles
    from .utils.subtitle_text_utils import generate_srt
    from .utils.subtitle_video_utils import burn_subtitles
    from .utils.task_control_utils import is_task_canceled

    business_id = options.get("business_id")
    target_langs = options.get("target_langs", ["Traditional Chinese"])
    do_burn = options.get("burn_subtitles", True)
    subtitle_format = options.get("subtitle_format", "ass")
    hf_token = options.get("hf_token")
    warnings = []

    try:
        if business_id and is_task_canceled(settings.get_upload_dir(), business_id):
            raise RuntimeError("Task canceled")

        upload_dir = settings.get_upload_dir()
        base_path = str(settings.task_artifact_base(business_id))

        if update_state_func:
            update_state_func(state="PROGRESS", meta={"progress": 40, "status": "Merging parallel results..."})

        prepared_results = prepare_segment_results_for_merge(segment_results)
        segments = merge_segments_subtitles(prepared_results)

        # Optional diarization (lazy import)
        if hf_token:
            diarization_ok = False
            try:
                from .utils.diarization_utils import diarize_audio, merge_speaker_info

                diarization_ok = True
            except ImportError:
                warnings.append("Diarization dependencies not installed. Skipping speaker diarization.")
                hf_token = None

            if diarization_ok and hf_token:
                if update_state_func:
                    update_state_func(
                        state="PROGRESS", meta={"progress": 50, "status": "Performing speaker diarization..."}
                    )

                audio_path = None
                try:
                    audio_path = f"{base_path}_temp.wav"
                    run_media_command(
                        [
                            settings.FFMPEG_BINARY,
                            "-y",
                            "-i",
                            video_path,
                            "-vn",
                            "-acodec",
                            "pcm_s16le",
                            "-ar",
                            "16000",
                            "-ac",
                            "1",
                            audio_path,
                        ],
                        check=True,
                        timeout=settings.FFMPEG_TIMEOUT_SECONDS,
                    )
                    diarization_result, diarization_warning = diarize_audio(audio_path, hf_token)
                    if diarization_warning:
                        warnings.append(diarization_warning)
                    segments = merge_speaker_info(segments, diarization_result)
                except Exception as e:
                    warnings.append(f"Diarization failed: {str(e)}")
                finally:
                    if audio_path and os.path.exists(audio_path):
                        try:
                            os.remove(audio_path)
                        except OSError:
                            logger.warning("Failed to remove diarization temp audio: %s", audio_path, exc_info=True)

        if update_state_func:
            update_state_func(state="PROGRESS", meta={"progress": 70, "status": "Translating..."})

        translations = {}
        translated_by_lang = {}
        translation_metadata = []
        llm_status = ensure_translation_available(target_langs)

        for lang in target_langs:
            if is_task_canceled(upload_dir, business_id):
                raise RuntimeError("Task canceled")

            if should_translate(lang, "Auto", llm_status.translation_enabled):
                try:
                    lang_translations, _ = translate_segments(segments, "Auto", [lang])
                    translations[lang] = lang_translations[lang]
                    translated_by_lang[lang] = True
                    translation_metadata.append(
                        {
                            "language": lang,
                            "translated": True,
                            "fallback_reason": None,
                        }
                    )
                except Exception as e:
                    fallback_reason = f"translation provider unavailable: {e}"
                    msg = f"Translation to {lang} failed: {e}. Using original text."
                    warnings.append(msg)
                    translations[lang] = [s.text for s in segments]
                    translated_by_lang[lang] = False
                    translation_metadata.append(
                        {
                            "language": lang,
                            "translated": False,
                            "fallback_reason": fallback_reason,
                        }
                    )
                    if update_state_func:
                        update_state_func(state="PROGRESS", meta={"progress": 70, "status": msg})
            else:
                translations[lang] = [s.text for s in segments]
                translated_by_lang[lang] = False
                translation_metadata.append(
                    {
                        "language": lang,
                        "translated": False,
                        "fallback_reason": None,
                    }
                )

        if update_state_func:
            update_state_func(state="PROGRESS", meta={"progress": 85, "status": "Generating final subtitles..."})

        result_files = {}
        for lang in target_langs:
            lang_suffix = normalize_lang_suffix(lang)
            subtitle_texts = translations[lang]
            is_translated = translated_by_lang.get(lang, False)
            output_srt = f"{base_path}_{lang_suffix}.srt"
            if is_translated:
                generate_bilingual_srt(segments, subtitle_texts, output_srt)
            else:
                monolingual_segments = [
                    SimpleSegment(s.start, s.end, subtitle_texts[i])
                    for i, s in enumerate(segments)
                ]
                with open(output_srt, "w", encoding="utf-8", newline="\n") as srt_file:
                    srt_file.write(generate_srt(monolingual_segments))

            if subtitle_format == "ass":
                output_ass = f"{base_path}_{lang_suffix}.ass"
                if is_translated:
                    ass_segments = [
                        SimpleSegment(s.start, s.end, f"{subtitle_texts[i]}\\N{s.text}")
                        for i, s in enumerate(segments)
                    ]
                else:
                    ass_segments = [
                        SimpleSegment(s.start, s.end, subtitle_texts[i])
                        for i, s in enumerate(segments)
                    ]
                generate_ass(ass_segments, output_ass)
                result_files[lang] = output_ass
            else:
                result_files[lang] = output_srt

        final_video_path = f"{base_path}_final.mp4"
        if do_burn:
            if update_state_func:
                update_state_func(state="PROGRESS", meta={"progress": 95, "status": "Burning subtitles..."})
            first_lang_file = list(result_files.values())[0]
            try:
                if is_task_canceled(upload_dir, business_id):
                    raise RuntimeError("Task canceled")
                burn_subtitles(video_path, first_lang_file, final_video_path)
            except Exception as e:
                warnings.append(f"Subtitle burning failed: {str(e)}. Copying original video.")
                shutil.copy2(video_path, final_video_path)
        else:
            shutil.copy2(video_path, final_video_path)

        if update_state_func:
            update_state_func(state="PROGRESS", meta={"progress": 100, "status": "Completed"})

        # Upload to object storage if configured
        storage = get_storage_backend()
        try:
            # Upload final video
            _record_storage_upload(storage, final_video_path, f"{business_id}_final.mp4", warnings)
            # Upload subtitles
            for lang, path in result_files.items():
                lang_suffix = normalize_lang_suffix(lang)
                ext = os.path.splitext(path)[1]
                _record_storage_upload(storage, path, f"{business_id}_{lang_suffix}{ext}", warnings)
        except Exception as e:
            if settings.STORAGE_BACKEND == "s3" and settings.S3_UPLOAD_REQUIRED:
                raise
            logger.warning("Failed to upload results to object storage: %s", e, exc_info=True)
            warnings.append(f"Object storage upload failed: {e}")

        return {
            "status": "COMPLETED",
            "business_id": business_id,
            "video_path": final_video_path,
            "warnings": list(dict.fromkeys(warnings)),
            "translations": translation_metadata,
        }
    finally:
        if segments_dir and os.path.exists(segments_dir):
            try:
                shutil.rmtree(segments_dir)
            except Exception:
                logger.warning("Could not clean up segments directory: %s", segments_dir, exc_info=True)

        if business_id:
            try:
                remove_task_lock(business_id)
            except Exception:
                logger.warning("Failed to remove task lock: business_id=%s", business_id, exc_info=True)


@celery_app.task
def transcribe_segment_task(segment_data: dict, model_size: str):
    from .utils.subtitle_utils import transcribe_video

    _integration_maybe_fail_segment(segment_data)
    return transcribe_segment(segment_data, model_size, transcribe_video)


@celery_app.task
def parallel_pipeline_failure_task(request=None, exc=None, traceback=None, business_id: str | None = None, segments_dir: str | None = None):
    _persist_parallel_failure(business_id, exc or "Parallel segment pipeline failed", segments_dir=segments_dir)
    return {"status": "FAILURE", "business_id": business_id}


@celery_app.task(bind=True)
def merge_and_finalize_task(self, segment_results, video_path, options, segments_dir=None):
    business_id = (options or {}).get("business_id")
    result = finalize_pipeline(
        segment_results,
        video_path,
        options,
        update_state_func=lambda state, meta: _update_worker_state(self, business_id, state=state, meta=meta),
        segments_dir=segments_dir,
    )
    _record_task_state(
        business_id,
        "SUCCESS",
        progress=100,
        message="Completed",
        warnings=result.get("warnings", []) if isinstance(result, dict) else [],
    )
    return result


@celery_app.task(bind=True)
def process_video_task(self, video_path: str, options: dict = None):
    options = options or {}
    business_id = options.get("business_id")
    if not business_id:
        raise ValueError("options.business_id is required")

    create_task_lock(business_id, settings.get_upload_dir())
    _record_task_state(business_id, "PROCESSING", progress=0, message="Worker started", warnings=[])

    try:
        from .utils.video_utils import remove_silence
        from .utils.split_utils import split_video
        from .utils.model_loader import resolve_model_size
        from .utils.subtitle_utils import transcribe_video
        from .utils.task_control_utils import is_task_canceled
        from moviepy.editor import VideoFileClip

        parallel = options.get("parallel", True)
        do_remove_silence = options.get("remove_silence", False)
        source_filename = str(options.get("source_filename") or "")
        upload_dir = settings.get_upload_dir()
        base_path = str(settings.task_artifact_base(business_id))

        current_video = video_path
        _integration_block_task(business_id, source_filename)
        if is_task_canceled(upload_dir, business_id):
            raise RuntimeError("Task canceled")
        if do_remove_silence:
            _update_worker_state(self, business_id, state="PROGRESS", meta={"progress": 5, "status": "Removing silence..."})
            silence_removed_video = f"{base_path}_no_silence.mp4"
            current_video = remove_silence(video_path, silence_removed_video)

        video = VideoFileClip(current_video)
        duration = video.duration
        video.close()
        model_size = resolve_model_size(duration, options.get("model_size"))

        if parallel and duration > 60:
            if chord is None:
                logger.warning("Chord unavailable; falling back to non-parallel mode for task %s", business_id)
                parallel = False  # Fallback to non-parallel mode

            if parallel:
                _update_worker_state(self, business_id, state="PROGRESS", meta={"progress": 10, "status": "Splitting video..."})
                from .utils.split_utils import expected_segment_count

                expected_segments = expected_segment_count(duration)
                if expected_segments > settings.MAX_PARALLEL_SEGMENTS:
                    raise ValueError(
                        f"Video would produce {expected_segments} segments, exceeding MAX_PARALLEL_SEGMENTS={settings.MAX_PARALLEL_SEGMENTS}"
                    )
                video_segments = split_video(current_video)
                if len(video_segments) > settings.MAX_PARALLEL_SEGMENTS:
                    raise ValueError(
                        f"Video split produced {len(video_segments)} segments, exceeding MAX_PARALLEL_SEGMENTS={settings.MAX_PARALLEL_SEGMENTS}"
                    )
                segments_dir = f"{os.path.splitext(current_video)[0]}_segments"
                # Inherit the current task's queue for sub-tasks
                current_queue = self.request.delivery_info.get("routing_key", "default")
                for segment in video_segments:
                    segment["business_id"] = business_id
                    segment["segments_dir"] = segments_dir
                    segment["source_filename"] = source_filename
                errback = parallel_pipeline_failure_task.s(business_id=business_id, segments_dir=segments_dir).set(queue=current_queue)
                header = [
                    transcribe_segment_task.s(seg, model_size).set(queue=current_queue).on_error(errback)
                    for seg in video_segments
                ]
                callback = merge_and_finalize_task.s(current_video, options, segments_dir=segments_dir).set(queue=current_queue).on_error(errback)
                workflow = chord(header, callback)
                return self.replace(workflow)

        _update_worker_state(self, business_id, state="PROGRESS", meta={"progress": 20, "status": "Transcribing..."})
        srt_path = f"{base_path}.srt"
        segments = transcribe_video(current_video, srt_path, model_size=model_size)
        payload = build_full_video_payload(segments, duration)
        result = finalize_pipeline(
            [payload],
            current_video,
            options,
            update_state_func=lambda state, meta: _update_worker_state(self, business_id, state=state, meta=meta),
        )
        _record_task_state(
            business_id,
            "SUCCESS",
            progress=100,
            message="Completed",
            warnings=result.get("warnings", []) if isinstance(result, dict) else [],
        )
        return result

    except Exception as e:
        try:
            remove_task_lock(business_id, settings.get_upload_dir())
        except Exception:
            logger.warning("Failed to remove task lock after exception: business_id=%s", business_id, exc_info=True)
        
        from .utils.task_control_utils import write_task_error_artifact
        failure_payload = _terminal_failure_payload(e)
        
        # Write to artifact file as backup (survives Celery meta override)
        upload_dir = settings.get_upload_dir()
        write_task_error_artifact(business_id, upload_dir, failure_payload)
        
        _update_worker_state(
            self,
            business_id,
            state="FAILURE",
            meta={
                "progress": 0,
                "status": "FAILED",
                **failure_payload
            },
        )
        raise


@celery_app.task
def cleanup_old_files():
    return cleanup_old_files_impl()


@celery_app.task(bind=True)
def rebuild_final_video_task(self, task_id: str, lang_suffix: str, subtitle_format: str = "ass"):
    """
    Rebuild (re-burn) the final video for an existing task.

    This is intentionally explicit (user-triggered) and never runs automatically on subtitle edit.
    """
    from .utils.subtitle_video_utils import burn_subtitles
    from .utils.task_control_utils import build_task_failure_payload, is_task_canceled, write_task_error_artifact
    from .utils.error_handler import get_error_response, handle_known_error

    upload_dir = settings.get_upload_dir()
    base_path = str(settings.task_artifact_base(task_id))
    rebuild_task_id = str(getattr(getattr(self, "request", None), "id", "") or task_id)

    try:
        _record_task_state(rebuild_task_id, "PROCESSING", progress=0, message="Rebuild worker started", result_task_id=task_id)
        _integration_block_task(rebuild_task_id, _task_source_filename(task_id))
        if is_task_canceled(upload_dir, rebuild_task_id):
            raise RuntimeError("Task canceled")

        # Prefer the silence-removed intermediate if it exists.
        candidate_videos = [
            f"{base_path}_no_silence.mp4",
            f"{base_path}.mp4",
            f"{base_path}.mkv",
            f"{base_path}.avi",
            f"{base_path}.mov",
        ]
        video_path = next((p for p in candidate_videos if os.path.exists(p)), None)
        if not video_path:
            raise FileNotFoundError("Source video not found for rebuild")

        subtitle_path = f"{base_path}_{lang_suffix}.{subtitle_format}"
        if not os.path.exists(subtitle_path):
            raise FileNotFoundError("Subtitle file not found for rebuild")

        out_path = f"{base_path}_final.mp4"
        _update_worker_state(
            self,
            rebuild_task_id,
            state="PROGRESS",
            meta={"progress": 10, "status": "Rebuilding final video...", "result_task_id": task_id},
        )
        burn_subtitles(video_path, subtitle_path, out_path)

        warnings: list[str] = []
        storage = get_storage_backend()
        _record_storage_upload(storage, out_path, f"{task_id}_final.mp4", warnings)

        final_warnings = list(dict.fromkeys(warnings))
        _update_worker_state(
            self,
            rebuild_task_id,
            state="PROGRESS",
            meta={"progress": 100, "status": "Completed", "warnings": final_warnings, "result_task_id": task_id},
        )
        _record_task_state(
            rebuild_task_id,
            "SUCCESS",
            progress=100,
            message="Completed",
            warnings=final_warnings,
            result_task_id=task_id,
        )
        return {"warnings": final_warnings, "result_task_id": task_id}
    except Exception as e:
        error_code = handle_known_error(e)
        error_info = get_error_response(error_code)
        failure_payload = build_task_failure_payload(
            error_code=error_code,
            message=error_info["message"],
            suggestion=error_info["suggestion"],
        )
        write_task_error_artifact(rebuild_task_id, upload_dir, failure_payload)
        _update_worker_state(
            self,
            rebuild_task_id,
            state="FAILURE",
            meta={
                "progress": 0,
                "status": "FAILED",
                **failure_payload,
            },
        )
        raise


if task_failure is not None:
    @task_failure.connect
    def _record_task_failure_signal(sender=None, task_id=None, exception=None, args=None, kwargs=None, **_extra):
        task_name = getattr(sender, "name", "")
        if task_name.endswith("transcribe_segment_task"):
            segment_data = args[0] if args else {}
            if isinstance(segment_data, dict):
                _persist_parallel_failure(
                    segment_data.get("business_id"),
                    exception or "Segment task failed",
                    segments_dir=segment_data.get("segments_dir"),
                )
        elif task_name.endswith("process_video_task"):
            options = args[1] if args and len(args) > 1 else {}
            if isinstance(options, dict):
                _persist_parallel_failure(options.get("business_id"), exception or "Task failed")


if task_revoked is not None:
    @task_revoked.connect
    def _record_task_revoked_signal(sender=None, request=None, expired=None, signum=None, terminated=None, **_extra):
        task_name = getattr(sender, "name", "")
        args = getattr(request, "args", None) or []
        if task_name.endswith("transcribe_segment_task"):
            segment_data = args[0] if args else {}
            if isinstance(segment_data, dict):
                _persist_parallel_failure(
                    segment_data.get("business_id"),
                    "Segment task was revoked or timed out",
                    segments_dir=segment_data.get("segments_dir"),
                )
        elif task_name.endswith("process_video_task"):
            options = args[1] if len(args) > 1 else {}
            if isinstance(options, dict):
                _persist_parallel_failure(options.get("business_id"), "Task was revoked or timed out")
