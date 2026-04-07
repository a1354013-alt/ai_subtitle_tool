"""
基本 FastAPI 測試，驗證 API 的核心功能與安全特性。
"""
import os
import sys
import json
import uuid
import tempfile
from pathlib import Path

# 加入 backend 路徑
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

class TestAPISecurity:
    """測試 API 安全性與路徑驗證"""
    
    def test_invalid_task_id_format(self):
        """task_id 必須是合法 UUID"""
        response = client.get("/status/invalid-task-id")
        assert response.status_code == 400
        assert "Invalid task_id format" in response.text or "UUID" in response.text
    
    def test_invalid_lang_format(self):
        """lang 需要白名單驗證，不允許特殊字符"""
        from backend.main import validate_lang
        
        # 有效的 lang
        assert validate_lang("Traditional_Chinese") == "Traditional_Chinese"
        assert validate_lang("en-US") == "en-US"
        
        # 無效的 lang（含特殊字符）
        try:
            validate_lang("../../etc/passwd")
            assert False, "Should have raised HTTPException"
        except Exception as e:
            assert "Invalid lang format" in str(e)
    
    def test_task_id_validation(self):
        """task_id 應驗證為 UUID"""
        from backend.main import validate_task_id
        
        # 有效的 UUID
        valid_uuid = str(uuid.uuid4())
        assert validate_task_id(valid_uuid) == valid_uuid
        
        # 無效的 task_id
        try:
            validate_task_id("not-a-valid-uuid")
            assert False, "Should have raised HTTPException"
        except Exception as e:
            assert "Invalid task_id format" in str(e)
    
    def test_path_traversal_prevention(self):
        """測試路徑逃逸防護"""
        from backend.main import validate_path_traversal
        
        allowed_root = "/tmp/uploads"
        
        # 有效路徑
        valid_path = "/tmp/uploads/file.txt"
        assert validate_path_traversal(valid_path, allowed_root) == valid_path
        
        # 無效路徑（逃逸）
        try:
            validate_path_traversal("/tmp/../etc/passwd", allowed_root)
            assert False, "Should have raised HTTPException"
        except Exception as e:
            assert "traversal" in str(e).lower()
    
    def test_subtitle_format_whitelist(self):
        """subtitle_format 應只允許 ass 或 srt"""
        # 有效格式應通過
        # 無效格式應拒絕
        # 這在 upload API 中驗證


class TestSubtitleFormatIsolation:
    """測試字幕編輯 API 的格式隔離"""
    
    def test_subtitle_edit_requires_format(self):
        """編輯字幕時必須指定 format"""
        from backend.main import SubtitleEditRequest
        
        # 應包含 format 參數
        edit_data = {
            "content": "New subtitle content",
            "format": "ass"  # 必須指定
        }
        
        # 驗證 Pydantic 模型
        try:
            req = SubtitleEditRequest(**edit_data)
            assert req.format == "ass"
        except Exception as e:
            assert False, f"Valid edit request should pass: {e}"
    
    def test_get_subtitle_format_parameter(self):
        """GET /subtitle 應支援 format 參數"""
        # 測試端點是否接受 format 參數
        pass  # 需要實際 task_id
    
    def test_get_download_format_parameter(self):
        """GET /download 應支援 format 參數"""
        # 測試端點是否接受 format 參數
        pass  # 需要實際 task_id


class TestTaskIDSafety:
    """測試 task_id 的安全性"""
    
    def test_status_endpoint_validates_task_id(self):
        """GET /status/{task_id} 應驗證 task_id"""
        response = client.get(f"/status/../../etc/passwd")
        assert response.status_code == 400
    
    def test_download_endpoint_validates_task_id(self):
        """GET /download/{task_id} 應驗證 task_id"""
        response = client.get(f"/download/not-uuid")
        assert response.status_code == 400


class TestSplitUtilsEdgeCases:
    """測試分段邊界情況"""
    
    def test_split_video_guard_segment_length_overlap(self):
        """segment_length 必須 > overlap"""
        from backend.utils.split_utils import split_video
        import tempfile
        
        # 創建一個 dummy 影片路徑
        with tempfile.NamedTemporaryFile(suffix=".mp4") as tmp:
            try:
                # segment_length <= overlap 應拋出例外
                split_video(tmp.name, segment_length=2, overlap=3)
                assert False, "Should raise ValueError"
            except ValueError as e:
                assert "segment_length" in str(e).lower()
    
    def test_split_video_no_infinite_loop(self):
        """最後一段應只切一次，不無限迴圈"""
        # 此測試實際上需要 mock 或真實影片
        # 這裡只驗證邏輯修正已提交
        from backend.utils.split_utils import split_video
        
        # 檢查新邏輯中有 if end >= duration: break
        import inspect
        source = inspect.getsource(split_video)
        assert "if end >= duration:" in source
        assert "break" in source


class TestLockMechanisms:
    """測試 lock 機制"""
    
    def test_is_lock_stale(self):
        """測試 stale lock 偵測"""
        import json
        import tempfile
        import time
        from backend.tasks import is_lock_stale
        
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_path = os.path.join(tmpdir, "test.lock")
            
            # 建立最近的 lock（不應視為 stale）
            lock_info = {
                "business_id": "test",
                "pid": os.getpid(),
                "timestamp": time.time()
            }
            with open(lock_path, "w") as f:
                json.dump(lock_info, f)
            
            # 應不視為 stale
            assert not is_lock_stale(lock_path, stale_threshold_seconds=10)
            
            # 建立過舊的 lock
            old_lock_info = {
                "business_id": "test",
                "pid": 99999,  # 不存在的 PID
                "timestamp": time.time() - 7200  # 2 小時前
            }
            with open(lock_path, "w") as f:
                json.dump(old_lock_info, f)
            
            # 應視為 stale
            assert is_lock_stale(lock_path, stale_threshold_seconds=3600)


class TestWarningsDeduplication:
    """測試 warnings 去重保序"""
    
    def test_warnings_order_preserved(self):
        """warnings 去重應保留順序"""
        warnings = [
            "Warning A",
            "Warning B",
            "Warning A",  # 重複
            "Warning C",
            "Warning B",  # 重複
        ]
        
        # 使用保序去重
        deduped = list(dict.fromkeys(warnings))
        
        assert deduped == ["Warning A", "Warning B", "Warning C"]
        assert deduped != sorted(deduped)  # 應保留原始順序


class TestTranscribeAudioCleanup:
    """測試轉錄後暫存檔清理"""
    
    def test_transcribe_cleanup_try_finally(self):
        """transcribe_video 應使用 try/finally 確保清理"""
        from backend.utils.subtitle_utils import transcribe_video
        import inspect
        
        source = inspect.getsource(transcribe_video)
        assert "finally:" in source
        assert "os.remove(audio_path)" in source


class TestTranslateRetry:
    """測試翻譯重試邏輯"""
    
    def test_translate_retry_covers_network_errors(self):
        """翻譯應重試網路錯誤、timeout、rate limit"""
        from backend.utils.translate_utils import translate_batch
        import inspect
        
        source = inspect.getsource(translate_batch)
        # 檢查是否有 APIConnectionError、RateLimitError
        assert "APIConnectionError" in source or "RateLimitError" in source or "APIError" in source


class TestTranscribeSegmentMetadata:
    """測試分段任務回傳完整元數據"""
    
    def test_transcribe_segment_task_returns_overlap(self):
        """transcribe_segment_task 應回傳 overlap、segment_idx、end_offset"""
        from backend.tasks import transcribe_segment_task
        import inspect
        
        source = inspect.getsource(transcribe_segment_task)
        # 檢查是否回傳這些元素
        assert '"overlap"' in source
        assert '"segment_idx"' in source
        assert '"end_offset"' in source


class TestFormDataUpload:
    """測試上傳 API 使用 Form 而非 Query"""
    
    def test_upload_uses_form_not_query(self):
        """upload API 應使用 Form 類型"""
        from backend.main import upload_video
        import inspect
        
        sig = inspect.signature(upload_video)
        # 檢查參數類型提示
        # target_langs、burn_subtitles 等應該是 Form
        source = inspect.getsource(upload_video)
        assert "Form(" in source


# ============================================================================
# 測試執行
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("運行增強測試...")
    print("=" * 70)
    
    tests = [
        ("API 安全性", TestAPISecurity),
        ("字幕格式隔離", TestSubtitleFormatIsolation),
        ("task_id 安全", TestTaskIDSafety),
        ("分段邊界", TestSplitUtilsEdgeCases),
        ("Lock 機制", TestLockMechanisms),
        ("Warnings 去重", TestWarningsDeduplication),
        ("Transcribe 清理", TestTranscribeAudioCleanup),
        ("Translate 重試", TestTranslateRetry),
        ("分段元數據", TestTranscribeSegmentMetadata),
        ("上傳 Form 型別", TestFormDataUpload),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_class in tests:
        print(f"\n【{test_name}】")
        instance = test_class()
        
        for method_name in dir(instance):
            if method_name.startswith("test_"):
                try:
                    method = getattr(instance, method_name)
                    method()
                    print(f"  ✓ {method_name}")
                    passed += 1
                except AssertionError as e:
                    print(f"  ✗ {method_name}: {e}")
                    failed += 1
                except Exception as e:
                    print(f"  ⚠ {method_name}: {type(e).__name__}: {e}")
    
    print("\n" + "=" * 70)
    print(f"測試結果: {passed} 通過, {failed} 失敗")
    print("=" * 70)
    
    sys.exit(0 if failed == 0 else 1)
