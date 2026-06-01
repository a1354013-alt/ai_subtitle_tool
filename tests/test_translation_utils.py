import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.utils.translate_utils import is_translation_request, should_translate, translation_targets_requested


def test_is_translation_request_false_for_original_source_auto():
    assert not is_translation_request("Original", "Auto")
    assert not is_translation_request("Source", "Auto")
    assert not is_translation_request("Auto", "Auto")


def test_is_translation_request_false_for_same_language():
    assert not is_translation_request("English", "English")
    assert not is_translation_request("english", "English")


def test_should_translate_only_with_openai_and_translate_language():
    assert should_translate("English", "Auto", True)
    assert not should_translate("English", "Auto", False)
    assert not should_translate("Original", "Auto", True)


def test_translation_targets_requested_checks_each_language():
    assert not translation_targets_requested(["Original"], "Auto")
    assert translation_targets_requested(["Traditional Chinese"], "Auto")
    assert translation_targets_requested(["Original", "Traditional Chinese"], "Auto")


def test_finalize_pipeline_skips_translate_segments_for_original_language(monkeypatch, tmp_path):
    import backend.tasks as tasks
    import backend.utils.translate_utils as translate_utils

    monkeypatch.setattr(tasks.settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(tasks.settings, "TESTING", False)

    translate_called = {"called": False}

    def fake_translate_segments(*args, **kwargs):
        translate_called["called"] = True
        raise AssertionError("translate_segments should not be called for Original target language")

    import backend.utils.split_utils as split_utils

    monkeypatch.setattr(translate_utils, "translate_segments", fake_translate_segments)
    monkeypatch.setattr(tasks, "prepare_segment_results_for_merge", lambda results: results)
    monkeypatch.setattr(split_utils, "merge_segments_subtitles", lambda results: results)

    def fake_generate_bilingual_srt(segments, translated_texts, output_path):
        Path(output_path).write_text("ok")
        return output_path

    monkeypatch.setattr(translate_utils, "generate_bilingual_srt", fake_generate_bilingual_srt)

    class DummyStorage:
        def upload_file(self, *args, **kwargs):
            return None

    monkeypatch.setattr(tasks, "get_storage_backend", lambda: DummyStorage())

    video_path = tmp_path / "input.mp4"
    video_path.write_bytes(b"dummy content")

    result = tasks.finalize_pipeline(
        [SimpleNamespace(text="hello", start=0.0, end=1.0)],
        str(video_path),
        {
            "business_id": "task1",
            "target_langs": ["Original"],
            "subtitle_format": "srt",
            "burn_subtitles": False,
        },
    )

    assert result["translations"][0]["translated"] is False
    assert translate_called["called"] is False


def test_finalize_pipeline_rejects_translation_target_without_openai_key(monkeypatch, tmp_path):
    import backend.tasks as tasks
    import backend.utils.split_utils as split_utils
    import backend.utils.translate_utils as translate_utils

    monkeypatch.setattr(tasks.settings, "OPENAI_API_KEY", "")

    translate_called = {"called": False}

    def fake_translate_segments(*args, **kwargs):
        translate_called["called"] = True
        raise AssertionError("translate_segments should not be called without OPENAI_API_KEY")

    monkeypatch.setattr(translate_utils, "translate_segments", fake_translate_segments)
    monkeypatch.setattr(tasks, "prepare_segment_results_for_merge", lambda results: results)
    monkeypatch.setattr(split_utils, "merge_segments_subtitles", lambda results: results)

    video_path = tmp_path / "input.mp4"
    video_path.write_bytes(b"dummy content")

    with pytest.raises(ValueError, match="OPENAI_API_KEY is required when translation targets are requested"):
        tasks.finalize_pipeline(
            [SimpleNamespace(text="hello", start=0.0, end=1.0)],
            str(video_path),
            {
                "business_id": "task1",
                "target_langs": ["Traditional Chinese"],
                "subtitle_format": "srt",
                "burn_subtitles": False,
            },
        )

    assert translate_called["called"] is False
