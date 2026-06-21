import ast
import json
from pathlib import Path


ROOT = Path(__file__).parents[4]
API = ROOT / "apps" / "api"
REPORT = ROOT / "third_party" / "licenses" / "paddle_ocr_candidate_report.json"
PACKAGE_NAMES = {"paddleocr", "paddlepaddle"}
REQUIRED_MODELS = {
    "PP-OCRv5_mobile_det",
    "korean_PP-OCRv3_mobile_rec",
    "en_PP-OCRv4_mobile_rec",
}


def _report() -> dict:
    return json.loads(REPORT.read_text(encoding="utf-8"))


def test_candidate_report_is_blocked_until_package_and_model_review_is_complete():
    report = _report()
    assert report["schema_version"] == "1"
    assert report["status"] == "blocked"
    assert report["approved_for_dependency_addition"] is False
    assert report["approved_for_default_distribution"] is False
    assert report["blockers"]


def test_cpu_package_candidates_are_exact_and_have_reviewable_wheel_hashes():
    packages = {item["name"]: item for item in _report()["package_candidates"]}
    assert set(packages) == PACKAGE_NAMES
    for package in packages.values():
        assert package["version"]
        assert package["package_source"].startswith("https://pypi.org/")
        assert package["license_evidence_url"].startswith("https://")
        assert package["cpu_only"] is True
        assert package["wheel_artifacts"]
        for wheel in package["wheel_artifacts"]:
            assert wheel["filename"].endswith(".whl")
            assert len(wheel["sha256"]) == 64
            int(wheel["sha256"], 16)


def test_model_candidates_are_checksum_pinned_but_not_license_approved():
    models = {item["model_id"]: item for item in _report()["model_candidates"]}
    assert set(models) == REQUIRED_MODELS
    for model in models.values():
        assert model["role"] in {"text_detection", "text_recognition"}
        assert model["source_url"].startswith(
            "https://paddle-model-ecology.bj.bcebos.com/"
        )
        assert len(model["sha256"]) == 64
        int(model["sha256"], 16)
        assert model["license_id"] == "LicenseRef-Unclear"
        assert model["redistribution_verified"] is False
        assert model["commercial_use_verified"] is False
        assert model["notice_obligations_verified"] is False
        assert model["default_distribution"] is False


def test_only_detection_and_recognition_models_are_candidates():
    report = _report()
    assert report["excluded_model_families"] == [
        "orientation",
        "classification",
        "layout",
        "PP-Structure",
        "VLM",
    ]
    assert {item["role"] for item in report["model_candidates"]} == {
        "text_detection",
        "text_recognition",
    }


def test_automatic_model_download_is_forbidden():
    policy = _report()["model_delivery_policy"]
    assert policy["automatic_download"] == "forbidden"
    assert policy["network_access_at_runtime"] == "forbidden"
    assert policy["provisioning"] == "pre-provisioned-checksum-verified-assets-only"
    assert policy["missing_asset_behavior"] == "fail-closed"


def test_paddle_dependencies_are_not_activated_while_gate_is_blocked():
    requirements = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in (API / "requirements.txt", API / "requirements-ocr.lock")
    )
    assert all(name not in requirements for name in PACKAGE_NAMES)


def test_blocked_candidates_are_absent_from_active_sbom_license_assets_and_notice():
    licenses = ROOT / "third_party" / "licenses"
    active = "\n".join(
        (licenses / name).read_text(encoding="utf-8").lower()
        for name in (
            "parser_ocr_sbom.json",
            "parser_ocr_license_report.json",
            "ocr_model_weight_license_report.json",
            "NOTICE.parser_ocr.txt",
        )
    )
    for token in (
        "paddleocr",
        "paddlepaddle",
        "pp-ocrv5_mobile_det",
        "korean_pp-ocrv3_mobile_rec",
        "en_pp-ocrv4_mobile_rec",
    ):
        assert token not in active


def test_application_code_has_no_paddle_concrete_import():
    offenders = []
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
        if imports & {"paddleocr", "paddle", "paddlepaddle"}:
            offenders.append(str(path.relative_to(API)))
    assert offenders == []
