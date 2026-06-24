import json
from dataclasses import dataclass
from typing import Any

TORCH_WORKER_PROTOCOL_VERSION = "promptguard.torch-worker.v1"

_ALLOWED_TASKS = {"context_smoke", "context_pipeline"}
_FORBIDDEN_KEYS = {
    "raw_prompt",
    "prompt",
    "file_content",
    "extracted_text",
    "ocr_text",
    "atom_text",
    "segment_text",
    "candidate_text",
    "detected_raw_value",
    "raw_value",
    "original_filename",
    "filename",
    "path",
    "url",
    "embedding",
    "embeddings",
    "embedding_vector",
    "segment_vector",
    "vector",
    "logits",
    "raw_logits",
    "classifier_score",
    "exact_score",
    "masked_prompt",
}


@dataclass(frozen=True)
class WorkerRequestValidation:
    """Represent the protocol validation outcome before worker execution."""

    ok: bool
    error_code: str | None = None


def validate_worker_request(payload: dict[str, Any]) -> WorkerRequestValidation:
    """Validate a Torch worker request without inspecting private content.

    The protocol rejects any field name that could carry raw prompt/file/OCR
    content or model internals. This keeps the API-to-worker boundary
    metadata-only even when future tasks add real model execution.
    """

    forbidden = _find_forbidden_keys(payload)
    if forbidden:
        return WorkerRequestValidation(ok=False, error_code="TORCH_WORKER_REQUEST_FORBIDDEN_FIELD")
    if payload.get("protocol_version") not in {None, TORCH_WORKER_PROTOCOL_VERSION}:
        return WorkerRequestValidation(ok=False, error_code="TORCH_WORKER_PROTOCOL_UNSUPPORTED")
    if payload.get("task") not in _ALLOWED_TASKS:
        return WorkerRequestValidation(ok=False, error_code="TORCH_WORKER_TASK_UNSUPPORTED")
    request_id = payload.get("request_id")
    if request_id is not None and (not isinstance(request_id, str) or not request_id.strip()):
        return WorkerRequestValidation(ok=False, error_code="TORCH_WORKER_REQUEST_INVALID")
    metadata = payload.get("metadata", {})
    if not isinstance(metadata, dict):
        return WorkerRequestValidation(ok=False, error_code="TORCH_WORKER_REQUEST_INVALID")
    return WorkerRequestValidation(ok=True)


def build_worker_error(error_code: str, *, task: str | None = None, request_id: str | None = None, detail: str | None = None) -> dict[str, Any]:
    """Build a sanitized worker error response.

    Worker details may contain file paths, exception text, or private input.
    Callers receive only a stable error code and a redaction marker.
    """

    result: dict[str, Any] = {
        "ok": False,
        "error_code": error_code,
    }
    if task:
        result["task"] = task
    if request_id:
        result["request_id"] = request_id
    if detail:
        result["metadata"] = {"detail_redacted": True}
    return result


def loads_worker_json(text: str) -> dict[str, Any] | None:
    """Parse a worker JSON message and return ``None`` for malformed payloads."""

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def dumps_worker_json(payload: dict[str, Any]) -> str:
    """Serialize a worker JSON message using deterministic key order."""

    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _find_forbidden_keys(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            if isinstance(key, str) and key.lower() in _FORBIDDEN_KEYS:
                found.add(key)
            found.update(_find_forbidden_keys(nested))
    elif isinstance(value, list):
        for item in value:
            found.update(_find_forbidden_keys(item))
    return found
