import json
from pathlib import Path

import pytest

from app.privacy.event_serializer import EventWriteProjection


REPO_ROOT = Path(__file__).parents[4]
LICENSE_ROOT = REPO_ROOT / "third_party" / "licenses"
REQUIREMENTS = REPO_ROOT / "apps" / "api" / "requirements.txt"
REQUIRED_ARTIFACTS = {
    "parser_ocr_sbom.json",
    "parser_ocr_license_report.json",
    "ocr_model_weight_license_report.json",
    "NOTICE.parser_ocr.txt",
}
PARSER_OCR_PACKAGES = {"pypdf", "pypdfium2", "paddleocr", "paddlepaddle", "pytesseract"}
FORBIDDEN_DEPENDENCIES = {
    "pymupdf", "fitz", "mupdf", "ghostscript", "poppler", "pdf2image",
    "google-cloud-vision", "azure-ai-vision-imageanalysis", "boto3-textract",
}
FORBIDDEN_LICENSES = {
    "GPL-2.0", "GPL-3.0", "LGPL-2.1", "LGPL-3.0", "AGPL-3.0", "SSPL-1.0",
    "Commercial-only", "LicenseRef-Unclear",
}


def _json(name: str) -> dict:
    return json.loads((LICENSE_ROOT / name).read_text(encoding="utf-8"))


def _pinned_requirements() -> dict[str, str]:
    result = {}
    for raw_line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, version = line.partition("==")
        if separator:
            result[name.lower()] = version
    return result


def _validate_decision(decision: dict) -> None:
    required = {"name", "version", "decision", "denial_reason", "source_disclosure_risk"}
    assert required <= set(decision)
    assert decision["license_id"] not in FORBIDDEN_LICENSES
    assert decision["decision"] == "allow"
    assert decision["denial_reason"] is None
    assert decision["source_disclosure_risk"] is False


def test_all_v352_parser_ocr_license_artifacts_exist():
    assert REQUIRED_ARTIFACTS <= {path.name for path in LICENSE_ROOT.iterdir() if path.is_file()}


def test_sbom_and_license_report_have_required_component_fields():
    sbom = _json("parser_ocr_sbom.json")
    report = _json("parser_ocr_license_report.json")
    assert sbom["schema_version"] == "2"
    assert report["schema_version"] == "2"
    assert sbom["components"]
    assert report["decisions"]
    for component in sbom["components"]:
        assert {"name", "version", "package_source", "license_id", "dependency_path"} <= set(component)
        assert component["license_id"] not in FORBIDDEN_LICENSES
    for decision in report["decisions"]:
        _validate_decision(decision)


def test_parser_ocr_requirements_are_exactly_pinned_and_match_artifacts():
    requirements = _pinned_requirements()
    artifact_versions = {
        component["name"].lower(): component["version"]
        for component in _json("parser_ocr_sbom.json")["components"]
        if component["dependency_type"] == "direct"
    }
    parser_requirements = PARSER_OCR_PACKAGES & set(requirements)
    assert parser_requirements
    for name in parser_requirements:
        assert artifact_versions[name] == requirements[name]
    assert set(artifact_versions) <= parser_requirements


def test_forbidden_dependencies_and_cloud_ocr_are_absent():
    requirements = set(_pinned_requirements())
    assert requirements.isdisjoint(FORBIDDEN_DEPENDENCIES)
    serialized = json.dumps(
        [_json("parser_ocr_sbom.json"), _json("parser_ocr_license_report.json")]
    ).lower()
    for forbidden in FORBIDDEN_DEPENDENCIES:
        assert forbidden not in serialized


@pytest.mark.parametrize("license_id", sorted(FORBIDDEN_LICENSES))
def test_forbidden_or_unclear_license_decision_is_rejected(license_id):
    decision = {
        "name": "synthetic-component", "version": "1", "license_id": license_id,
        "decision": "allow", "denial_reason": None, "source_disclosure_risk": False,
    }
    with pytest.raises(AssertionError):
        _validate_decision(decision)


def test_notice_has_structure_for_permissive_notices_and_attribution():
    notice = (LICENSE_ROOT / "NOTICE.parser_ocr.txt").read_text(encoding="utf-8")
    assert "Parser/OCR Third-Party Notices" in notice
    assert "Component:" in notice
    assert "License:" in notice
    assert "Source:" in notice
    assert "Required attribution:" in notice


def test_license_artifacts_and_runtime_refs_cannot_enter_event_storage_projection():
    persisted_fields = set(EventWriteProjection.model_fields)
    forbidden_fields = {
        "license_artifact", "license_report", "sbom", "notice", "dependency_path",
        "file_ref", "local_runtime_ref", "ocr_text", "extracted_text", "image_bytes",
        "image_base64", "raw_exception",
    }
    assert persisted_fields.isdisjoint(forbidden_fields)
    serialized_artifacts = "\n".join(
        (LICENSE_ROOT / name).read_text(encoding="utf-8")
        for name in REQUIRED_ARTIFACTS
    ).lower()
    for forbidden in (
        "file_ref", "local_runtime_ref", "ocr_text", "extracted_text",
        "original_filename", "image_bytes", "image_base64", "raw_exception",
    ):
        assert forbidden not in serialized_artifacts


def test_runtime_license_metadata_allowlist_is_narrow():
    allowed = {
        "component_name", "component_version", "license_id", "engine_id",
        "model_id", "model_version",
    }
    assert allowed.isdisjoint(EventWriteProjection.model_fields)
