import json
from dataclasses import dataclass
from typing import Any

PADDLE_WORKER_PROTOCOL_VERSION = "promptguard.paddle-worker.v1"

_ALLOWED_TASKS = {"ocr_image"}
_FORBIDDEN_KEYS = {
    "raw_prompt",
    "prompt",
    "file_content",
    "extracted_text",
    "ocr_text",
    "detected_raw_value",
    "raw_value",
    "original_filename",
    "filename",
    "path",
    "url",
    "embedding",
    "embeddings",
    "logits",
    "classifier_score",
    "masked_prompt",
}


@dataclass(frozen=True)
class PaddleWorkerRequestValidation:
    ok: bool
    error_code: str | None = None


def validate_paddle_worker_request(payload: dict[str, Any]) -> PaddleWorkerRequestValidation:
    forbidden = _find_forbidden_keys(payload)
    if forbidden:
        return PaddleWorkerRequestValidation(ok=False, error_code="PADDLE_WORKER_REQUEST_FORBIDDEN_FIELD")
    if payload.get("protocol_version") not in {None, PADDLE_WORKER_PROTOCOL_VERSION}:
        return PaddleWorkerRequestValidation(ok=False, error_code="PADDLE_WORKER_PROTOCOL_UNSUPPORTED")
    if payload.get("task") not in _ALLOWED_TASKS:
        return PaddleWorkerRequestValidation(ok=False, error_code="PADDLE_WORKER_TASK_UNSUPPORTED")
    metadata = payload.get("metadata", {})
    if not isinstance(metadata, dict):
        return PaddleWorkerRequestValidation(ok=False, error_code="PADDLE_WORKER_REQUEST_INVALID")
    request_id = payload.get("request_id")
    if request_id is not None and (not isinstance(request_id, str) or not request_id.strip()):
        return PaddleWorkerRequestValidation(ok=False, error_code="PADDLE_WORKER_REQUEST_INVALID")
    return PaddleWorkerRequestValidation(ok=True)


def build_paddle_worker_error(
    error_code: str,
    *,
    task: str | None = None,
    request_id: str | None = None,
    detail: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {"ok": False, "error_code": error_code}
    if task:
        result["task"] = task
    if request_id:
        result["request_id"] = request_id
    if detail:
        result["metadata"] = {"detail_redacted": True}
    return result


def loads_paddle_worker_json(text: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def dumps_paddle_worker_json(payload: dict[str, Any]) -> str:
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
