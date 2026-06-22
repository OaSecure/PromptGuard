import ast
import json
from pathlib import Path

ROOT = Path(__file__).parents[4]
API = ROOT / "apps" / "api"
REPORT = ROOT / "third_party" / "licenses" / "tesseract_ocr_candidate_report.json"


def _report() -> dict:
    return json.loads(REPORT.read_text(encoding="utf-8"))


def test_candidate_stays_blocked_until_artifacts_and_native_dependencies_are_reviewed():
    report = _report()
    assert report["schema_version"] == "1"
    assert report["scope"] == "development_contract_pr10_b3_a"
    assert report["status"] == "blocked"
    assert report["approved_for_dependency_addition"] is False
    assert report["approved_for_default_distribution"] is False
    assert report["blockers"]


def test_engine_and_optional_wrapper_are_exact_and_permissively_licensed():
    report = _report()
    engine = report["engine_candidate"]
    assert engine["name"] == "tesseract"
    assert engine["version"] == "5.5.2"
    assert engine["license_id"] == "Apache-2.0"
    assert engine["official_release_url"].startswith("https://github.com/tesseract-ocr/")
    wrapper = report["python_wrapper_candidate"]
    assert wrapper["name"] == "pytesseract"
    assert wrapper["version"] == "0.3.13"
    assert wrapper["license_id"] == "Apache-2.0"
    assert wrapper["relationship"] == "optional-subprocess-wrapper"


def test_korean_and_english_traineddata_have_separate_license_evidence():
    models = {item["language"]: item for item in _report()["traineddata_candidates"]}
    assert set(models) == {"kor", "eng"}
    for language, model in models.items():
        assert model["filename"] == f"{language}.traineddata"
        assert model["repository"] == "tesseract-ocr/tessdata"
        assert len(model["repository_commit"]) == 40
        assert model["license_id"] == "Apache-2.0"
        assert model["commercial_use_verified"] is True
        assert model["redistribution_verified"] is True
        assert model["sha256_status"] == "artifact-inspection-required"
        assert model["default_distribution"] is False


def test_native_dependency_and_platform_provenance_remain_blockers():
    report = _report()
    native = report["native_dependency_review"]
    assert native["required"] == ["Leptonica"]
    assert "libpng" in native["optional_or_build_selected"]
    assert "libjpeg" in native["optional_or_build_selected"]
    assert native["status"] == "blocked-platform-artifact-inventory-required"
    platforms = report["platform_delivery"]
    assert platforms["linux"]["status"] == "distribution-package-pin-required"
    assert platforms["windows"]["status"] == "official-project-binary-unavailable"


def test_offline_policy_forbids_runtime_download_and_network():
    policy = _report()["offline_runtime_policy"]
    assert policy == {
        "binary_path": "explicit-local-path-only",
        "tessdata_path": "explicit-local-path-only",
        "automatic_download": "forbidden",
        "runtime_network": "forbidden",
        "missing_artifact": "fail-closed",
        "checksum_mismatch": "fail-before-execution",
    }


def test_blocked_candidate_is_absent_from_requirements_active_artifacts_and_app_imports():
    requirement_text = "\n".join(
        path.read_text(encoding="utf-8").lower() for path in (API / "requirements.txt", API / "requirements-ocr.lock")
    )
    assert "pytesseract" not in requirement_text
    active = "\n".join(
        (ROOT / "third_party" / "licenses" / name).read_text(encoding="utf-8").lower()
        for name in (
            "parser_ocr_sbom.json",
            "parser_ocr_license_report.json",
            "ocr_model_weight_license_report.json",
            "NOTICE.parser_ocr.txt",
        )
    )
    assert "tesseract" not in active
    offenders = []
    for path in (API / "app").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = {
            alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names
        }
        imports.update(
            node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
        )
        if imports & {"pytesseract", "tesserocr"}:
            offenders.append(str(path.relative_to(API)))
    assert offenders == []
