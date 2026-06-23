import base64
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.infrastructure.temp_storage import EncryptedTemporaryFileStorage
from app.routes.auth import require_active_user
from app.routes.temp_files import get_temp_storage, router


def client(tmp_path):
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[require_active_user] = lambda: SimpleNamespace(id=uuid4())
    app.dependency_overrides[get_temp_storage] = lambda: EncryptedTemporaryFileStorage(tmp_path, base64.b64encode(b"U" * 32).decode())
    return TestClient(app)


def test_upload_derives_bucket_and_discards_filename(tmp_path):
    response = client(tmp_path).post("/files/temp", data={"request_id": "req_1", "file_kind": "plain_text", "mime_hint": "text/plain", "extension_hint": ".txt"}, files={"file": ("secret-customer.txt", b"x", "text/plain")})
    assert response.status_code == 200
    body = response.json(); assert body["size_bucket"] == "tiny" and body["file_ref"].startswith("fref_")
    assert body["temp_scope_id"].startswith("tscope_")
    encoded = b"".join(path.read_bytes() for path in tmp_path.iterdir())
    assert b"secret-customer" not in encoded and b'"size_bytes"' not in encoded


def test_upload_allows_empty_and_rejects_unsupported(tmp_path):
    ok = client(tmp_path).post("/files/temp", data={"request_id": "req", "file_kind": "plain_text"}, files={"file": ("x", b"")})
    bad = client(tmp_path).post("/files/temp", data={"request_id": "req", "file_kind": "executable"}, files={"file": ("x", b"x")})
    assert ok.status_code == 200 and ok.json()["size_bucket"] == "empty"
    assert bad.status_code == 422
