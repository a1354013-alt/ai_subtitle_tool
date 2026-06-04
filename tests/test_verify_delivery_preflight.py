from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def _load_script_module(module_name: str, relative_path: str):
    module_path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


verify_delivery = _load_script_module("test_verify_delivery_script", "scripts/verify_delivery.py")
runtime_requirements = _load_script_module("test_runtime_requirements", "scripts/runtime_requirements.py")


def test_backend_dependency_preflight_passes_when_required_modules_exist(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(verify_delivery.importlib.util, "find_spec", lambda _name: object())
    verify_delivery._verify_backend_dependency_preflight()


def test_backend_dependency_preflight_reports_missing_celery(monkeypatch: pytest.MonkeyPatch):
    def fake_find_spec(name: str):
        return None if name == "celery" else object()

    monkeypatch.setattr(verify_delivery.importlib.util, "find_spec", fake_find_spec)

    with pytest.raises(verify_delivery.VerificationError) as exc_info:
        verify_delivery._verify_backend_dependency_preflight()

    assert exc_info.value.exit_code == verify_delivery.EXIT_BACKEND_DEPENDENCY_ERROR
    message = str(exc_info.value)
    assert "[backend-preflight]" in message
    assert "Missing backend dependencies: celery" in message
    assert "python -m pip install -r requirements.lock.txt" in message


@pytest.mark.parametrize("version", [(3, 11, 0), (3, 12, 7)])
def test_supported_python_versions_are_allowed(version: tuple[int, int, int]):
    assert runtime_requirements.is_supported_python_version(version) is True


@pytest.mark.parametrize("version", [(3, 10, 14), (3, 13, 0)])
def test_unsupported_python_versions_are_rejected(version: tuple[int, int, int]):
    assert runtime_requirements.is_supported_python_version(version) is False
    message = runtime_requirements.python_version_error_message(version)
    assert "Python 3.11 or 3.12 is required." in message
    assert f"Current version: {version[0]}.{version[1]}.{version[2]}" in message
