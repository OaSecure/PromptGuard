import json
import sys
from pathlib import Path

import app.models  # noqa: F401
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.db import startup
from app.db.base import Base


def repo_api_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_compose_text() -> str:
    return (repo_api_root().parents[1] / "compose.yml").read_text(encoding="utf-8")


def load_env_example_text() -> str:
    return (repo_api_root().parents[1] / ".env.example").read_text(encoding="utf-8")


def load_start_api_script() -> str:
    return (repo_api_root() / "scripts" / "start_api.sh").read_text(encoding="utf-8")


def repo_root() -> Path:
    return repo_api_root().parents[1]


def get_migration_head() -> str:
    alembic_config = Config(str(repo_api_root() / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(repo_api_root() / "alembic"))
    script = ScriptDirectory.from_config(alembic_config)
    return script.get_current_head()


def test_start_api_runner_waits_migrates_seeds_then_runs_uvicorn(monkeypatch) -> None:
    order: list[str] = []

    monkeypatch.setattr(startup, "wait_for_configured_database", lambda: order.append("wait_for_db"))
    monkeypatch.setattr(startup, "run_alembic_upgrade", lambda: order.append("alembic_upgrade"))
    monkeypatch.setattr(startup, "run_default_admin_seed", lambda: order.append("seed_default_admin"))
    monkeypatch.setattr(startup, "run_uvicorn", lambda: order.append("uvicorn"))

    startup.main()

    assert order == ["wait_for_db", "alembic_upgrade", "seed_default_admin", "uvicorn"]


def test_startup_subprocesses_run_inside_current_python_environment(monkeypatch) -> None:
    commands: list[list[str]] = []

    monkeypatch.setattr(startup, "run_checked", lambda command: commands.append(command))

    startup.run_alembic_upgrade()
    uvicorn_command = startup.build_uvicorn_command()

    assert commands == [[sys.executable, "-m", "alembic", "upgrade", "head"]]
    assert uvicorn_command[:3] == [sys.executable, "-m", "uvicorn"]
    assert "alembic" not in {commands[0][0], uvicorn_command[0]}
    assert "uvicorn" not in {commands[0][0], uvicorn_command[0]}


def test_compose_uses_startup_runner_and_v1_admin_default() -> None:
    compose_text = load_compose_text()
    env_example_text = load_env_example_text()
    start_api_script = load_start_api_script()

    assert "PROMPTGUARD_INITIAL_ADMIN_PASSWORD: ${PROMPTGUARD_INITIAL_ADMIN_PASSWORD:-1234}" in compose_text
    assert "command: /bin/sh /app/scripts/start_api.sh" in compose_text
    assert "PROMPTGUARD_INITIAL_ADMIN_PASSWORD=1234" in env_example_text
    assert "/opt/venvs/api/bin/python -m app.db.startup" in start_api_script
    assert "ACCESS_TOKEN_SECRET=" not in start_api_script
    assert "REFRESH_TOKEN_SECRET=" not in start_api_script
    assert "DATABASE_URL=" not in start_api_script


def test_compose_mounts_model_artifacts_read_only_and_documents_manifest_paths() -> None:
    compose_text = load_compose_text()
    env_example_text = load_env_example_text()

    assert "./models:/opt/promptguard/models:ro" in compose_text
    assert (
        "PROMPTGUARD_CLASSIFIER_RUNTIME_ENABLED: ${PROMPTGUARD_CLASSIFIER_RUNTIME_ENABLED:-false}"
        in compose_text
    )
    assert "PROMPTGUARD_CLASSIFIER_MANIFEST_PATH: ${PROMPTGUARD_CLASSIFIER_MANIFEST_PATH:-}" in compose_text
    assert "PROMPTGUARD_VERIFIER_RUNTIME_ENABLED: ${PROMPTGUARD_VERIFIER_RUNTIME_ENABLED:-false}" in compose_text
    assert "PROMPTGUARD_VERIFIER_MANIFEST_PATH: ${PROMPTGUARD_VERIFIER_MANIFEST_PATH:-}" in compose_text
    assert (
        "PROMPTGUARD_TORCH_WORKER_PAYLOAD_DIR: ${PROMPTGUARD_TORCH_WORKER_PAYLOAD_DIR:-/tmp/promptguard-torch-payloads}"
        in compose_text
    )
    assert (
        "PROMPTGUARD_TORCH_WORKER_PYTHON_PATH: ${PROMPTGUARD_TORCH_WORKER_PYTHON_PATH:-/opt/venvs/torch/bin/python}"
        in compose_text
    )
    assert (
        "PROMPTGUARD_TORCH_WORKER_SCRIPT_PATH: ${PROMPTGUARD_TORCH_WORKER_SCRIPT_PATH:-/app/scripts/torch_context_worker.py}"
        in compose_text
    )
    assert (
        "PROMPTGUARD_PADDLE_WORKER_PYTHON_PATH: ${PROMPTGUARD_PADDLE_WORKER_PYTHON_PATH:-/opt/venvs/paddle/bin/python}"
        in compose_text
    )
    assert (
        "PROMPTGUARD_PADDLE_WORKER_SCRIPT_PATH: ${PROMPTGUARD_PADDLE_WORKER_SCRIPT_PATH:-/app/scripts/paddle_ocr_worker.py}"
        in compose_text
    )
    assert (
        "PROMPTGUARD_TEMP_FILE_ENCRYPTION_KEY: ${PROMPTGUARD_TEMP_FILE_ENCRYPTION_KEY:-}"
        in compose_text
    )
    assert "PROMPTGUARD_TEMP_FILE_DIR: ${PROMPTGUARD_TEMP_FILE_DIR:-.promptguard-temp}" in compose_text
    assert "PROMPTGUARD_TEMP_FILE_TTL_SECONDS: ${PROMPTGUARD_TEMP_FILE_TTL_SECONDS:-900}" in compose_text
    assert "PROMPTGUARD_TEMP_FILE_MAX_BYTES: ${PROMPTGUARD_TEMP_FILE_MAX_BYTES:-1048576}" in compose_text
    assert (
        "PROMPTGUARD_CLASSIFIER_MANIFEST_PATH=/opt/promptguard/models/context_lr_roberta_active_best_f1_manifest.json"
        in env_example_text
    )
    assert (
        "PROMPTGUARD_VERIFIER_MANIFEST_PATH=/opt/promptguard/models/context_lr_roberta_active_best_f1_manifest.json"
        in env_example_text
    )
    assert "PROMPTGUARD_TORCH_WORKER_PAYLOAD_DIR=/tmp/promptguard-torch-payloads" in env_example_text
    assert "PROMPTGUARD_TORCH_WORKER_PYTHON_PATH=/opt/venvs/torch/bin/python" in env_example_text
    assert "PROMPTGUARD_TORCH_WORKER_SCRIPT_PATH=/app/scripts/torch_context_worker.py" in env_example_text
    assert "PROMPTGUARD_PADDLE_WORKER_PAYLOAD_DIR=/tmp/promptguard-paddle-payloads" in env_example_text
    assert "PROMPTGUARD_PADDLE_WORKER_PYTHON_PATH=/opt/venvs/paddle/bin/python" in env_example_text
    assert "PROMPTGUARD_PADDLE_WORKER_SCRIPT_PATH=/app/scripts/paddle_ocr_worker.py" in env_example_text


def test_compose_builds_single_api_image_with_split_worker_virtualenvs() -> None:
    compose_text = load_compose_text()
    dockerfile_text = (repo_api_root() / "Dockerfile").read_text(encoding="utf-8")

    assert "PROMPTGUARD_INSTALL_ML_RUNTIME" not in compose_text
    assert "PROMPTGUARD_INSTALL_CUDA_TORCH" not in compose_text
    assert "PROMPTGUARD_INSTALL_OCR_GPU" not in compose_text
    assert "gpus: all" in compose_text
    assert "ARG PROMPTGUARD_INSTALL_ML_RUNTIME" not in dockerfile_text
    assert "ARG PROMPTGUARD_INSTALL_CUDA_TORCH" not in dockerfile_text
    assert "ARG PROMPTGUARD_INSTALL_OCR_GPU" not in dockerfile_text
    assert "libgl1" in dockerfile_text
    assert "libglib2.0-0" in dockerfile_text
    assert "COPY requirements.txt ./" in dockerfile_text
    assert "COPY requirements-paddle-gpu.txt ./" in dockerfile_text
    assert "COPY requirements-torch-gpu.txt ./" in dockerfile_text
    assert "COPY requirements.txt requirements-paddle-gpu.txt requirements-torch-gpu.txt ./" not in dockerfile_text
    assert "python -m venv /opt/venvs/api" in dockerfile_text
    assert "python -m venv /opt/venvs/paddle" in dockerfile_text
    assert "python -m venv /opt/venvs/torch" in dockerfile_text
    assert "/opt/venvs/api/bin/python -m pip install --no-cache-dir -r requirements.txt" in dockerfile_text
    assert "/opt/venvs/paddle/bin/python -m pip install --no-cache-dir -r requirements-paddle-gpu.txt" in dockerfile_text
    assert "/opt/venvs/torch/bin/python -m pip install --no-cache-dir -r requirements-torch-gpu.txt" in dockerfile_text
    assert 'CMD ["/opt/venvs/api/bin/uvicorn"' in dockerfile_text
    assert "requirements-ml.txt" not in dockerfile_text
    assert "requirements-ml-cu128.txt" not in dockerfile_text


def test_model_artifact_directory_documents_samples_without_real_artifacts() -> None:
    model_root = repo_root() / "models"
    examples_root = model_root / "examples"
    readme_text = (model_root / "README.md").read_text(encoding="utf-8")
    lr_manifest = json.loads((examples_root / "context_lr_manifest.sample.json").read_text(encoding="utf-8"))
    verifier_manifest = json.loads(
        (examples_root / "context_roberta_verifier_manifest.sample.json").read_text(encoding="utf-8")
    )
    target_labels = json.loads((examples_root / "context_target_labels.sample.json").read_text(encoding="utf-8"))
    label_definitions = json.loads((examples_root / "context_label_definitions.sample.json").read_text(encoding="utf-8"))

    assert "./models:/opt/promptguard/models:ro" in readme_text
    assert "OASecure/promptguard-context-classifier" in readme_text
    assert "v287-20260623" in readme_text
    assert "Do not commit real model artifacts to Git" in readme_text
    assert lr_manifest["selected"]["lr_model"].endswith(".joblib")
    assert lr_manifest["selected"]["target_labels_json"] == "models/context_target_labels.sample.json"
    assert verifier_manifest["selected"]["verifier_dir"].startswith("models/")
    assert verifier_manifest["selected"]["label_definitions_json"] == "models/context_label_definitions.sample.json"
    assert verifier_manifest["selected"]["verifier_threshold_mode"] == "labelwise"
    assert set(verifier_manifest["selected"]["verifier_thresholds"]) == set(target_labels["target_labels"])
    assert target_labels["target_labels"]
    assert set(target_labels["target_labels"]) == set(label_definitions)


def test_wbs48_required_metadata_tables_exist() -> None:
    table_names = set(Base.metadata.tables)

    assert "dashboard_sessions" in table_names
    assert "event_inputs" in table_names
    assert "idempotency_keys" in table_names
    assert "audit_logs" in table_names
    assert get_migration_head() == "20260621_0012"


def test_audit_logs_schema_is_metadata_only_with_required_indexes() -> None:
    audit_logs = Base.metadata.tables["audit_logs"]
    actual_columns = set(audit_logs.columns.keys())

    assert {
        "actor_login_id",
        "action",
        "target_type",
        "target_id",
        "safe_metadata",
        "created_at",
    }.issubset(actual_columns)
    assert {
        "request_body",
        "raw_request_body",
        "raw_payload",
        "password",
        "password_hash",
        "access_token",
        "refresh_token",
        "session_token",
    }.isdisjoint(actual_columns)

    actual_indexes = {tuple(index.columns.keys()) for index in audit_logs.indexes}
    assert ("created_at",) in actual_indexes
    assert ("actor_login_id", "created_at") in actual_indexes


def test_contract_tests_do_not_depend_on_retired_pr76_combined_migration() -> None:
    migration_files = {path.name for path in (repo_api_root() / "alembic" / "versions").iterdir()}

    assert "20260601_0008_mvp_readiness_tables.py" not in migration_files
