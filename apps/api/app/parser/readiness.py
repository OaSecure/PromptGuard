"""Static, fail-closed readiness checks for parser/OCR license artifacts."""

from dataclasses import dataclass
from typing import Mapping

REQUIRED_ARTIFACTS = (
    "parser_ocr_sbom.json",
    "parser_ocr_license_report.json",
    "ocr_model_weight_license_report.json",
    "NOTICE.parser_ocr.txt",
    "paddle_ocr_candidate_report.json",
    "tesseract_ocr_candidate_report.json",
    "tesseract_isolated_validation_evidence.json",
)

_SBOM_FIELDS = frozenset({"components", "schema_version", "scope"})
_COMPONENT_FIELDS = frozenset(
    {
        "artifact_sha256",
        "bundled_by",
        "bundled_license_inventory",
        "dependency_path",
        "dependency_type",
        "license_id",
        "name",
        "package_source",
        "transitive_dependencies",
        "transitive_dependency_status",
        "version",
    }
)
_LICENSE_REPORT_FIELDS = frozenset({"decisions", "ocr_model_weights", "schema_version", "scope"})
_DECISION_FIELDS = frozenset(
    {
        "decision",
        "denial_reason",
        "license_id",
        "name",
        "notice_license_preservation_required",
        "reason",
        "source_disclosure_required",
        "source_disclosure_risk",
        "version",
    }
)
_MODEL_REPORT_FIELDS = frozenset({"asset_types_in_scope", "assets", "schema_version", "scope", "status"})
_MODEL_ASSET_FIELDS = frozenset(
    {
        "asset_type",
        "commercial_use_compatible",
        "default_distribution",
        "license_id",
        "model_id",
        "model_version",
        "source_disclosure_required",
        "weight_source",
    }
)
_ALLOWED_LICENSES = frozenset(
    {
        "Apache-2.0",
        "BSD-3-Clause",
        "BSD-3-Clause OR Apache-2.0",
        "ISC",
        "MIT",
    }
)


@dataclass(frozen=True)
class ParserOcrReadinessResult:
    ready: bool
    reason_codes: tuple[str, ...]


def validate_parser_ocr_readiness(artifacts: Mapping[str, object]) -> ParserOcrReadinessResult:
    reasons: set[str] = set()
    if set(artifacts) != set(REQUIRED_ARTIFACTS):
        reasons.add("REQUIRED_ARTIFACT_MISSING" if set(REQUIRED_ARTIFACTS) - set(artifacts) else "UNKNOWN_ARTIFACT")
        return _result(reasons)

    sbom = _mapping(artifacts["parser_ocr_sbom.json"])
    licenses = _mapping(artifacts["parser_ocr_license_report.json"])
    models = _mapping(artifacts["ocr_model_weight_license_report.json"])
    notice = artifacts["NOTICE.parser_ocr.txt"]
    if sbom is None or licenses is None or models is None or not isinstance(notice, str):
        return _result({"ARTIFACT_SCHEMA_INVALID"})

    components = _records(sbom, _SBOM_FIELDS, "components", _COMPONENT_FIELDS)
    decisions = _records(licenses, _LICENSE_REPORT_FIELDS, "decisions", _DECISION_FIELDS)
    assets = _records(models, _MODEL_REPORT_FIELDS, "assets", _MODEL_ASSET_FIELDS)
    if components is None or decisions is None or assets is None:
        reasons.add("ARTIFACT_SCHEMA_INVALID")
    else:
        _validate_active_components(components, decisions, notice, reasons)
        _validate_model_assets(assets, components, reasons)

    _validate_candidate(
        artifacts["paddle_ocr_candidate_report.json"],
        "PADDLE",
        reasons,
    )
    _validate_candidate(
        artifacts["tesseract_ocr_candidate_report.json"],
        "TESSERACT",
        reasons,
    )
    _validate_evidence(artifacts["tesseract_isolated_validation_evidence.json"], reasons)
    return _result(reasons)


def _validate_active_components(
    components: list[Mapping[str, object]],
    decisions: list[Mapping[str, object]],
    notice: str,
    reasons: set[str],
) -> None:
    component_ids = _identities(components, "name", "version", "license_id")
    decision_ids = _identities(decisions, "name", "version", "license_id")
    if None in component_ids or _invalid_dependency_path_present(components):
        reasons.add("ACTIVE_COMPONENT_INVALID")
    if None in decision_ids:
        reasons.add("ACTIVE_COMPONENT_INVALID")
    if _forbidden_license_present(decisions):
        reasons.add("ACTIVE_LICENSE_FORBIDDEN")
    if component_ids != decision_ids:
        reasons.add("ACTIVE_COMPONENT_MISMATCH")
    if _notice_component_missing(components, notice):
        reasons.add("NOTICE_COMPONENT_MISSING")


def _validate_model_assets(
    assets: list[Mapping[str, object]],
    components: list[Mapping[str, object]],
    reasons: set[str],
) -> None:
    component_ids = {_normalized_identity(item, "name", "version", "license_id") for item in components}
    asset_ids = {_normalized_identity(item, "model_id", "model_version", "license_id") for item in assets}
    if None in asset_ids or any(not _nonempty_string(item.get("weight_source")) for item in assets):
        reasons.add("MODEL_ASSET_INVALID")
    if any(item.get("license_id") not in _ALLOWED_LICENSES for item in assets):
        reasons.add("MODEL_ASSET_INVALID")
    if not asset_ids.issubset(component_ids):
        reasons.add("MODEL_ASSET_MISMATCH")


def _validate_candidate(artifact: object, prefix: str, reasons: set[str]) -> None:
    candidate = _mapping(artifact)
    if candidate is None:
        reasons.add("ARTIFACT_SCHEMA_INVALID")
        return
    status = candidate.get("status")
    dependency_approved = candidate.get("approved_for_dependency_addition")
    distribution_approved = candidate.get("approved_for_default_distribution")
    if not isinstance(status, str) or not isinstance(dependency_approved, bool) or not isinstance(
        distribution_approved, bool
    ):
        reasons.add("ARTIFACT_SCHEMA_INVALID")
        return
    if dependency_approved or distribution_approved or status in {"approved", "enabled", "production-ready", "ready"}:
        if candidate.get("production_approval_evidence") is not True:
            reasons.add(f"{prefix}_APPROVAL_EVIDENCE_MISSING")
        return
    reasons.add(f"{prefix}_CANDIDATE_NOT_APPROVED")


def _validate_evidence(artifact: object, reasons: set[str]) -> None:
    evidence = _mapping(artifact)
    if evidence is None or not isinstance(evidence.get("production_approval"), bool):
        reasons.add("ARTIFACT_SCHEMA_INVALID")
    elif evidence["production_approval"] is not True:
        reasons.add("TESSERACT_EVIDENCE_NOT_APPROVED")


def _records(
    document: Mapping[str, object],
    document_fields: frozenset[str],
    records_field: str,
    record_fields: frozenset[str],
) -> list[Mapping[str, object]] | None:
    if set(document) != document_fields:
        return None
    records = document.get(records_field)
    if not isinstance(records, list) or not records:
        return None
    if any(not isinstance(item, dict) or not set(item).issubset(record_fields) for item in records):
        return None
    return records


def _identity(item: Mapping[str, object], *fields: str) -> tuple[str, ...] | None:
    values = tuple(item.get(field) for field in fields)
    if not all(_nonempty_string(value) for value in values):
        return None
    return values  # type: ignore[return-value]


def _normalized_identity(item: Mapping[str, object], *fields: str) -> tuple[str, ...] | None:
    identity = _identity(item, *fields)
    if identity is None:
        return None
    return (identity[0].casefold(), *identity[1:])


def _identities(records: list[Mapping[str, object]], *fields: str) -> set[tuple[str, ...] | None]:
    return {_identity(item, *fields) for item in records}


def _invalid_dependency_path_present(components: list[Mapping[str, object]]) -> bool:
    return any(not _dependency_path_valid(item) for item in components)


def _forbidden_license_present(records: list[Mapping[str, object]]) -> bool:
    return any(item.get("license_id") not in _ALLOWED_LICENSES for item in records)


def _notice_component_missing(components: list[Mapping[str, object]], notice: str) -> bool:
    names = (item.get("name") for item in components)
    return any(isinstance(name, str) and f"Component: {name}" not in notice for name in names)


def _dependency_path_valid(item: Mapping[str, object]) -> bool:
    path = item.get("dependency_path")
    return isinstance(path, list) and bool(path) and all(_nonempty_string(value) for value in path)


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _mapping(value: object) -> Mapping[str, object] | None:
    return value if isinstance(value, dict) else None


def _result(reasons: set[str]) -> ParserOcrReadinessResult:
    return ParserOcrReadinessResult(not reasons, tuple(sorted(reasons)))
