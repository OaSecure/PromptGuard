import base64
import io
from datetime import UTC, datetime

from app.domain.types.parser import OcrResult, OcrTextBlock
from app.infrastructure.temp_storage import EncryptedTemporaryFileStorage
from app.parser.models import ParserWorkerPayload, TempFileAccessContext
from app.runtime import parser_worker_factory
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

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
    pool = parser_worker_factory.build_parser_worker_pool(storage, max_workers=1, max_queue_size=1, clock=_Clock())

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
    pool = parser_worker_factory.build_parser_worker_pool(storage, max_workers=1, max_queue_size=1, clock=_Clock())

    result = pool.execute(_payload(stored["file_ref"], "tscope_wrong_scope_value_123456"), timeout_ms=1000)

    assert result.parser_status == "failed"
    assert result.failure.code in {"TEMP_FILE_SCOPE_MISMATCH", "TEMP_FILE_ACCESS_DENIED"}
    assert "private runtime bytes" not in repr(result.failure)


def test_parser_worker_factory_routes_image_references_to_image_ocr(tmp_path, monkeypatch):
    storage = _storage(tmp_path)
    stored = storage.store(
        b"\x89PNG\r\n\x1a\nruntime-image-bytes",
        subject_id="subject_1",
        request_id="request_1",
        file_kind="image",
        mime_hint="image/png",
        extension_hint="png",
        size_bucket="tiny",
        now=NOW,
    )
    engine = _FakeOcrEngine()
    monkeypatch.setattr(
        parser_worker_factory,
        "compose_paddle_ocr_engine",
        lambda *_args, **_kwargs: engine,
    )
    pool = parser_worker_factory.build_parser_worker_pool(storage, max_workers=1, max_queue_size=1, clock=_Clock())

    result = pool.execute(
        _payload(stored["file_ref"], stored["temp_scope_id"], file_kind="image", extraction_requirement="ocr_required"),
        timeout_ms=1000,
    )

    assert result.parser_status == "parsed"
    assert result.ocr_status == "text_found"
    assert result.document is not None
    assert [block.source_type for block in result.document.blocks] == ["image_ocr"]
    assert [block.text for block in result.document.blocks] == ["detected image text"]
    assert stored["file_ref"] not in repr(result.failure)
    assert "runtime-image-bytes" not in repr(result.failure)


def test_parser_worker_factory_reads_pdf_native_text_from_encrypted_temp_storage(tmp_path):
    storage = _storage(tmp_path)
    stored = storage.store(
        _synthetic_text_pdf("runtime-only pdf text"),
        subject_id="subject_1",
        request_id="request_1",
        file_kind="pdf",
        mime_hint="application/pdf",
        extension_hint="pdf",
        size_bucket="tiny",
        now=NOW,
    )
    pool = parser_worker_factory.build_parser_worker_pool(storage, max_workers=1, max_queue_size=1, clock=_Clock())

    result = pool.execute(
        _payload(
            stored["file_ref"],
            stored["temp_scope_id"],
            file_kind="pdf",
            extraction_requirement="native_parse_then_ocr_fallback",
        ),
        timeout_ms=1000,
    )

    assert result.parser_status == "parsed"
    assert result.document is not None
    assert [block.text for block in result.document.blocks] == ["runtime-only pdf text"]
    assert [block.source_type for block in result.document.blocks] == ["pdf_native_page"]
    assert result.ocr_status == "not_applicable"
    assert stored["file_ref"] not in repr(result.failure)


def _storage(tmp_path):
    return EncryptedTemporaryFileStorage(tmp_path, base64.b64encode(b"K" * 32).decode(), 900)


class _Clock:
    def now(self):
        return NOW


class _FakeOcrEngine:
    engine_id = "fake-paddleocr"

    def recognize(self, image, options):
        return OcrResult(
            status="text_found",
            blocks=[OcrTextBlock(text="detected image text", confidence_bucket="high")],
            engine_id=self.engine_id,
        )


def _payload(
    file_ref: str,
    temp_scope_id: str,
    *,
    file_kind: str = "plain_text",
    extraction_requirement: str = "native_parse",
) -> ParserWorkerPayload:
    return ParserWorkerPayload(
        input_id="file_1",
        request_id="request_1",
        input_kind="file_reference",
        extraction_requirement=extraction_requirement,
        file_ref=file_ref,
        file_kind=file_kind,
        access_context=TempFileAccessContext(
            authenticated_subject_id="subject_1",
            session_id="subject_1",
            request_id="request_1",
            temp_scope_id=temp_scope_id,
        ),
    )


def _synthetic_text_pdf(text: str) -> bytes:
    output = io.BytesIO()
    writer = PdfWriter()
    page = writer.add_blank_page(width=360, height=180)
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})
    })
    content = DecodedStreamObject()
    content.set_data(f"BT /F1 18 Tf 32 90 Td ({text}) Tj ET".encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(content)
    writer.write(output)
    return output.getvalue()
