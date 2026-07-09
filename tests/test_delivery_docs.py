from pathlib import Path
import json


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_env_examples_exist_for_docker_delivery():
    assert (REPO_ROOT / "backend" / ".env.example").exists()
    assert (REPO_ROOT / "frontend" / ".env.example").exists()


def test_backend_env_example_allows_f5_frontend_origin():
    env_example = (REPO_ROOT / "backend" / ".env.example").read_text(encoding="utf-8")
    cors_line = next(line for line in env_example.splitlines() if line.startswith("CORS_ORIGINS="))
    origins = cors_line.split("=", 1)[1].split(",")

    assert "http://127.0.0.1:5173" in origins
    assert "http://localhost:5173" in origins
    assert "http://127.0.0.1:3000" in origins
    assert "http://localhost:3000" in origins


def test_start_dev_normalizes_backend_cors_for_f5_origin():
    start_dev = (REPO_ROOT / "scripts" / "start-dev.ps1").read_text(encoding="utf-8")

    assert "Ensure-BackendCorsOrigins" in start_dev
    assert "http://127.0.0.1:5173" in start_dev


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


def test_vscode_f5_development_files_are_tracked_and_wired():
    expected_files = [
        ".vscode/launch.json",
        ".vscode/tasks.json",
        ".vscode/extensions.json",
        "scripts/dev_start.py",
        "scripts/dev_bootstrap.py",
        "scripts/start-dev.cmd",
        "scripts/start-dev.ps1",
        "scripts/stop-dev.ps1",
        "scripts/stop-dev.cmd",
    ]
    for relative_path in expected_files:
        assert (REPO_ROOT / relative_path).exists(), relative_path

    launch = json.loads((REPO_ROOT / ".vscode" / "launch.json").read_text(encoding="utf-8"))
    assert launch["configurations"][0]["name"] == "Run Full Stack Dev"
    assert launch["configurations"][0]["program"].endswith("/scripts/dev_start.py")

    tasks = json.loads((REPO_ROOT / ".vscode" / "tasks.json").read_text(encoding="utf-8"))
    stop_task = next(task for task in tasks["tasks"] if task["label"] == "dev:stop")
    assert stop_task["command"].endswith("/scripts/stop-dev.cmd")

    extensions = json.loads((REPO_ROOT / ".vscode" / "extensions.json").read_text(encoding="utf-8"))
    for extension in ("ms-python.python", "ms-python.vscode-pylance", "Vue.volar", "dbaeumer.vscode-eslint"):
        assert extension in extensions["recommendations"]


def test_gitignore_preserves_tracked_vscode_development_files():
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".vscode/*" in gitignore
    assert "!.vscode/launch.json" in gitignore
    assert "!.vscode/tasks.json" in gitignore
    assert "!.vscode/extensions.json" in gitignore
