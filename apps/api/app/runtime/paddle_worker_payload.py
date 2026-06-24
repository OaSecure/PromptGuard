import base64
import json
import secrets
from pathlib import Path
from typing import Any


class PaddleWorkerPayloadStore:
    """Manage transient OCR payloads for the Paddle worker boundary.

    The API sends only an opaque reference through the control plane. Raw image
    bytes live in this temporary store just long enough for the Paddle venv
    subprocess to read them and are deleted by the client in a finally path.
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def write(self, payload: dict[str, Any]) -> str:
        payload_ref = f"pwpl_{secrets.token_urlsafe(24)}"
        self._path_for(payload_ref).write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        return payload_ref

    def read(self, payload_ref: str) -> dict[str, Any]:
        payload = json.loads(self._path_for(payload_ref).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("paddle worker payload must be an object")
        return payload

    def delete(self, payload_ref: str) -> None:
        self._path_for(payload_ref).unlink(missing_ok=True)

    def exists(self, payload_ref: str) -> bool:
        return self._path_for(payload_ref).exists()

    def _path_for(self, payload_ref: str) -> Path:
        if not payload_ref.startswith("pwpl_") or any(character in payload_ref for character in ("/", "\\", "..")):
            raise ValueError("invalid paddle worker payload reference")
        return self._root / f"{payload_ref}.json"


def encode_bytes(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def decode_bytes(value: object) -> bytes:
    if not isinstance(value, str):
        raise ValueError("payload bytes must be encoded text")
    return base64.b64decode(value.encode("ascii"), validate=True)
