import ast
import json
from pathlib import Path

ROOT = Path(__file__).parents[4]
API = ROOT / "apps" / "api"
REPORT = ROOT / "third_party" / "licenses" / "paddle_ocr_runtime_report.json"
PACKAGE_NAMES = {"paddleocr", "paddlepaddle-gpu"}
REQUIRED_MODELS = {
    "PP-OCRv5_mobile_det",
    "korean_PP-OCRv3_mobile_rec",
    "en_PP-OCRv4_mobile_rec",
}


def _report() -> dict:
    return json.loads(REPORT.read_text(encoding="utf-8"))


def test_runtime_report_marks_paddle_as_active_local_runtime_dependency():
    report = _report()
    assert report["schema_version"] == "1"
    assert report["status"] == "runtime-ready"
    assert report["dependency_overlay_enabled"] is False
    assert report["default_runtime_enabled"] is True
    assert report["blockers"] == []
    assert report["runtime_profile"]["dependency_file"] == "apps/api/requirements-paddle-gpu.txt"
    assert report["runtime_profile"]["worker_venv"] == "/opt/venvs/paddle"
    assert report["runtime_profile"]["cuda_required"] is True


def test_gpu_package_overlay_is_explicit():
    packages = {item["name"]: item for item in _report()["packages"]}
    assert set(packages) == PACKAGE_NAMES
    assert packages["paddleocr"]["version"] == "3.7.0"
    assert packages["paddlepaddle-gpu"]["version"] == "3.3.1"
    for package in packages.values():
        assert package["version"]
        assert package["package_source"].startswith("https://")
        assert package["license_id"] == "Apache-2.0"
        assert package["cpu_only"] is False
        assert package["transitive_dependency_status"] == "paddle-worker-requirements"


def test_models_are_runtime_ready_and_checksum_pinned():
    models = {item["model_id"]: item for item in _report()["models"]}
    assert set(models) == REQUIRED_MODELS
    for model in models.values():
        assert model["role"] in {"text_detection", "text_recognition"}
        assert model["source_url"].startswith(
            "https://paddle-model-ecology.bj.bcebos.com/"
        )
        assert len(model["sha256"]) == 64
        int(model["sha256"], 16)
        assert model["license_id"] == "Apache-2.0"
        assert model["redistribution_verified"] is True
        assert model["commercial_use_verified"] is True
        assert model["notice_obligations_verified"] is True


def test_primary_stack_is_not_blocked_by_runtime_gate():
    report = _report()
    reviews = report["approval_matrix"]
    assert {item["model_id"] for item in reviews} == REQUIRED_MODELS
    assert report["primary_stack_decision"] == "runtime-ready"
    for review in reviews:
        assert review["decision"] == "runtime-ready"
        assert review["commercial_use"] == "verified"
        assert review["redistribution"] == "verified"
        assert review["notice_obligations"] == "verified"


def test_model_delivery_remains_local_and_fail_closed():
    policy = _report()["model_delivery_policy"]
    assert policy["automatic_download"] == "forbidden"
    assert policy["network_access_at_runtime"] == "forbidden"
    assert policy["provisioning"] == "pre-provisioned-checksum-verified-assets-only"
    assert policy["missing_asset_behavior"] == "fail-closed"


def test_gpu_requirements_include_paddle_runtime():
    api_requirements = (API / "requirements.txt").read_text(encoding="utf-8").lower()
    requirements = (API / "requirements-paddle-gpu.txt").read_text(encoding="utf-8").lower()
    assert "paddleocr==" not in api_requirements
    assert "paddlepaddle-gpu==" not in api_requirements
    assert "paddleocr==3.7.0" in requirements
    assert "paddlepaddle-gpu==3.3.1" in requirements
    assert "cu126" in requirements
    assert "cu118" not in requirements
    assert "paddlepaddle==" not in requirements


def test_application_code_keeps_paddle_imports_behind_lazy_runtime_boundary():
    offenders = []
    allowed = {Path("app/infrastructure/ocr/paddle_real_adapter.py")}
    for path in (API / "app").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imports.update(
            node.module.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        )
        if imports & {"paddleocr", "paddle", "paddlepaddle"} and path.relative_to(API) not in allowed:
            offenders.append(str(path.relative_to(API)))
    assert offenders == []
