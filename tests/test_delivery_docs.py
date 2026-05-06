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
