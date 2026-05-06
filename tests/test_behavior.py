import asyncio
import importlib
import io
import json
import time
import os
import shutil
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend.pipeline_segments import (
    SimpleSegment as PayloadSegment,
    build_full_video_payload,
    prepare_segment_results_for_merge,
    transcribe_segment,
)


_TEMP_DIRS: list[Path] = []


def _make_tmpdir() -> Path:
    d = Path(tempfile.mkdtemp(prefix="ai_subtitle_tool_test_"))
    _TEMP_DIRS.append(d)
    return d


def tearDownModule():  # noqa: N802 (unittest naming convention)
    # Best-effort cleanup to avoid leaving artifacts in the repo/workspace.
    for d in _TEMP_DIRS:
        shutil.rmtree(d, ignore_errors=True)


def _run(coro):
    return asyncio.run(coro)


def _load_app_with_upload_dir(upload_dir: str):
    os.environ["UPLOAD_DIR"] = upload_dir
    import backend.main as main  # import inside helper for reload

    return importlib.reload(main)


class _UploadFileStub:
    def __init__(self, filename: str, content: bytes, content_type: str | None):
        self.filename = filename
        self.content_type = content_type
        self.file = io.BytesIO(content)


class TestFinalizeAndMergePayloads(unittest.TestCase):
    def test_prepare_segment_results_requires_uniform_payload(self):
        with self.assertRaises(ValueError):
            prepare_segment_results_for_merge({"not": "a list"})

        with self.assertRaises(ValueError):
            prepare_segment_results_for_merge([{"start_offset": 0}])

    def test_prepare_segment_results_converts_segments_once(self):
        payload = [
            {
                "start_offset": 0,
                "end_offset": 30,
                "overlap": 0,
                "segment_idx": 0,
                "segments": [{"start": 0.0, "end": 1.0, "text": "Hello"}],
            }
        ]
        prepared = prepare_segment_results_for_merge(payload)
        self.assertEqual(len(prepared), 1)
        self.assertEqual(prepared[0]["start_offset"], 0)
        self.assertTrue(hasattr(prepared[0]["segments"][0], "start"))
        self.assertEqual(prepared[0]["segments"][0].text, "Hello")

    def test_transcribe_segment_returns_metadata_and_removes_temp_srt(self):
        tmpdir = _make_tmpdir()
        segment_path = str(tmpdir / "seg_000.mp4")
        temp_srt = f"{segment_path}.srt"

        def _fake_transcribe(_path, _srt_path, model_size=None):
            return [PayloadSegment(0.0, 1.0, "Hello")]

        segment_data = {
            "path": segment_path,
            "start_offset": 28.0,
            "end_offset": 60.0,
            "overlap": 2.0,
            "segment_idx": 1,
        }

        with (
            patch("backend.pipeline_segments.os.path.exists", return_value=True),
            patch("backend.pipeline_segments.os.remove") as remove_mock,
        ):
            result = transcribe_segment(segment_data, "tiny", _fake_transcribe)

        self.assertEqual(result["start_offset"], 28.0)
        self.assertEqual(result["end_offset"], 60.0)
        self.assertEqual(result["overlap"], 2.0)
        self.assertEqual(result["segment_idx"], 1)
        self.assertEqual(result["segments"][0]["text"], "Hello")
        remove_mock.assert_called_once_with(temp_srt)

    def test_non_parallel_builds_uniform_payload(self):
        payload = build_full_video_payload([PayloadSegment(0.0, 1.0, "Hi")], duration=10.0)
        self.assertEqual(set(payload.keys()), {"start_offset", "end_offset", "overlap", "segment_idx", "segments"})
        self.assertEqual(payload["end_offset"], 10.0)
        self.assertEqual(payload["overlap"], 0)


class TestMergeSegmentsDedupNormalize(unittest.TestCase):
    def test_overlap_dedup_whitespace_case_punct(self):
        from backend.utils.split_utils import SimpleSegment, merge_segments_subtitles

        segment_results = [
            {
                "start_offset": 0.0,
                "end_offset": 30.0,
                "overlap": 2.0,
                "segment_idx": 0,
                "segments": [SimpleSegment(28.0, 29.0, "Hello   World!")],
            },
            {
                "start_offset": 28.0,
                "end_offset": 60.0,
                "overlap": 2.0,
                "segment_idx": 1,
                "segments": [SimpleSegment(0.0, 1.0, " hello world ")],
            },
        ]

        merged = merge_segments_subtitles(segment_results)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].start, 28.0)


class TestSubtitleAndDownloadEndpoints(unittest.TestCase):
    def test_put_subtitle_only_updates_target_format_and_requests_final_delete(self):
        tmpdir = _make_tmpdir()
        main = _load_app_with_upload_dir(str(tmpdir))

        task_id = str(uuid.uuid4())
        lang = "Traditional_Chinese"

        srt_path = tmpdir / f"{task_id}_{lang}.srt"
        ass_path = tmpdir / f"{task_id}_{lang}.ass"
        final_path = tmpdir / f"{task_id}_final.mp4"
        srt_path.write_text("OLD_SRT", encoding="utf-8")
        ass_path.write_text("OLD_ASS", encoding="utf-8")
        final_path.write_bytes(b"video")

        def _fake_replace(src: str, dst: str):
            Path(dst).write_text(Path(src).read_text(encoding="utf-8"), encoding="utf-8")
            return None

        with (
            patch.object(main.os, "remove", autospec=True) as remove_mock,
            patch.object(main.os, "replace", side_effect=_fake_replace),
        ):
            result = _run(
                main.update_subtitle(
                    task_id=task_id,
                    edit=main.SubtitleEditRequest(content="NEW_SRT", format="srt"),
                    lang=lang,
                )
            )

        self.assertEqual(result["status"], "updated")
        self.assertIn("warnings", result)
        self.assertIsInstance(result["warnings"], list)
        self.assertNotIn("warning", result)
        self.assertEqual(srt_path.read_text(encoding="utf-8"), "NEW_SRT")
        self.assertEqual(ass_path.read_text(encoding="utf-8"), "OLD_ASS")
        remove_mock.assert_called()

        # final.mp4 不存在時，下載影片應回 404（符合現行規格）
        with (
            patch.object(main.os.path, "exists", return_value=False),
            self.assertRaises(main.HTTPException) as ctx,
        ):
            _run(main.download_result(task_id=task_id, lang=None, format=None))
        self.assertEqual(ctx.exception.status_code, 404)

        # GET /subtitle 應回指定格式內容
        get_srt = _run(main.get_subtitle(task_id=task_id, lang=lang, format="srt"))
        self.assertEqual(get_srt["content"], "NEW_SRT")

        get_ass = _run(main.get_subtitle(task_id=task_id, lang=lang, format="ass"))
        self.assertEqual(get_ass["content"], "OLD_ASS")

    def test_update_subtitle_uses_atomic_replace(self):
        tmpdir = _make_tmpdir()
        main = _load_app_with_upload_dir(str(tmpdir))

        task_id = str(uuid.uuid4())
        lang = "Traditional_Chinese"
        srt_path = tmpdir / f"{task_id}_{lang}.srt"
        srt_path.write_text("OLD", encoding="utf-8")

        calls: list[tuple[str, str]] = []

        def _spy_replace(src: str, dst: str):
            calls.append((src, dst))
            # 不真的 replace（避免環境限制），只驗證呼叫與最終檔案內容
            # 以 copy 的方式模擬「替換完成」的結果
            Path(dst).write_text(Path(src).read_text(encoding="utf-8"), encoding="utf-8")
            return None

        with patch.object(main.os, "replace", side_effect=_spy_replace):
            _run(
                main.update_subtitle(
                    task_id=task_id,
                    edit=main.SubtitleEditRequest(content="NEW", format="srt"),
                    lang=lang,
                )
            )

        self.assertEqual(srt_path.read_text(encoding="utf-8"), "NEW")
        self.assertTrue(any(dst == str(srt_path) for (_src, dst) in calls))

    def test_update_subtitle_write_failure_does_not_corrupt_original(self):
        tmpdir = _make_tmpdir()
        main = _load_app_with_upload_dir(str(tmpdir))

        task_id = str(uuid.uuid4())
        lang = "Traditional_Chinese"
        srt_path = tmpdir / f"{task_id}_{lang}.srt"
        srt_path.write_text("OLD", encoding="utf-8")

        with (
            patch.object(main.os, "replace", side_effect=OSError("nope")),
            self.assertRaises(main.HTTPException) as ctx,
        ):
            _run(
                main.update_subtitle(
                    task_id=task_id,
                    edit=main.SubtitleEditRequest(content="NEW", format="srt"),
                    lang=lang,
                )
            )

        self.assertEqual(ctx.exception.status_code, 500)
        self.assertEqual(srt_path.read_text(encoding="utf-8"), "OLD")
        # 暫存檔清理失敗只應記錄 log，不應影響 API 行為；此測試只關注原檔不被破壞

    def test_update_subtitle_invalid_format_is_400(self):
        tmpdir = _make_tmpdir()
        main = _load_app_with_upload_dir(str(tmpdir))
        task_id = str(uuid.uuid4())

        with self.assertRaises(main.HTTPException) as ctx:
            _run(
                main.update_subtitle(
                    task_id=task_id,
                    edit=main.SubtitleEditRequest(content="X", format="vtt"),
                    lang="Traditional_Chinese",
                )
            )
        self.assertEqual(ctx.exception.status_code, 400)

    def test_update_subtitle_missing_file_is_404(self):
        tmpdir = _make_tmpdir()
        main = _load_app_with_upload_dir(str(tmpdir))
        task_id = str(uuid.uuid4())

        with self.assertRaises(main.HTTPException) as ctx:
            _run(
                main.update_subtitle(
                    task_id=task_id,
                    edit=main.SubtitleEditRequest(content="X", format="srt"),
                    lang="Traditional_Chinese",
                )
            )
        self.assertEqual(ctx.exception.status_code, 404)


class TestUploadMimeAndFfprobe(unittest.TestCase):
    def test_upload_allows_octet_stream_when_ffprobe_ok(self):
        tmpdir = _make_tmpdir()
        main = _load_app_with_upload_dir(str(tmpdir))

        fake_ffprobe = MagicMock(returncode=0, stdout="video\n", stderr="")
        with (
            patch("subprocess.run", return_value=fake_ffprobe),
            patch.object(main, "_enqueue_process_video_task", return_value=None),
        ):
            result = _run(
                main.upload_video(
                    file=_UploadFileStub("video.mp4", b"dummy", "application/octet-stream"),
                    target_langs="Traditional Chinese",
                    burn_subtitles=True,
                    subtitle_format="ass",
                    remove_silence=False,
                    parallel=False,
                )
            )

        self.assertTrue(uuid.UUID(result.task_id))
        self.assertEqual(result.status, "PENDING")

    def test_upload_filters_empty_target_langs(self):
        tmpdir = _make_tmpdir()
        main = _load_app_with_upload_dir(str(tmpdir))

        fake_ffprobe = MagicMock(returncode=0, stdout="video\n", stderr="")
        captured: dict = {}

        def _capture_enqueue(_file_path: str, options: dict, _task_id: str) -> None:
            captured.update(options)

        with (
            patch("subprocess.run", return_value=fake_ffprobe),
            patch.object(main, "_enqueue_process_video_task", side_effect=_capture_enqueue),
        ):
            _run(
                main.upload_video(
                    file=_UploadFileStub("video.mp4", b"dummy", "application/octet-stream"),
                    target_langs="Traditional Chinese,",
                    burn_subtitles=True,
                    subtitle_format="ass",
                    remove_silence=False,
                    parallel=False,
                )
            )

        self.assertEqual(captured["target_langs"], ["Traditional Chinese"])

    def test_upload_rejects_empty_target_langs(self):
        tmpdir = _make_tmpdir()
        main = _load_app_with_upload_dir(str(tmpdir))

        fake_ffprobe = MagicMock(returncode=0, stdout="video\n", stderr="")
        with (
            patch("subprocess.run", return_value=fake_ffprobe),
            patch.object(main, "_enqueue_process_video_task", return_value=None),
        ):
            with self.assertRaises(main.HTTPException) as ctx:
                _run(
                    main.upload_video(
                        file=_UploadFileStub("video.mp4", b"dummy", "application/octet-stream"),
                        target_langs=" ,  ,",
                        burn_subtitles=True,
                        subtitle_format="ass",
                        remove_silence=False,
                        parallel=False,
                    )
                )
        self.assertEqual(ctx.exception.status_code, 400)

    def test_upload_rejects_illegal_mime_before_ffprobe(self):
        tmpdir = _make_tmpdir()
        main = _load_app_with_upload_dir(str(tmpdir))

        with self.assertRaises(main.HTTPException) as ctx:
            _run(
                main.upload_video(
                    file=_UploadFileStub("video.mp4", b"dummy", "text/plain"),
                    target_langs="Traditional Chinese",
                    burn_subtitles=True,
                    subtitle_format="ass",
                    remove_silence=False,
                    parallel=False,
                )
            )
        self.assertEqual(ctx.exception.status_code, 400)

    def test_upload_rejects_when_ffprobe_fails(self):
        tmpdir = _make_tmpdir()
        main = _load_app_with_upload_dir(str(tmpdir))

        fake_ffprobe = MagicMock(returncode=1, stdout="", stderr="not video")
        with (
            patch("subprocess.run", return_value=fake_ffprobe),
            patch.object(main, "_enqueue_process_video_task", return_value=None),
        ):
            with self.assertRaises(main.HTTPException) as ctx:
                _run(
                    main.upload_video(
                        file=_UploadFileStub("video.mp4", b"dummy", "application/octet-stream"),
                        target_langs="Traditional Chinese",
                        burn_subtitles=True,
                        subtitle_format="ass",
                        remove_silence=False,
                        parallel=False,
                    )
                )

        self.assertEqual(ctx.exception.status_code, 400)

    def test_upload_preserves_http_exception_from_enqueue(self):
        tmpdir = _make_tmpdir()
        main = _load_app_with_upload_dir(str(tmpdir))

        fake_ffprobe = MagicMock(returncode=0, stdout="video\n", stderr="")
        with (
            patch("subprocess.run", return_value=fake_ffprobe),
            patch.object(main, "_enqueue_process_video_task", side_effect=main.HTTPException(status_code=503, detail="no worker")),
        ):
            with self.assertRaises(main.HTTPException) as ctx:
                _run(
                    main.upload_video(
                        file=_UploadFileStub("video.mp4", b"dummy", "application/octet-stream"),
                        target_langs="Traditional Chinese",
                        burn_subtitles=True,
                        subtitle_format="ass",
                        remove_silence=False,
                        parallel=False,
                    )
                )

        self.assertEqual(ctx.exception.status_code, 503)


class TestPathTraversalAndManifest(unittest.TestCase):
    def test_validate_path_traversal_blocks_escape(self):
        tmpdir = _make_tmpdir()
        main = _load_app_with_upload_dir(str(tmpdir))

        allowed_root = str(tmpdir)
        outside = str(Path(tmpdir).parent / "evil.txt")
        with self.assertRaises(main.HTTPException) as ctx:
            main.validate_path_traversal(outside, allowed_root)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_results_manifest_parses_lang_suffix_with_dots(self):
        tmpdir = _make_tmpdir()
        main = _load_app_with_upload_dir(str(tmpdir))
        task_id = str(uuid.uuid4())

        # 模擬 uploads 目錄內的檔案列表（語言後綴含 '.'）
        fake_files = [f"{task_id}_English.UK.ass"]

        class _FakeAsyncResult:
            status = "SUCCESS"
            result = {"warnings": []}

        with (
            patch.object(main, "_get_async_result", return_value=_FakeAsyncResult()),
            patch.object(main.os, "listdir", return_value=fake_files),
            patch.object(main.os.path, "exists", return_value=False),
        ):
            manifest = _run(main.get_results_manifest(task_id=task_id))

        langs = {f.lang for f in manifest.available_files}
        self.assertIn("English.UK", langs)

    def test_results_manifest_available_files_is_sorted(self):
        tmpdir = _make_tmpdir()
        main = _load_app_with_upload_dir(str(tmpdir))
        task_id = str(uuid.uuid4())

        # out-of-order file list
        fake_files = [
            f"{task_id}_Zulu.srt",
            f"{task_id}_alpha.ass",
            f"{task_id}_Bravo.srt",
        ]

        class _FakeAsyncResult:
            status = "SUCCESS"
            result = {"warnings": []}

        with (
            patch.object(main, "_get_async_result", return_value=_FakeAsyncResult()),
            patch.object(main.os, "listdir", return_value=fake_files),
            patch.object(main.os.path, "exists", return_value=False),
        ):
            manifest = _run(main.get_results_manifest(task_id=task_id))

        ordered = [f.lang for f in manifest.available_files]
        self.assertEqual(ordered, ["alpha", "Bravo", "Zulu"])

    def test_results_manifest_non_success_does_not_expose_outputs(self):
        tmpdir = _make_tmpdir()
        main = _load_app_with_upload_dir(str(tmpdir))
        task_id = str(uuid.uuid4())

        # Even if files exist, non-success statuses should not expose them as available outputs.
        fake_files = [f"{task_id}_Traditional_Chinese.srt"]

        class _FakeAsyncResult:
            status = "PENDING"
            result = None
            info = None

        with (
            patch.object(main, "_get_async_result", return_value=_FakeAsyncResult()),
            patch.object(main.os, "listdir", return_value=fake_files),
        ):
            manifest = _run(main.get_results_manifest(task_id=task_id))

        self.assertEqual(manifest.task_status, "PENDING")
        self.assertEqual(manifest.available_files, [])
        self.assertTrue(manifest.orphaned_files_detected)


class TestTargetLangNormalization(unittest.TestCase):
    def test_normalize_target_langs_filters_empty_and_dedups_preserving_order(self):
        tmpdir = _make_tmpdir()
        main = _load_app_with_upload_dir(str(tmpdir))

        raw = "Traditional Chinese,  English,English , , Traditional   Chinese,"
        langs = main.normalize_target_langs(raw)
        self.assertEqual(langs, ["Traditional Chinese", "English"])


class TestStatusEndpoint(unittest.TestCase):
    def test_status_pending_progress_success_failure(self):
        tmpdir = _make_tmpdir()
        main = _load_app_with_upload_dir(str(tmpdir))
        task_id = str(uuid.uuid4())

        class _R:
            def __init__(self, status, info=None, result=None):
                self.status = status
                self.info = info
                self.result = result

        # PENDING
        main.TASK_HISTORY.upsert_created(task_id=task_id, filename="demo.mp4", status="PENDING")
        with patch.object(main, "_get_async_result", return_value=_R("PENDING")):
            res = _run(main.get_status(task_id=task_id))
            self.assertEqual(res.status, "PENDING")
            self.assertIsInstance(res.warnings, list)

        # PROGRESS -> PROCESSING
        with patch.object(main, "_get_async_result", return_value=_R("PROGRESS", info={"progress": 12, "status": "x", "warnings": ["w1"]})):
            res = _run(main.get_status(task_id=task_id))
            self.assertEqual(res.status, "PROCESSING")
            self.assertEqual(res.progress, 12)
            self.assertEqual(res.warnings, ["w1"])

        # SUCCESS
        with patch.object(main, "_get_async_result", return_value=_R("SUCCESS", result={"warnings": ["w2"]})):
            res = _run(main.get_status(task_id=task_id))
            self.assertEqual(res.status, "SUCCESS")
            self.assertEqual(res.progress, 100)
            self.assertEqual(res.warnings, ["w2"])

        # FAILURE
        with patch.object(main, "_get_async_result", return_value=_R("FAILURE", result="boom")):
            res = _run(main.get_status(task_id=task_id))
            self.assertEqual(res.status, "FAILURE")
            self.assertTrue(isinstance(res.message, str))

    def test_status_canceled_is_terminal_canceled(self):
        tmpdir = _make_tmpdir()
        main = _load_app_with_upload_dir(str(tmpdir))
        task_id = str(uuid.uuid4())

        (tmpdir / f"{task_id}.cancel").write_text("canceled\n", encoding="utf-8")
        res = _run(main.get_status(task_id=task_id))
        self.assertEqual(res.status, "CANCELED")
        self.assertEqual(res.error_code, "task_canceled")
        self.assertTrue(isinstance(res.suggestion, str) and len(res.suggestion) > 0)


class TestUnifiedTaskPaths(unittest.TestCase):
    def test_settings_generate_consistent_paths_for_api_and_worker(self):
        tmpdir = _make_tmpdir()
        os.environ["UPLOAD_DIR"] = str(tmpdir)

        import backend.settings as app_settings
        import backend.main as main
        import backend.tasks as tasks

        app_settings = importlib.reload(app_settings)
        main = importlib.reload(main)
        tasks = importlib.reload(tasks)

        task_id = str(uuid.uuid4())
        input_path = app_settings.task_input_path(task_id, ".mp4")
        artifact_base = app_settings.task_artifact_base(task_id)
        final_path = app_settings.task_final_video_path(task_id)

        self.assertEqual(str(input_path.parent), main.UPLOAD_DIR)
        self.assertEqual(str(artifact_base.parent), main.UPLOAD_DIR)
        self.assertEqual(str(final_path.parent), main.UPLOAD_DIR)
        self.assertEqual(app_settings.get_upload_dir(), main.UPLOAD_DIR)


class TestSubtitleFallbackAndDownload(unittest.TestCase):
    def test_get_subtitle_fallback_prefers_ass_then_srt(self):
        tmpdir = _make_tmpdir()
        main = _load_app_with_upload_dir(str(tmpdir))
        task_id = str(uuid.uuid4())
        lang = "Traditional Chinese"  # backend normalizes whitespace -> underscore

        (tmpdir / f"{task_id}_Traditional_Chinese.srt").write_text("SRT", encoding="utf-8")
        (tmpdir / f"{task_id}_Traditional_Chinese.ass").write_text("ASS", encoding="utf-8")

        res = _run(main.get_subtitle(task_id=task_id, lang=lang, format=None))
        self.assertEqual(res["format"], "ass")
        self.assertEqual(res["content"], "ASS")

    def test_download_video_when_exists(self):
        tmpdir = _make_tmpdir()
        main = _load_app_with_upload_dir(str(tmpdir))
        task_id = str(uuid.uuid4())

        (tmpdir / f"{task_id}_final.mp4").write_bytes(b"video")
        res = _run(main.download_result(task_id=task_id, lang=None, format=None))
        self.assertTrue(hasattr(res, "path"))


class TestDiarizationObservability(unittest.TestCase):
    def test_diarize_audio_reports_reason_when_dependency_missing(self):
        # This test must be runnable without installing heavy diarization deps.
        from backend.utils.diarization_utils import diarize_audio

        segments, warning = diarize_audio(audio_path="dummy.wav", hf_token="token")
        self.assertEqual(segments, [])
        self.assertTrue(isinstance(warning, str) and len(warning) > 0)
        self.assertIn("pyannote", warning.lower())


class TestCleanupOldFiles(unittest.TestCase):
    def test_cleanup_respects_valid_lock(self):
        import backend.utils.cleanup_utils as cu

        now = time.time()
        business_id = "biz_valid"
        locked_file = f"{business_id}_final.mp4"
        lock_name = f"{business_id}.lock"

        with (
            patch.object(cu, "is_lock_stale", return_value=False),
            patch.object(cu.os, "listdir", return_value=[lock_name, locked_file]),
            patch.object(cu.os.path, "exists", return_value=True),
            patch.object(cu.os.path, "getmtime", return_value=now - (25 * 3600)),
            patch.object(cu.os.path, "isdir", return_value=False),
            patch.object(cu.os.path, "isfile", return_value=True),
            patch.object(cu.os, "remove") as remove_mock,
        ):
            cu.cleanup_old_files(upload_dir="X")

        # A valid lock must prevent deletion of task files.
        removed_paths = " ".join(str(c.args[0]) for c in remove_mock.call_args_list)
        self.assertNotIn(locked_file, removed_paths)
        self.assertNotIn(lock_name, removed_paths)

    def test_cleanup_removes_stale_lock_and_old_files(self):
        import backend.utils.cleanup_utils as cu

        now = time.time()
        business_id = "biz_stale"
        lock_name = f"{business_id}.lock"
        old_file = f"{business_id}_final.mp4"

        def _is_stale(lock_path, _threshold):
            return str(lock_path).endswith(lock_name)

        with (
            patch.object(cu, "is_lock_stale", side_effect=_is_stale),
            patch.object(cu.os, "listdir", return_value=[lock_name, old_file]),
            patch.object(cu.os.path, "exists", return_value=True),
            patch.object(cu.os.path, "getmtime", return_value=now - (25 * 3600)),
            patch.object(cu.os.path, "isdir", return_value=False),
            patch.object(cu.os.path, "isfile", return_value=True),
            patch.object(cu.os, "remove") as remove_mock,
        ):
            cu.cleanup_old_files(upload_dir="X")

        removed_paths = [str(c.args[0]) for c in remove_mock.call_args_list]
        self.assertTrue(any(p.endswith(lock_name) for p in removed_paths))
        self.assertTrue(any(p.endswith(old_file) for p in removed_paths))

    def test_cleanup_removes_old_unlocked_files_and_dirs(self):
        import backend.utils.cleanup_utils as cu

        now = time.time()
        old_file = "orphan.mp4"
        old_dir = "orphan_dir"

        def _isdir(p):
            return str(p).endswith(old_dir)

        def _isfile(p):
            return str(p).endswith(old_file)

        with (
            patch.object(cu.os, "listdir", return_value=[old_file, old_dir]),
            patch.object(cu.os.path, "exists", return_value=True),
            patch.object(cu.os.path, "getmtime", return_value=now - (25 * 3600)),
            patch.object(cu.os.path, "isdir", side_effect=_isdir),
            patch.object(cu.os.path, "isfile", side_effect=_isfile),
            patch.object(cu.os, "remove") as remove_mock,
            patch.object(cu.shutil, "rmtree") as rmtree_mock,
        ):
            cu.cleanup_old_files(upload_dir="X")

        removed_paths = [str(c.args[0]) for c in remove_mock.call_args_list]
        rmtree_paths = [str(c.args[0]) for c in rmtree_mock.call_args_list]
        self.assertTrue(any(p.endswith(old_file) for p in removed_paths))
        self.assertTrue(any(p.endswith(old_dir) for p in rmtree_paths))
