import base64
from datetime import UTC, datetime, timedelta

import pytest

from app.infrastructure.temp_storage import EncryptedTemporaryFileStorage, TempFileAccessContext, TempFileError


def storage(tmp_path, key=b"K" * 32): return EncryptedTemporaryFileStorage(tmp_path, base64.b64encode(key).decode(), 900)


def test_encrypted_round_trip_and_plaintext_absent(tmp_path):
    store = storage(tmp_path); now = datetime(2026, 1, 1, tzinfo=UTC); raw = b"SYNTHETIC_PLAINTEXT_SENTINEL"
    result = store.store(raw, subject_id="u1", request_id="r1", file_kind="plain_text", mime_hint="text/plain", extension_hint="txt", size_bucket="tiny", now=now)
    assert result["file_ref"].startswith("fref_") and raw not in b"".join(path.read_bytes() for path in tmp_path.iterdir())
    context = TempFileAccessContext("u1", "r1", result["temp_scope_id"])
    assert store.resolve(result["file_ref"], context, now + timedelta(seconds=899)) == raw
    with pytest.raises(TempFileError, match="TEMP_FILE_EXPIRED"): store.resolve(result["file_ref"], context, now + timedelta(seconds=900))


def test_scope_mismatch_tamper_and_cleanup(tmp_path):
    store = storage(tmp_path); now = datetime(2026, 1, 1, tzinfo=UTC)
    result = store.store(b"data", subject_id="u1", request_id="r1", file_kind="plain_text", mime_hint=None, extension_hint=None, size_bucket="tiny", now=now)
    with pytest.raises(TempFileError, match="TEMP_FILE_ACCESS_DENIED"): store.resolve(result["file_ref"], TempFileAccessContext("other", "r1", result["temp_scope_id"]), now)
    blob = next(tmp_path.glob("*.blob")); blob.write_bytes(blob.read_bytes()[:-1] + b"x")
    with pytest.raises(TempFileError, match="TEMP_FILE_DECRYPT_FAILED"): store.resolve(result["file_ref"], TempFileAccessContext("u1", "r1", result["temp_scope_id"]), now)
    assert store.delete(result["file_ref"]) and store.delete(result["file_ref"])


def test_sweep_preserves_active_and_removes_expired(tmp_path):
    store = storage(tmp_path); now = datetime(2026, 1, 1, tzinfo=UTC)
    old = store.store(b"old", subject_id="u", request_id="r", file_kind="plain_text", mime_hint=None, extension_hint=None, size_bucket="tiny", now=now)
    active = store.store(b"new", subject_id="u", request_id="r", file_kind="plain_text", mime_hint=None, extension_hint=None, size_bucket="tiny", now=now + timedelta(seconds=500))
    assert store.sweep_expired(now + timedelta(seconds=900)) == [old["file_ref"]]
    assert (tmp_path / f"{active['file_ref']}.blob").exists()
