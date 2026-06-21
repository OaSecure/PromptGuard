import io

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.parser.adapters.pdf_foundation import PdfParserFoundationAdapter
from app.parser.models import (
    ParserPlanStep,
    ParserWorkerPayload,
    ResolvedTemporaryFile,
    TempFileAccessContext,
)


PRIVATE_TEXT = "PRIVATE PAGE TEXT"
PRIVATE_PATH = r"C:\private\document.pdf"
FILE_REF = "opaque-file-ref"
RUNTIME_REF = "opaque-runtime-ref"


class ContentSource:
    def __init__(self, content: bytes, exception: Exception | None = None) -> None:
        self.content = content
        self.exception = exception

    def read(self, resolved_file: ResolvedTemporaryFile) -> bytes:
        if self.exception:
            raise self.exception
        return self.content


class FakeObject(dict):
    def get_object(self):
        return self


class FakePage(dict):
    def __init__(self, text: str | None = "", resources=None, exception: Exception | None = None):
        super().__init__()
        if resources is not None:
            self["/Resources"] = resources
        self.text = text
        self.exception = exception

    def extract_text(self):
        if self.exception:
            raise self.exception
        return self.text


class FakeReader:
    def __init__(self, pages, encrypted: bool = False):
        self.pages = pages
        self.is_encrypted = encrypted


def _payload() -> ParserWorkerPayload:
    return ParserWorkerPayload(
        input_id="input-1",
        request_id="request-1",
        input_kind="file_reference",
        extraction_requirement="native_parse_then_ocr_fallback",
        file_ref=FILE_REF,
        file_kind="pdf",
        access_context=TempFileAccessContext(
            authenticated_subject_id="subject-1", session_id="session-1", request_id="request-1"
        ),
    )


def _step() -> ParserPlanStep:
    return ParserPlanStep(
        step_id="pdf-native", ordinal=0, step_kind="pdf_native_text_extract", capability_id="pdf-cap"
    )


def _resolved() -> ResolvedTemporaryFile:
    return ResolvedTemporaryFile(file_ref=FILE_REF, file_kind="pdf", local_runtime_ref=RUNTIME_REF)


def _run(content: bytes, reader=None):
    factory = (lambda stream: reader) if reader is not None else None
    return PdfParserFoundationAdapter(ContentSource(content), reader_factory=factory).execute_step(
        _step(), _payload(), _resolved()
    )


def _blank_pdf(page_count: int = 1) -> bytes:
    stream = io.BytesIO()
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=200, height=200)
    writer.write(stream)
    return stream.getvalue()


def _text_pdf(text: str) -> bytes:
    output = io.BytesIO()
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})
    })
    content = DecodedStreamObject()
    content.set_data(f"BT /F1 12 Tf 20 100 Td ({text}) Tj ET".encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(content)
    writer.write(output)
    return output.getvalue()


def test_valid_pdf_extracts_page_text_into_runtime_block_only():
    result = _run(_text_pdf("alpha invoice total"))
    assert result.status == "success"
    assert result.failure is None
    assert [block.text for block in result.document.blocks] == ["alpha invoice total"]
    assert result.document.blocks[0].block_id == "pdf-page-1"
    assert result.document.blocks[0].location == {"kind": "pdf", "page": 1}
    assert result.document.blocks[0].metadata == {}


def test_multi_page_pdf_uses_page_index_for_blocks_and_coverage_inputs():
    result = _run(_blank_pdf(2), FakeReader([FakePage("alpha"), FakePage("beta 42")]))
    assert [block.block_id for block in result.document.blocks] == ["pdf-page-1", "pdf-page-2"]
    assert [block.location for block in result.document.blocks] == [
        {"kind": "pdf", "page": 1}, {"kind": "pdf", "page": 2}
    ]
    coverage = result.document.metadata["page_coverage_inputs"]
    assert [item["page_index"] for item in coverage] == [1, 2]
    assert [item["meaningful_character_count"] for item in coverage] == [5, 6]


def test_blank_page_has_no_block_and_zero_count_coverage_input():
    result = _run(_blank_pdf(), FakeReader([FakePage(None)]))
    assert result.status == "success"
    assert result.document.blocks == []
    assert result.document.metadata["page_coverage_inputs"] == [{
        "page_index": 1,
        "native_extraction_status": "success",
        "meaningful_character_count": 0,
        "image_evidence": "absent",
    }]


def test_real_pypdf_reader_accepts_synthetic_blank_pdf():
    result = _run(_blank_pdf())
    assert result.status == "success"
    assert result.document.blocks == []
    assert result.document.metadata["page_coverage_inputs"][0]["meaningful_character_count"] == 0


def test_empty_bytes_preserve_existing_empty_success_contract():
    result = _run(b"")
    assert result.status == "success"
    assert result.document.blocks == []
    assert result.document.metadata == {}


@pytest.mark.parametrize("content", [b"%PDF-1.7\ntruncated", b"not-a-pdf"])
def test_malformed_or_truncated_pdf_returns_sanitized_failure(content, caplog):
    result = _run(content)
    assert result.status == "failed"
    assert result.failure.code == "PDF_PARSE_FAILED"
    assert result.failure.message == "PDF_PARSE_FAILED"
    assert PRIVATE_PATH not in caplog.text


def test_encrypted_pdf_is_rejected_without_password_attempt():
    result = _run(_blank_pdf(), FakeReader([], encrypted=True))
    assert result.status == "failed"
    assert result.failure.code == "PDF_ENCRYPTED"
    assert result.failure.model_dump() == {
        "code": "PDF_ENCRYPTED",
        "message": "PDF_ENCRYPTED",
        "metadata": {"failure_code": "PDF_ENCRYPTED"},
    }


def test_page_failure_returns_partial_and_preserves_available_blocks():
    exception = RuntimeError(f"{PRIVATE_TEXT} {PRIVATE_PATH} {FILE_REF} {RUNTIME_REF}")
    reader = FakeReader([FakePage("alpha"), FakePage(exception=exception), FakePage("beta")])
    result = _run(_blank_pdf(3), reader)
    assert result.status == "partial"
    assert result.failure.code == "PDF_PAGE_EXTRACTION_PARTIAL"
    assert [block.text for block in result.document.blocks] == ["alpha", "beta"]
    assert result.document.metadata["failed_page_indices"] == [2]
    coverage = result.document.metadata["page_coverage_inputs"]
    assert coverage[1] == {
        "page_index": 2,
        "native_extraction_status": "failed",
        "meaningful_character_count": 0,
        "image_evidence": "unknown",
    }
    exposed = repr(result.failure.model_dump()) + repr(result.document.metadata)
    for private in (PRIVATE_TEXT, PRIVATE_PATH, FILE_REF, RUNTIME_REF):
        assert private not in exposed


def test_all_pdf_page_references_use_the_same_one_based_numbering():
    reader = FakeReader([
        FakePage("alpha"),
        FakePage(exception=RuntimeError("sanitized")),
        FakePage("beta"),
    ])
    result = _run(_blank_pdf(3), reader)
    assert [block.block_id for block in result.document.blocks] == ["pdf-page-1", "pdf-page-3"]
    assert [block.location["page"] for block in result.document.blocks] == [1, 3]
    assert [item["page_index"] for item in result.document.metadata["page_coverage_inputs"]] == [1, 2, 3]
    assert result.document.metadata["failed_page_indices"] == [2]


@pytest.mark.parametrize(
    ("resources", "expected"),
    [
        ({"/XObject": {"/Im1": FakeObject({"/Subtype": "/Image"})}}, "present"),
        ({"/XObject": {"/Form1": FakeObject({"/Subtype": "/Form"})}}, "absent"),
        (None, "absent"),
    ],
)
def test_image_evidence_present_and_absent(resources, expected):
    result = _run(_blank_pdf(), FakeReader([FakePage("alpha", resources=resources)]))
    assert result.document.metadata["page_coverage_inputs"][0]["image_evidence"] == expected


def test_image_evidence_failure_becomes_unknown():
    class BrokenResources:
        def get(self, key, default=None):
            raise RuntimeError(PRIVATE_TEXT)

    result = _run(_blank_pdf(), FakeReader([FakePage("alpha", resources=BrokenResources())]))
    assert result.document.metadata["page_coverage_inputs"][0]["image_evidence"] == "unknown"


def test_coverage_metadata_contains_only_safe_count_index_status_and_enum(caplog):
    result = _run(_blank_pdf(), FakeReader([FakePage(PRIVATE_TEXT)]))
    coverage = result.document.metadata["page_coverage_inputs"]
    assert set(coverage[0]) == {
        "page_index", "native_extraction_status", "meaningful_character_count", "image_evidence"
    }
    exposed = repr(result.document.metadata) + caplog.text
    for private in (PRIVATE_TEXT, PRIVATE_PATH, FILE_REF, RUNTIME_REF):
        assert private not in exposed
