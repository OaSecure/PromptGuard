import importlib.metadata
import json
from pathlib import Path


REPO_ROOT = Path(__file__).parents[4]
REQUIREMENTS = REPO_ROOT / "apps" / "api" / "requirements.txt"
LICENSE_ROOT = REPO_ROOT / "third_party" / "licenses"
SBOM = LICENSE_ROOT / "parser_ocr_sbom.json"
LICENSE_REPORT = LICENSE_ROOT / "parser_ocr_license_report.json"
NOTICE = LICENSE_ROOT / "NOTICE.parser_ocr.txt"
PYPDF_VERSION = "6.13.3"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_pypdf_exact_version_matches_dependency_and_artifacts():
    assert f"pypdf=={PYPDF_VERSION}" in REQUIREMENTS.read_text(encoding="utf-8").splitlines()
    sbom_component = _json(SBOM)["components"][0]
    license_decision = _json(LICENSE_REPORT)["decisions"][0]
    assert (sbom_component["name"], sbom_component["version"]) == ("pypdf", PYPDF_VERSION)
    assert (license_decision["name"], license_decision["version"]) == ("pypdf", PYPDF_VERSION)


def test_pypdf_import_smoke_and_runtime_version():
    import pypdf

    assert pypdf.__version__ == PYPDF_VERSION
    assert importlib.metadata.version("pypdf") == PYPDF_VERSION


def test_pypdf_license_is_allowed_by_parser_policy():
    report = _json(LICENSE_REPORT)
    decision = report["decisions"][0]
    assert decision == {
        "decision": "allow",
        "denial_reason": None,
        "license_id": "BSD-3-Clause",
        "name": "pypdf",
        "notice_license_preservation_required": True,
        "reason": "permissive_license",
        "source_disclosure_required": False,
        "source_disclosure_risk": False,
        "version": PYPDF_VERSION,
    }


def test_sbom_records_direct_and_transitive_dependency_resolution():
    component = _json(SBOM)["components"][0]
    assert component["dependency_type"] == "direct"
    assert component["dependency_path"] == ["PromptGuard", f"pypdf=={PYPDF_VERSION}"]
    assert component["transitive_dependencies"] == []
    assert component["transitive_dependency_status"] == "none_for_default_install_on_python_3_14"


def test_license_artifacts_have_only_required_deterministic_fields():
    sbom = _json(SBOM)
    report = _json(LICENSE_REPORT)
    assert list(sbom) == ["components", "schema_version", "scope"]
    assert list(sbom["components"][0]) == [
        "dependency_path", "dependency_type", "license_id", "name", "package_source",
        "transitive_dependencies", "transitive_dependency_status", "version",
    ]
    assert list(report) == ["decisions", "ocr_model_weights", "schema_version", "scope"]
    assert sbom["schema_version"] == "2"
    assert report["schema_version"] == "2"
    assert report["ocr_model_weights"] == {
        "reason": "no_ocr_model_dependency_in_scope",
        "status": "not_applicable",
    }


def test_notice_contains_pinned_component_and_required_attribution():
    notice = NOTICE.read_text(encoding="utf-8")
    assert "Component: pypdf" in notice
    assert f"Version: {PYPDF_VERSION}" in notice
    assert "BSD-3-Clause" in notice
    assert "Copyright (c) 2006-2008, Mathieu Fenniak" in notice


def test_forbidden_pdf_and_ocr_stacks_are_absent_from_default_dependencies():
    requirements = {
        line.split("==", 1)[0].lower()
        for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    }
    forbidden = {
        "pymupdf", "fitz", "mupdf", "ghostscript", "poppler", "pdf2image",
        "pypdfium2", "paddleocr", "pytesseract",
    }
    assert requirements.isdisjoint(forbidden)


def test_pdf_adapter_uses_pinned_parser_without_ocr_or_renderer_dependencies():
    source = (REPO_ROOT / "apps" / "api" / "app" / "parser" / "adapters" / "pdf_foundation.py").read_text(encoding="utf-8")
    assert "from pypdf import PdfReader" in source
    assert "PARSER_NOT_IMPLEMENTED" not in source
    for forbidden in ("pypdfium2", "paddleocr", "pytesseract"):
        assert forbidden not in source.lower()
