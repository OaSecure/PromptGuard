import base64, json, os, secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class TempFileError(Exception):
    def __init__(self, code: str):
        super().__init__(code); self.code = code


@dataclass(frozen=True)
class TempFileAccessContext:
    authenticated_subject_id: str
    request_id: str
    temp_scope_id: str
    purpose: str = "analyze"


class EncryptedTemporaryFileStorage:
    def __init__(self, root: Path, encryption_key_b64: str, ttl_seconds: int = 900):
        try: key = base64.b64decode(encryption_key_b64, validate=True)
        except Exception as exc: raise ValueError("invalid temporary file encryption key") from exc
        if len(key) != 32: raise ValueError("temporary file encryption key must decode to 32 bytes")
        self.root, self.aes, self.ttl = root, AESGCM(key), timedelta(seconds=ttl_seconds)
        root.mkdir(parents=True, exist_ok=True)

    def store(self, data: bytes, *, subject_id: str, request_id: str, file_kind: str, mime_hint: str | None,
              extension_hint: str | None, size_bucket: str, now: datetime | None = None) -> dict:
        now = now or datetime.now(UTC); ref = f"fref_{secrets.token_urlsafe(32)}"; scope = f"tscope_{secrets.token_urlsafe(24)}"; expires = now + self.ttl
        nonce = os.urandom(12); cipher = nonce + self.aes.encrypt(nonce, data, ref.encode())
        manifest = {"storage_version": 1, "subject_id": subject_id, "request_id": request_id, "temp_scope_id": scope,
                    "created_at": now.isoformat(), "expires_at": expires.isoformat(), "file_kind": file_kind,
                    "mime_hint": mime_hint, "extension_hint": extension_hint, "size_bucket": size_bucket}
        self._write(self._path(ref, ".blob"), cipher); self._write(self._path(ref, ".json"), json.dumps(manifest, separators=(",", ":")).encode())
        return {"file_ref": ref, "expires_at": expires, "temp_scope_id": scope, **{k: manifest[k] for k in ("file_kind", "mime_hint", "extension_hint", "size_bucket")}}

    def resolve(self, ref: str, context: TempFileAccessContext, now: datetime | None = None) -> bytes:
        manifest = self._manifest(ref); now = now or datetime.now(UTC)
        if (manifest["subject_id"], manifest["request_id"], manifest["temp_scope_id"]) != (context.authenticated_subject_id, context.request_id, context.temp_scope_id): raise TempFileError("TEMP_FILE_ACCESS_DENIED")
        if now >= datetime.fromisoformat(manifest["expires_at"]): raise TempFileError("TEMP_FILE_EXPIRED")
        try:
            cipher = self._path(ref, ".blob").read_bytes(); return self.aes.decrypt(cipher[:12], cipher[12:], ref.encode())
        except Exception as exc: raise TempFileError("TEMP_FILE_DECRYPT_FAILED") from exc

    def delete(self, ref: str) -> bool:
        for suffix in (".blob", ".json"): self._path(ref, suffix).unlink(missing_ok=True)
        return True

    def sweep_expired(self, now: datetime | None = None) -> list[str]:
        now = now or datetime.now(UTC); deleted = []
        for path in self.root.glob("fref_*.json"):
            ref = path.stem
            try: expired = now >= datetime.fromisoformat(self._manifest(ref)["expires_at"])
            except TempFileError: expired = True
            if expired: self.delete(ref); deleted.append(ref)
        return deleted

    def _manifest(self, ref: str) -> dict:
        if not ref.startswith("fref_"): raise TempFileError("TEMP_FILE_NOT_FOUND")
        try: return json.loads(self._path(ref, ".json").read_text(encoding="utf-8"))
        except FileNotFoundError as exc: raise TempFileError("TEMP_FILE_NOT_FOUND") from exc
        except Exception as exc: raise TempFileError("TEMP_FILE_CORRUPT") from exc
    def manifest(self, ref: str) -> dict:
        return self._manifest(ref)
    def _path(self, ref: str, suffix: str) -> Path: return self.root / f"{ref}{suffix}"
    @staticmethod
    def _write(target: Path, data: bytes) -> None:
        temp = target.with_suffix(target.suffix + ".tmp"); temp.write_bytes(data); os.replace(temp, target)
