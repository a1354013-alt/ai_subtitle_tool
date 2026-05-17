from __future__ import annotations

import importlib.util
import sys
import zipfile
from pathlib import Path


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


make_release_zip = _load_script_module("test_make_release_zip", "scripts/make_release_zip.py")
verify_release_zip = _load_script_module("test_verify_release_zip", "scripts/verify_release_zip.py")


def test_build_release_zip_supports_repo_relative_output(tmp_path: Path):
    out_path = REPO_ROOT / "release-test.zip"
    try:
        make_release_zip.build_release_zip(REPO_ROOT, out_path)
        assert out_path.exists()
        make_release_zip._assert_release_zip_clean(out_path)
    finally:
        out_path.unlink(missing_ok=True)


def test_build_release_zip_supports_absolute_output_outside_repo(tmp_path: Path):
    out_path = tmp_path / "release-outside.zip"
    make_release_zip.build_release_zip(REPO_ROOT, out_path)
    assert out_path.exists()
    make_release_zip._assert_release_zip_clean(out_path)
    verify_release_zip.main([str(out_path)])


def test_release_zip_excludes_sensitive_and_generated_content(tmp_path: Path):
    out_path = tmp_path / "release-check.zip"
    make_release_zip.build_release_zip(REPO_ROOT, out_path)

    with zipfile.ZipFile(out_path, "r") as archive:
        names = set(archive.namelist())

    assert ".env" not in names
    assert "frontend/.env" not in names
    assert "backend/.env" not in names
    assert not any(name.startswith("node_modules/") or "/node_modules/" in name for name in names)
    assert not any(name.startswith("uploads/") or "/uploads/" in name for name in names)
    assert not any(name.startswith("outputs/") or "/outputs/" in name for name in names)
    assert not any(name == "frontend/dist" or name.startswith("frontend/dist/") for name in names)
    assert "release.zip" not in names
    assert "release-check.zip" not in names
