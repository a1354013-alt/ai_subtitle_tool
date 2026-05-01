import logging
import os
import shutil
import subprocess

try:
    from celery import chord
    from .celery_app import celery_app
except ImportError:
    chord = None

    class _NoCelery:
        def task(self, *args, **kwargs):
            def _dec(fn):
                return fn

            return _dec

    celery_app = _NoCelery()

from .pipeline_segments import (
    SimpleSegment,
    prepare_segment_results_for_merge,
    transcribe_segment,
    build_full_video_payload,
)
from .settings import AUTO_SEGMENT_THRESHOLD_SECONDS
from .utils.cleanup_utils import create_task_lock, remove_task_lock, cleanup_old_files as cleanup_old_files_impl

logger = logging.getLogger(__name__)


def _probe_duration_for_strategy(video_path: str):
    from .utils.video_utils import probe_video_duration

    duration = probe_video_duration(video_path)
    if duration is None:
        logger.warning(
            "Falling back to single-task processing because duration probe failed: video_path=%s",
            video_path,
        )
    return duration


def finalize_pipeline(segment_results, video_path, options, update_state_func=None, segments_dir=None):
    """Finalize the pipeline after transcription (parallel or non-parallel).

    Notes (keep responsibilities clear):
    - Segment payloads are validated/converted once via prepare_segment_results_for_merge().
    - Cleanup is best-effort and logged; do not rely on finally to return warnings.
    """

    # Lazy imports to keep this module importable in lightweight test environments.
    from .utils.translate_utils import translate_segments, generate_bilingual_srt
    from .utils.ass_utils import generate_ass
    from .utils.split_utils import merge_segments_subtitles
    from .utils.subtitle_video_utils import burn_subtitles
    from .utils.task_control_utils import is_task_canceled

    business_id = options.get("business_id")
    target_langs = options.get("target_langs", ["Traditional Chinese"])
    do_burn = options.get("burn_subtitles", True)
    subtitle_format = options.get("subtitle_format", "ass")
    hf_token = options.get("hf_token")
    warnings = []

    try:
        if business_id and is_task_canceled(os.path.dirname(os.path.abspath(video_path)), business_id):
            raise RuntimeError("Task canceled")

        upload_dir = os.path.dirname(os.path.abspath(video_path))
        base_path = os.path.join(upload_dir, business_id)

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
                    subprocess.run(
                        [
                            "ffmpeg",
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
                        capture_output=True,
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
        for lang in target_langs:
            if is_task_canceled(upload_dir, business_id):
                raise RuntimeError("Task canceled")
            try:
                lang_trans, _ = translate_segments(segments, "Auto", [lang])
                translations[lang] = lang_trans[lang]
            except Exception as e:
                msg = f"Translation to {lang} failed: {e}. Using original text."
                warnings.append(msg)
                translations[lang] = [s.text for s in segments]
                if update_state_func:
                    update_state_func(state="PROGRESS", meta={"progress": 70, "status": msg})

        if update_state_func:
            update_state_func(state="PROGRESS", meta={"progress": 85, "status": "Generating final subtitles..."})

        result_files = {}
        for lang in target_langs:
            lang_suffix = lang.replace(" ", "_")
            bilingual_srt = f"{base_path}_{lang_suffix}.srt"
            generate_bilingual_srt(segments, translations[lang], bilingual_srt)

            if subtitle_format == "ass":
                bilingual_ass = f"{base_path}_{lang_suffix}.ass"
                ass_segments = [
                    SimpleSegment(s.start, s.end, f"{translations[lang][i]}\\N{s.text}")
                    for i, s in enumerate(segments)
                ]
                generate_ass(ass_segments, bilingual_ass)
                result_files[lang] = bilingual_ass
            else:
                result_files[lang] = bilingual_srt

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

        return {
            "status": "COMPLETED",
            "business_id": business_id,
            "video_path": final_video_path,
            "warnings": list(dict.fromkeys(warnings)),
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

    return transcribe_segment(segment_data, model_size, transcribe_video)


@celery_app.task(bind=True)
def merge_and_finalize_task(self, segment_results, video_path, options, segments_dir=None):
    return finalize_pipeline(
        segment_results, video_path, options, update_state_func=self.update_state, segments_dir=segments_dir
    )


@celery_app.task(bind=True)
def process_video_task(self, video_path: str, options: dict = None):
    options = options or {}
    business_id = options.get("business_id")
    if not business_id:
        raise ValueError("options.business_id is required")

    create_task_lock(business_id)

    try:
        from .utils.video_utils import remove_silence
        from .utils.split_utils import split_video
        from .utils.model_loader import get_model_by_duration
        from .utils.subtitle_utils import transcribe_video
        from .utils.task_control_utils import is_task_canceled

        parallel = options.get("parallel", True)
        do_remove_silence = options.get("remove_silence", False)
        upload_dir = os.path.dirname(os.path.abspath(video_path))
        base_path = os.path.join(upload_dir, business_id)

        current_video = video_path
        if is_task_canceled(upload_dir, business_id):
            raise RuntimeError("Task canceled")
        if do_remove_silence:
            self.update_state(state="PROGRESS", meta={"progress": 5, "status": "Removing silence..."})
            silence_removed_video = f"{base_path}_no_silence.mp4"
            current_video = remove_silence(video_path, silence_removed_video)

        duration = _probe_duration_for_strategy(current_video)
        model_size = get_model_by_duration(duration or AUTO_SEGMENT_THRESHOLD_SECONDS)
        should_segment = bool(parallel and duration is not None and duration > AUTO_SEGMENT_THRESHOLD_SECONDS)

        if should_segment:
            if chord is None:
                logger.warning("Chord unavailable; falling back to non-parallel mode for task %s", business_id)
                should_segment = False

        if should_segment:
            self.update_state(
                state="PROGRESS",
                meta={
                    "progress": 10,
                    "status": f"Splitting video into segments for parallel transcription ({duration:.1f}s)...",
                },
            )
            video_segments = split_video(current_video)
            segments_dir = f"{os.path.splitext(current_video)[0]}_segments"
            header = [transcribe_segment_task.s(seg, model_size) for seg in video_segments]
            callback = merge_and_finalize_task.s(current_video, options, segments_dir=segments_dir)
            workflow = chord(header, callback)
            return self.replace(workflow)

        single_task_status = "Processing single video task"
        if duration is None:
            single_task_status += " (duration probe unavailable; using safe fallback)"
        elif duration <= AUTO_SEGMENT_THRESHOLD_SECONDS:
            single_task_status += f" ({duration:.1f}s video)"
        else:
            single_task_status += " (parallel processing unavailable)"

        self.update_state(state="PROGRESS", meta={"progress": 20, "status": single_task_status})
        srt_path = f"{base_path}.srt"
        segments = transcribe_video(current_video, srt_path, model_size=model_size)
        payload = build_full_video_payload(segments, duration or 0)
        return finalize_pipeline([payload], current_video, options, update_state_func=self.update_state)

    except Exception:
        try:
            remove_task_lock(business_id)
        except Exception:
            logger.warning("Failed to remove task lock after exception: business_id=%s", business_id, exc_info=True)
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
    from .utils.task_control_utils import is_task_canceled

    upload_dir = os.getenv("UPLOAD_DIR", "./uploads")
    base_path = os.path.join(upload_dir, task_id)

    if is_task_canceled(upload_dir, task_id):
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
    self.update_state(state="PROGRESS", meta={"progress": 10, "status": "Rebuilding final video..."})
    burn_subtitles(video_path, subtitle_path, out_path)
    self.update_state(state="PROGRESS", meta={"progress": 100, "status": "Completed"})
    return {"warnings": []}
