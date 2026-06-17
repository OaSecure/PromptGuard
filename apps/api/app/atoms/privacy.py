from typing import Any

from app.atoms.models import AnalysisAtom, AnalysisAtomBuildResult, PipelineFailure

ALLOWED_LOCATION_KINDS = {"none", "page", "line", "cell", "ocr", "unknown"}


def length_bucket(length: int) -> str:
    if length <= 0:
        return "empty"
    if length <= 32:
        return "tiny"
    if length <= 128:
        return "short"
    if length <= 512:
        return "medium"
    if length <= 2048:
        return "long"
    return "huge"


def location_kind(location: object | None, source_type: str | None = None, metadata: dict[str, Any] | None = None) -> str:
    if source_type == "ocr" or (metadata or {}).get("source") == "ocr":
        return "ocr"
    if location is None:
        return "none"
    kind = None
    if isinstance(location, dict):
        kind = location.get("kind")
    else:
        kind = getattr(location, "kind", None)
    if kind == "ocr":
        return "ocr"
    if kind in ALLOWED_LOCATION_KINDS:
        return str(kind)
    return "unknown"


def serialize_atom_metadata(atom: AnalysisAtom, atomizer_version: str) -> dict[str, str]:
    return {
        "atom_id": atom.atom_id,
        "block_id": atom.block_id,
        "atom_type": atom.atom_type,
        "length_bucket": length_bucket(len(atom.text)),
        "location_kind": location_kind(atom.location),
        "atomizer_version": atomizer_version,
    }


def serialize_failure_metadata(failure: PipelineFailure, atomizer_version: str) -> dict[str, Any]:
    payload = {
        "failure_code": failure.code,
        "atomizer_version": atomizer_version,
    }
    for key in ("length_bucket", "location_kind", "atom_count", "block_count"):
        if key in failure.metadata:
            payload[key] = failure.metadata[key]
    return payload


def serialize_result_metadata(result: AnalysisAtomBuildResult) -> dict[str, list[dict[str, Any]]]:
    return {
        "atoms": [serialize_atom_metadata(atom, result.atomizer_version) for atom in result.atoms],
        "failures": [serialize_failure_metadata(failure, result.atomizer_version) for failure in result.failures],
    }
