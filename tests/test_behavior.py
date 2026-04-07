import asyncio
import importlib
import io
import os
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


_TMP_ROOT = Path(__file__).resolve().parent / "_tmp"
_TMP_ROOT.mkdir(parents=True, exist_ok=True)


def _make_tmpdir() -> Path:
    # 某些受限環境會拒絕刪檔/刪資料夾；測試不做自動清理，統一落在 workspace 內的忽略目錄
    d = _TMP_ROOT / uuid.uuid4().hex
    d.mkdir(parents=True, exist_ok=True)
    return d


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
