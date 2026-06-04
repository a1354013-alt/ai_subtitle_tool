from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_env_examples_exist_for_docker_delivery():
    assert (REPO_ROOT / "backend" / ".env.example").exists()
    assert (REPO_ROOT / "frontend" / ".env.example").exists()


def test_readme_no_longer_references_old_batch_storage_path():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    deployment = (REPO_ROOT / "DEPLOYMENT.md").read_text(encoding="utf-8")
    assert "backend/storage/batches" not in readme
    assert "backend/storage/batches" not in deployment


def test_delivery_docs_reference_existing_env_examples_and_dockerfiles():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    deployment = (REPO_ROOT / "DEPLOYMENT.md").read_text(encoding="utf-8")

    assert "backend/.env.example" in readme
    assert "frontend/.env.example" in readme
    assert "backend/.env.example" in deployment
    assert (REPO_ROOT / "backend" / "Dockerfile").exists()
    assert (REPO_ROOT / "frontend" / "Dockerfile").exists()


def test_delivery_docs_describe_supported_runtime_versions_and_preflight_commands():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    development = (REPO_ROOT / "DEVELOPMENT.md").read_text(encoding="utf-8")
    deployment = (REPO_ROOT / "DEPLOYMENT.md").read_text(encoding="utf-8")

    expected_python = "Python 3.11 or 3.12 is required."
    expected_version_guidance = "Recommended: Python 3.11"
    expected_node = "Node.js 20.x is required."
    expected_backend_install = "python -m pip install -r requirements.lock.txt"
    expected_frontend_install = "npm ci"
    expected_full_verify = "python scripts/verify_delivery.py --full"
    expected_prod_audit = "npm audit --omit=dev"

    for text in (readme, development, deployment):
        assert expected_python in text
        assert expected_version_guidance in text
        assert expected_node in text

    for text in (readme, development):
        assert expected_backend_install in text
        assert expected_frontend_install in text
        assert expected_full_verify in text

    assert expected_prod_audit in readme
    assert "dev dependency advisories are not production runtime risks" in readme
