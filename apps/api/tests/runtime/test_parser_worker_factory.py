import base64
from datetime import UTC, datetime

from app.infrastructure.temp_storage import EncryptedTemporaryFileStorage
from app.parser.models import ParserWorkerPayload, TempFileAccessContext
from app.runtime.parser_worker_factory import build_parser_worker_pool

NOW = datetime(2026, 6, 23, tzinfo=UTC)


def test_parser_worker_factory_reads_plain_text_from_encrypted_temp_storage(tmp_path):
    storage = _storage(tmp_path)
    stored = storage.store(
        b"runtime-only plain text",
        subject_id="subject_1",
        request_id="request_1",
        file_kind="plain_text",
        mime_hint="text/plain",
        extension_hint="txt",
        size_bucket="tiny",
        now=NOW,
    )
    pool = build_parser_worker_pool(storage, max_workers=1, max_queue_size=1, clock=_Clock())

    result = pool.execute(_payload(stored["file_ref"], stored["temp_scope_id"]), timeout_ms=1000)

    assert result.parser_status == "parsed"
    assert [block.text for block in result.document.blocks] == ["runtime-only plain text"]
    assert stored["file_ref"] not in repr(result.failure)


def test_parser_worker_factory_fails_closed_on_scope_mismatch(tmp_path):
    storage = _storage(tmp_path)
    stored = storage.store(
        b"private runtime bytes",
        subject_id="subject_1",
        request_id="request_1",
        file_kind="plain_text",
        mime_hint="text/plain",
        extension_hint="txt",
        size_bucket="tiny",
        now=NOW,
    )
    pool = build_parser_worker_pool(storage, max_workers=1, max_queue_size=1, clock=_Clock())

    result = pool.execute(_payload(stored["file_ref"], "tscope_wrong_scope_value_123456"), timeout_ms=1000)

    assert result.parser_status == "failed"
    assert result.failure.code in {"TEMP_FILE_SCOPE_MISMATCH", "TEMP_FILE_ACCESS_DENIED"}
    assert "private runtime bytes" not in repr(result.failure)


def _storage(tmp_path):
    return EncryptedTemporaryFileStorage(tmp_path, base64.b64encode(b"K" * 32).decode(), 900)


class _Clock:
    def now(self):
        return NOW


def _payload(file_ref: str, temp_scope_id: str) -> ParserWorkerPayload:
    return ParserWorkerPayload(
        input_id="file_1",
        request_id="request_1",
        input_kind="file_reference",
        extraction_requirement="native_parse",
        file_ref=file_ref,
        file_kind="plain_text",
        access_context=TempFileAccessContext(
            authenticated_subject_id="subject_1",
            session_id="subject_1",
            request_id="request_1",
            temp_scope_id=temp_scope_id,
        ),
    )
