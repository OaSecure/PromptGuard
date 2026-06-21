import ast
import json
from pathlib import Path


ROOT = Path(__file__).parents[4]
API = ROOT / "apps" / "api"
LICENSES = ROOT / "third_party" / "licenses"
VERSION = "5.10.1"
PDFIUM_VERSION = "151.0.7891.0"
WIN_AMD64_SHA256 = "58da5b51fb7884c7d21a05062ab13edb011d1a08dfd9694f3d5d685df62796b9"


def _json(name):
    return json.loads((LICENSES / name).read_text(encoding="utf-8"))


def test_pdfium_dependency_is_pinned_and_locked_with_artifact_hash():
    requirements = (API / "requirements.txt").read_text(encoding="utf-8").splitlines()
    lock = (API / "requirements-ocr.lock").read_text(encoding="utf-8")
    assert f"pypdfium2=={VERSION}" in requirements
    assert f"pypdfium2=={VERSION}" in lock
    assert WIN_AMD64_SHA256 in lock


def test_sbom_records_pypdfium2_and_bundled_pdfium_binary():
    components = {item["name"]: item for item in _json("parser_ocr_sbom.json")["components"]}
    package = components["pypdfium2"]
    assert package["version"] == VERSION
    assert package["package_source"] == "PyPI"
    assert package["dependency_path"] == ["PromptGuard", f"pypdfium2=={VERSION}"]
    assert package["artifact_sha256"]["win_amd64"] == WIN_AMD64_SHA256
    binary = components["PDFium"]
    assert binary["version"] == PDFIUM_VERSION
    assert binary["bundled_by"] == f"pypdfium2=={VERSION}"
    assert set(binary["bundled_license_inventory"]) >= {
        "abseil", "agg23", "fast_float", "freetype", "icu", "lcms",
        "libjpeg-turbo", "libopenjpeg", "libpng", "libtiff", "zlib",
    }
    assert not any(
        token in json.dumps(binary).lower()
        for token in ("agpl", "sspl", "commercial-only", "license-ref-unclear")
    )


def test_license_report_allows_package_and_binary_without_source_disclosure():
    decisions = {item["name"]: item for item in _json("parser_ocr_license_report.json")["decisions"]}
    for name in ("pypdfium2", "PDFium"):
        assert decisions[name]["decision"] == "allow"
        assert decisions[name]["denial_reason"] is None
        assert decisions[name]["source_disclosure_risk"] is False


def test_pdfium_binary_is_registered_as_runtime_asset_and_notice_exists():
    assets = _json("ocr_model_weight_license_report.json")["assets"]
    asset = next(item for item in assets if item["asset_type"] == "pdf_renderer_binary")
    assert asset["model_id"] == "pdfium"
    assert asset["model_version"] == PDFIUM_VERSION
    assert asset["license_id"] == "BSD-3-Clause"
    assert asset["commercial_use_compatible"] is True
    assert asset["source_disclosure_required"] is False
    notice = (LICENSES / "NOTICE.parser_ocr.txt").read_text(encoding="utf-8")
    assert f"Component: pypdfium2\nVersion: {VERSION}" in notice
    assert f"Component: PDFium\nVersion: {PDFIUM_VERSION}" in notice


def test_concrete_pdfium_import_is_confined_to_renderer_implementation():
    offenders = []
    for path in (API / "app").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = {
            alias.name.split(".")[0]
            for node in ast.walk(tree) if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported.update(
            node.module.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        )
        if "pypdfium2" in imported and path.name != "pdfium_renderer.py":
            offenders.append(path)
    assert offenders == []


def test_renderer_has_no_forbidden_layer_imports():
    path = API / "app" / "infrastructure" / "pdf" / "pdfium_renderer.py"
    source = path.read_text(encoding="utf-8").lower()
    for forbidden in (
        "eventstorage", "app.events", "app.policy", "app.scanner", "app.normalization",
        "app.ml", "pymupdf", "fitz", "mupdf", "poppler", "ghostscript", "pdf2image",
    ):
        assert forbidden not in source
