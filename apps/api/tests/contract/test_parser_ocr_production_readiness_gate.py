import json
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

import pytest
from app.parser.readiness import REQUIRED_ARTIFACTS, validate_parser_ocr_readiness

ROOT = Path(__file__).parents[4]
LICENSES = ROOT / "third_party" / "licenses"


def _inventory() -> dict[str, object]:
    inventory: dict[str, object] = {}
    for name in REQUIRED_ARTIFACTS:
        path = LICENSES / name
        inventory[name] = path.read_text(encoding="utf-8")
        if path.suffix == ".json":
            inventory[name] = json.loads(inventory[name])
    return inventory


def test_current_required_artifact_inventory_is_exact_and_fail_closed():
    expected = {
        "parser_ocr_sbom.json",
        "parser_ocr_license_report.json",
        "ocr_model_weight_license_report.json",
        "NOTICE.parser_ocr.txt",
        "paddle_ocr_runtime_report.json",
        "tesseract_ocr_candidate_report.json",
        "tesseract_isolated_validation_evidence.json",
    }

    assert set(REQUIRED_ARTIFACTS) == expected
    assert {path.name for path in LICENSES.iterdir() if path.is_file()} == expected
    result = validate_parser_ocr_readiness(_inventory())
    assert result.ready is False
    assert set(result.reason_codes) == {
        "TESSERACT_CANDIDATE_NOT_APPROVED",
        "TESSERACT_EVIDENCE_NOT_APPROVED",
    }


def test_active_sbom_license_and_model_weight_identifiers_are_consistent():
    inventory = _inventory()
    result = validate_parser_ocr_readiness(inventory)

    assert "ACTIVE_COMPONENT_MISMATCH" not in result.reason_codes
    assert "MODEL_ASSET_MISMATCH" not in result.reason_codes
    assert "NOTICE_COMPONENT_MISSING" not in result.reason_codes


@pytest.mark.parametrize("missing", REQUIRED_ARTIFACTS)
def test_missing_required_artifact_fails_closed(missing):
    inventory = _inventory()
    del inventory[missing]

    result = validate_parser_ocr_readiness(inventory)

    assert result.ready is False
    assert "REQUIRED_ARTIFACT_MISSING" in result.reason_codes


@pytest.mark.parametrize("field", ["name", "version", "license_id"])
def test_empty_component_identifiers_fail_closed(field):
    inventory = _inventory()
    inventory["parser_ocr_sbom.json"]["components"][0][field] = ""

    result = validate_parser_ocr_readiness(inventory)

    assert "ACTIVE_COMPONENT_INVALID" in result.reason_codes


@pytest.mark.parametrize("license_id", ["LicenseRef-Unknown", "GPL-3.0", "AGPL-3.0", "commercial-only"])
def test_unknown_or_forbidden_active_license_fails_closed(license_id):
    inventory = _inventory()
    inventory["parser_ocr_license_report.json"]["decisions"][0]["license_id"] = license_id

    result = validate_parser_ocr_readiness(inventory)

    assert "ACTIVE_LICENSE_FORBIDDEN" in result.reason_codes


@pytest.mark.parametrize("field", ["model_id", "model_version", "license_id", "weight_source"])
def test_unclear_or_empty_model_asset_identity_fails_closed(field):
    inventory = _inventory()
    inventory["ocr_model_weight_license_report.json"]["assets"][0][field] = ""

    result = validate_parser_ocr_readiness(inventory)

    assert "MODEL_ASSET_INVALID" in result.reason_codes


def test_sbom_component_missing_from_license_report_fails_closed():
    inventory = _inventory()
    inventory["parser_ocr_license_report.json"]["decisions"].pop()

    result = validate_parser_ocr_readiness(inventory)

    assert "ACTIVE_COMPONENT_MISMATCH" in result.reason_codes


def test_disabled_paddle_runtime_report_fails_closed():
    inventory = _inventory()
    paddle = inventory["paddle_ocr_runtime_report.json"]
    paddle["status"] = "disabled"
    paddle["dependency_overlay_enabled"] = False
    paddle["default_runtime_enabled"] = False

    result = validate_parser_ocr_readiness(inventory)

    assert result.ready is False
    assert "PADDLE_RUNTIME_NOT_READY" in result.reason_codes


@pytest.mark.parametrize(
    ("artifact", "mutation"),
    [
        ("parser_ocr_sbom.json", lambda value: value.update({"unknown": {"raw": "PRIVATE"}})),
        ("parser_ocr_sbom.json", lambda value: value.update({"components": "not-a-list"})),
        ("parser_ocr_license_report.json", lambda value: value.update({"decisions": {"bad": "type"}})),
    ],
)
def test_unknown_field_or_wrong_schema_type_fails_closed(artifact, mutation):
    inventory = _inventory()
    mutation(inventory[artifact])

    result = validate_parser_ocr_readiness(inventory)

    assert result.ready is False
    assert "ARTIFACT_SCHEMA_INVALID" in result.reason_codes


def test_result_exposes_only_readiness_and_reason_codes_not_artifact_content():
    inventory = _inventory()
    sensitive = (
        "PRIVATE_RAW_BYTES",
        "/PRIVATE_TEMP_PATH",
        "PRIVATE_ORIGINAL_FILENAME",
        "PRIVATE_OCR_TEXT",
        "PRIVATE_STDOUT",
        "PRIVATE_STDERR",
        "PRIVATE_RAW_EXCEPTION",
    )
    inventory["parser_ocr_sbom.json"]["unknown"] = list(sensitive)

    result = validate_parser_ocr_readiness(inventory)
    serialized = json.dumps(asdict(result), sort_keys=True)

    assert set(asdict(result)) == {"ready", "reason_codes"}
    assert all(value not in serialized for value in sensitive)
    assert all(value not in str(result) for value in sensitive)


def test_validator_does_not_mutate_artifact_inventory():
    inventory = _inventory()
    original = deepcopy(inventory)

    validate_parser_ocr_readiness(inventory)

    assert inventory == original


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("dependency_path", ["pypdf", {"raw_file_path": "/PRIVATE_TEMP_PATH"}]),
        ("transitive_dependencies", [{"raw_ocr_text": "PRIVATE_OCR_TEXT"}]),
        ("bundled_license_inventory", {"runtime_ref": "PRIVATE_RUNTIME_REF"}),
    ],
)
def test_malformed_nested_component_fields_fail_closed_without_leaking_values(field, value):
    inventory = _inventory()
    inventory["parser_ocr_sbom.json"]["components"][0][field] = value

    result = validate_parser_ocr_readiness(inventory)
    serialized = json.dumps(asdict(result), sort_keys=True)

    assert result.ready is False
    assert "ACTIVE_COMPONENT_INVALID" in result.reason_codes
    assert "/PRIVATE_TEMP_PATH" not in serialized
    assert "PRIVATE_OCR_TEXT" not in serialized
    assert "PRIVATE_RUNTIME_REF" not in serialized


def test_model_weight_source_must_match_active_component_source():
    inventory = _inventory()
    inventory["ocr_model_weight_license_report.json"]["assets"][0][
        "weight_source"
    ] = "https://example.invalid/private-model-with-different-provenance"

    result = validate_parser_ocr_readiness(inventory)

    assert result.ready is False
    assert "MODEL_ASSET_MISMATCH" in result.reason_codes


def test_successful_windows_local_validation_cannot_make_readiness_true():
    inventory = _inventory()
    evidence = inventory["tesseract_isolated_validation_evidence.json"]
    local = evidence["windows_local_validation"]

    assert set(local["validation_results"].values()) == {"success"}
    assert local["scope"] == "local-developer-isolated-validation"
    assert local["production_artifact"] is False
    assert local["satisfies_linux_production_pin"] is False
    assert local["can_satisfy_production_approval"] is False
    assert evidence["production_approval"] is False

    result = validate_parser_ocr_readiness(inventory)

    assert result.ready is False
    assert "TESSERACT_EVIDENCE_NOT_APPROVED" in result.reason_codes
