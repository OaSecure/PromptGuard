import json
import secrets
from pathlib import Path
from typing import Any


class TorchWorkerPayloadStore:
    """Manage transient data-plane payloads for the Torch worker boundary.

    The control-plane worker request remains metadata-only and carries only an
    opaque payload reference. This store holds raw model input only long enough
    for the dedicated Torch subprocess to read it, then the API-side client
    deletes it in a ``finally`` path.
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def write(self, payload: dict[str, Any]) -> str:
        """Persist a transient payload and return an opaque worker-local reference."""
        payload_ref = f"twpl_{secrets.token_urlsafe(24)}"
        path = self._path_for(payload_ref)
        path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        return payload_ref

    def read(self, payload_ref: str) -> dict[str, Any]:
        """Read a transient payload by opaque reference."""
        payload = json.loads(self._path_for(payload_ref).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("torch worker payload must be an object")
        return payload

    def delete(self, payload_ref: str) -> None:
        """Delete a transient payload if it still exists."""
        self._path_for(payload_ref).unlink(missing_ok=True)

    def exists(self, payload_ref: str) -> bool:
        """Return whether a transient payload still exists."""
        return self._path_for(payload_ref).exists()

    def _path_for(self, payload_ref: str) -> Path:
        if not payload_ref.startswith("twpl_") or any(character in payload_ref for character in ("/", "\\", "..")):
            raise ValueError("invalid torch worker payload reference")
        return self._root / f"{payload_ref}.json"
