import io
import zipfile

import pytest

from app.parser.adapters.office_foundation import OfficeParserFoundationAdapter
from app.parser.models import (
    ParserPlanStep,
    ParserWorkerPayload,
    ResolvedTemporaryFile,
    TempFileAccessContext,
)


class ContentSource:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def read(self, resolved_file: ResolvedTemporaryFile) -> bytes:
        return self.content


def _zip(parts: dict[str, bytes], *, encrypted: bool = False) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, content in parts.items():
            archive.writestr(name, content)
    data = bytearray(stream.getvalue())
    if encrypted:
        # Set the general-purpose encryption flag in local and central headers.
        for signature, offset in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
            start = 0
            while (index := data.find(signature, start)) >= 0:
                flags = int.from_bytes(data[index + offset:index + offset + 2], "little") | 1
                data[index + offset:index + offset + 2] = flags.to_bytes(2, "little")
                start = index + 4
    return bytes(data)


def _payload(file_kind: str) -> ParserWorkerPayload:
    return ParserWorkerPayload(
        input_id="input-1",
        request_id="request-1",
        input_kind="file_reference",
        extraction_requirement="native_parse",
        file_ref="opaque-ref",
        file_kind=file_kind,
        access_context=TempFileAccessContext(
            authenticated_subject_id="subject-1", session_id="session-1", request_id="request-1"
        ),
    )


def _run(content: bytes, file_kind: str, step_kind: str):
    return OfficeParserFoundationAdapter(ContentSource(content)).execute_step(
        ParserPlanStep(step_id="office-step", ordinal=0, step_kind=step_kind, capability_id="office-cap"),
        _payload(file_kind),
        ResolvedTemporaryFile(file_ref="opaque-ref", file_kind=file_kind, local_runtime_ref="runtime-ref"),
    )


def test_docx_extracts_paragraph_and_table_text_blocks():
    content = _zip({"word/document.xml": b"""<?xml version='1.0'?>
        <w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>
          <w:body><w:p><w:r><w:t>alpha</w:t></w:r></w:p>
          <w:tbl><w:tr><w:tc><w:p><w:r><w:t>invoice total</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
          </w:body></w:document>"""})
    result = _run(content, "office_document", "office_parse")
    assert result.status == "success"
    assert [block.text for block in result.document.blocks] == ["alpha", "invoice total"]
    assert result.document.blocks[0].location == {"kind": "office", "block_index": 0}


def test_xlsx_extracts_shared_inline_and_numeric_cells_by_row():
    content = _zip({
        "xl/sharedStrings.xml": b"""<sst xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'>
          <si><t>alpha</t></si></sst>""",
        "xl/worksheets/sheet1.xml": b"""<worksheet xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'><sheetData>
          <row r='1'><c r='A1' t='s'><v>0</v></c><c r='B1' t='inlineStr'><is><t>beta</t></is></c><c r='C1'><v>42</v></c></row>
        </sheetData></worksheet>""",
    })
    result = _run(content, "spreadsheet", "spreadsheet_parse")
    assert result.status == "success"
    assert [block.text for block in result.document.blocks] == ["alpha\tbeta\t42"]
    assert result.document.blocks[0].location == {"kind": "spreadsheet", "sheet_index": 0, "row_index": 1}


def test_pptx_extracts_slide_text_without_notes_or_properties():
    content = _zip({
        "ppt/slides/slide1.xml": b"""<p:sld xmlns:p='p' xmlns:a='a'><a:t>alpha</a:t><a:t>beta</a:t></p:sld>""",
        "ppt/notesSlides/notesSlide1.xml": b"<a:t xmlns:a='a'>private note</a:t>",
    })
    result = _run(content, "slide", "slide_parse")
    assert result.status == "success"
    assert [block.text for block in result.document.blocks] == ["alpha\nbeta"]
    assert result.document.blocks[0].location == {"kind": "slide", "slide": 1}


def test_csv_on_existing_spreadsheet_path_extracts_rows_and_utf8_sig():
    result = _run(b"\xef\xbb\xbfalpha,beta\r\ninvoice total,42\r\n", "spreadsheet", "spreadsheet_parse")
    assert result.status == "success"
    assert [block.text for block in result.document.blocks] == ["alpha\tbeta", "invoice total\t42"]


@pytest.mark.parametrize(
    ("file_kind", "step_kind"),
    [("office_document", "office_parse"), ("spreadsheet", "spreadsheet_parse"), ("slide", "slide_parse")],
)
def test_empty_office_content_preserves_empty_success_contract(file_kind, step_kind):
    result = _run(b"", file_kind, step_kind)
    assert result.status == "success"
    assert result.document.blocks == []


@pytest.mark.parametrize("content", [b"PK malformed", _zip({"unrelated.xml": b"<root/>"})])
def test_docx_malformed_or_missing_required_part_is_sanitized(content):
    result = _run(content, "office_document", "office_parse")
    assert result.status == "failed"
    assert result.failure.code == "PARSER_WORKER_FAILED"
    assert result.failure.message == "PARSER_WORKER_FAILED"


def test_xml_parse_error_is_sanitized():
    result = _run(_zip({"word/document.xml": b"<broken>"}), "office_document", "office_parse")
    assert result.status == "failed"
    assert result.failure.code == "PARSER_WORKER_FAILED"


def test_encrypted_zip_flag_is_sanitized():
    result = _run(_zip({"word/document.xml": b"<root/>"}, encrypted=True), "office_document", "office_parse")
    assert result.status == "failed"
    assert result.failure.code == "PARSER_ENCRYPTED"


def test_xlsx_partial_result_preserves_valid_sheet_blocks():
    content = _zip({
        "xl/worksheets/sheet1.xml": b"""<worksheet xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'><sheetData>
          <row r='1'><c r='A1'><v>42</v></c></row></sheetData></worksheet>""",
        "xl/worksheets/sheet2.xml": b"<broken>",
    })
    result = _run(content, "spreadsheet", "spreadsheet_parse")
    assert result.status == "partial"
    assert [block.text for block in result.document.blocks] == ["42"]
    assert result.failure.code == "PARSER_PARTIAL"


def test_csv_decode_failure_does_not_expose_private_values():
    result = _run(b"\xffPRIVATE_EXCEPTION C:\\private\\alpha.csv opaque-ref runtime-ref", "spreadsheet", "spreadsheet_parse")
    exposed = f"{result.failure.message} {result.failure.metadata}"
    assert result.failure.code == "TEXT_DECODE_FAILED"
    for private in ("PRIVATE_EXCEPTION", "C:\\private", "opaque-ref", "runtime-ref"):
        assert private not in exposed
