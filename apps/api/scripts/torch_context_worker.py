"""Metadata-only Torch worker subprocess entry point.

The API process calls this script with the Torch venv Python. This first slice
only establishes the subprocess contract; model execution tasks are added in
the next integration slice.
"""

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.runtime.torch_worker_protocol import (  # noqa: E402
    build_worker_error,
    dumps_worker_json,
    loads_worker_json,
    validate_worker_request,
)


def main() -> int:
    payload = loads_worker_json(sys.stdin.read())
    if payload is None:
        print(dumps_worker_json(build_worker_error("TORCH_WORKER_INVALID_REQUEST")))
        return 1
    validation = validate_worker_request(payload)
    task = payload.get("task") if isinstance(payload.get("task"), str) else None
    request_id = payload.get("request_id") if isinstance(payload.get("request_id"), str) else None
    if not validation.ok:
        print(dumps_worker_json(build_worker_error(validation.error_code or "TORCH_WORKER_INVALID_REQUEST", task=task, request_id=request_id)))
        return 1
    if task == "context_smoke":
        print(dumps_worker_json({"ok": True, "task": task, "request_id": request_id, "metadata": {"worker": "torch"}}))
        return 0
    print(dumps_worker_json(build_worker_error("TORCH_WORKER_TASK_NOT_IMPLEMENTED", task=task, request_id=request_id)))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
