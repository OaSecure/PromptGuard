import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).parents[4]
REPORT = REPO_ROOT / "third_party" / "licenses" / "ocr_model_weight_license_report.json"
REQUIRED_ASSET_TYPES = {"ocr_model_weight", "language_pack", "pdf_renderer_binary", "native_library_binding"}


def _validate_asset(asset: dict) -> None:
    assert {
        "asset_type", "model_id", "model_version", "weight_source", "license_id",
        "commercial_use_compatible", "source_disclosure_required", "default_distribution",
    } <= set(asset)
    assert asset["asset_type"] in REQUIRED_ASSET_TYPES
    assert asset["license_id"] not in {"", "UNKNOWN", "LicenseRef-Unclear"}
    assert asset["commercial_use_compatible"] is True
    if asset["default_distribution"]:
        assert asset["source_disclosure_required"] is False


def test_model_weight_license_report_exists_and_has_v352_schema():
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    assert report["schema_version"] == "1"
    assert report["scope"] == "parser_ocr_runtime_assets"
    assert report["assets"]
    assert report["asset_types_in_scope"] == sorted(REQUIRED_ASSET_TYPES)
    assert report["status"] == "pdf_renderer_runtime_asset_registered"
    for asset in report["assets"]:
        _validate_asset(asset)


@pytest.mark.parametrize("asset_type", sorted(REQUIRED_ASSET_TYPES))
def test_all_runtime_asset_types_use_the_same_license_gate(asset_type):
    valid = {
        "asset_type": asset_type,
        "model_id": "synthetic-id",
        "model_version": "1",
        "weight_source": "https://example.invalid/artifact",
        "license_id": "Apache-2.0",
        "commercial_use_compatible": True,
        "source_disclosure_required": False,
        "default_distribution": True,
    }
    _validate_asset(valid)


def test_unclear_model_weight_license_is_rejected():
    invalid = {
        "asset_type": "ocr_model_weight", "model_id": "m", "model_version": "1",
        "weight_source": "unknown", "license_id": "LicenseRef-Unclear",
        "commercial_use_compatible": True, "source_disclosure_required": False,
        "default_distribution": True,
    }
    with pytest.raises(AssertionError):
        _validate_asset(invalid)

def test_source_disclosure_asset_is_rejected_from_default_distribution():
    invalid = {
        "asset_type": "language_pack", "model_id": "lang", "model_version": "1",
        "weight_source": "https://example.invalid/artifact", "license_id": "GPL-3.0",
        "commercial_use_compatible": True, "source_disclosure_required": True,
        "default_distribution": True,
    }
    with pytest.raises(AssertionError):
        _validate_asset(invalid)
