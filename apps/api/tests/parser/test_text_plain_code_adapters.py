import ast
from pathlib import Path

import pytest

from app.parser.adapters.code_text import CodeTextParserAdapter
from app.parser.adapters.native_text import NativeTextAdapter
from app.parser.adapters.text_wrapper import TextWrapperParserAdapter
from app.parser.models import ParserPlanStep, ParserWorkerPayload, ResolvedTemporaryFile


RAW_TEXT = "PRIVATE RAW CONTENT"
PRIVATE_PATH = r"C:\private\original-secret.py"
ORIGINAL_FILENAME = "original-secret.py"
RUNTIME_REF = "private-runtime-ref"
PRIVATE_EXCEPTION = "PRIVATE CONTENT SOURCE EXCEPTION"


class FakeResolvedFileContentSource:
    def __init__(self, content: bytes = b"", exception: Exception | None = None) -> None:
        self.content = content
        self.exception = exception

    def read(self, resolved_file: ResolvedTemporaryFile) -> bytes:
        if self.exception is not None:
            raise self.exception
        return self.content


def _text_payload(text: str) -> ParserWorkerPayload:
    return ParserWorkerPayload(
        input_id="opaque-input",
        request_id="opaque-request",
        input_kind="text_wrapper",
        extraction_requirement="wrap_text",
        text=text,
    )


def _file_payload(file_kind: str) -> ParserWorkerPayload:
    return ParserWorkerPayload(
        input_id="opaque-input",
        request_id="opaque-request",
        input_kind="file_reference",
        extraction_requirement="native_parse",
        file_ref="opaque-file-ref",
        file_kind=file_kind,
        access_context={
            "authenticated_subject_id": "opaque-subject",
            "session_id": "opaque-session",
            "request_id": "opaque-request",
        },
    )


def _resolved_file(file_kind: str) -> ResolvedTemporaryFile:
    return ResolvedTemporaryFile(
        file_ref="opaque-file-ref",
        file_kind=file_kind,
        local_runtime_ref=RUNTIME_REF,
    )


def _step(step_kind: str) -> ParserPlanStep:
    return ParserPlanStep(
        step_id=step_kind,
        ordinal=0,
        step_kind=step_kind,
        capability_id=f"cap-{step_kind}",
    )


def _assert_success_contract(result) -> None:
    assert result.status == "success"
    assert result.document is not None
    assert result.document.parser_status == "parsed"
    assert result.document.ocr_status == "not_applicable"
    assert result.document.metadata == {}
    assert all(block.metadata == {} for block in result.document.blocks)


def _exposed(result, caplog) -> str:
    failure = result.failure
    return " ".join((
        failure.message if failure else "",
        repr(failure.metadata) if failure else "",
        repr(result.document.metadata) if result.document else "",
        " ".join(block.block_id for block in result.document.blocks) if result.document else "",
        caplog.text,
    ))


def _assert_private_values_hidden(result, caplog) -> None:
    exposed = _exposed(result, caplog)
    for private_value in (
        RAW_TEXT,
        PRIVATE_PATH,
        ORIGINAL_FILENAME,
        RUNTIME_REF,
        PRIVATE_EXCEPTION,
    ):
        assert private_value not in exposed


# These tests intentionally freeze the current runtime compatibility mapping.
# The runtime ParsedBlock does not yet expose BlockSource or ExtractionStatus.
def test_text_wrapper_adapter_returns_one_runtime_compatible_block():
    result = TextWrapperParserAdapter().execute_step(
        _step("wrap_text"), _text_payload("hello wrapper"), None
    )

    _assert_success_contract(result)
    assert result.document.file_ref is None
    assert result.document.file_type is None
    assert len(result.document.blocks) == 1
    block = result.document.blocks[0]
    assert block.block_id == "text-wrapper-0"
    assert block.text == "hello wrapper"
    assert block.source_type == "text_wrapper"
    assert block.location is None


def test_text_wrapper_adapter_accepts_empty_text_without_file_access():
    result = TextWrapperParserAdapter().execute_step(
        _step("wrap_text"), _text_payload(""), None
    )

    _assert_success_contract(result)
    assert result.document.blocks == []


def test_native_text_adapter_preserves_plain_text_runtime_mapping():
    adapter = NativeTextAdapter(FakeResolvedFileContentSource("hello 한글".encode()))

    result = adapter.execute_step(
        _step("native_text_extract"), _file_payload("plain_text"), _resolved_file("plain_text")
    )

    _assert_success_contract(result)
    assert result.document.blocks[0].block_id == "native-text-0"
    assert result.document.blocks[0].source_type == "plain_text_block"
    assert result.document.blocks[0].location is None


def test_native_text_adapter_accepts_empty_file():
    result = NativeTextAdapter(FakeResolvedFileContentSource()).execute_step(
        _step("native_text_extract"), _file_payload("plain_text"), _resolved_file("plain_text")
    )

    _assert_success_contract(result)
    assert result.document.blocks == []


@pytest.mark.parametrize(
    ("text", "line_end"),
    [("a\nb", 2), ("a\n", 1), ("a", 1)],
)
def test_code_adapter_uses_stable_splitlines_location_policy(text, line_end):
    result = CodeTextParserAdapter(FakeResolvedFileContentSource(text.encode())).execute_step(
        _step("code_parse"), _file_payload("code"), _resolved_file("code")
    )

    _assert_success_contract(result)
    assert len(result.document.blocks) == 1
    block = result.document.blocks[0]
    assert block.block_id == "code-text-0"
    assert block.text == text
    assert block.source_type == "code_block"
    assert block.location == {"kind": "code", "line_start": 1, "line_end": line_end}


def test_code_adapter_accepts_empty_file_without_location():
    result = CodeTextParserAdapter(FakeResolvedFileContentSource()).execute_step(
        _step("code_parse"), _file_payload("code"), _resolved_file("code")
    )

    _assert_success_contract(result)
    assert result.document.blocks == []


@pytest.mark.parametrize(
    ("adapter_type", "step_kind", "file_kind"),
    [
        (NativeTextAdapter, "native_text_extract", "plain_text"),
        (CodeTextParserAdapter, "code_parse", "code"),
    ],
)
def test_file_text_adapters_sanitize_invalid_utf8(
    adapter_type, step_kind, file_kind, caplog
):
    result = adapter_type(FakeResolvedFileContentSource(b"\xff" + RAW_TEXT.encode())).execute_step(
        _step(step_kind), _file_payload(file_kind), _resolved_file(file_kind)
    )

    assert result.status == "failed"
    assert result.failure is not None
    assert result.failure.code == "TEXT_DECODE_FAILED"
    _assert_private_values_hidden(result, caplog)


@pytest.mark.parametrize(
    ("adapter_type", "step_kind", "file_kind"),
    [
        (NativeTextAdapter, "native_text_extract", "plain_text"),
        (CodeTextParserAdapter, "code_parse", "code"),
    ],
)
def test_file_text_adapters_sanitize_content_source_failure(
    adapter_type, step_kind, file_kind, caplog
):
    exception = RuntimeError(
        f"{PRIVATE_EXCEPTION} {PRIVATE_PATH} {ORIGINAL_FILENAME} {RUNTIME_REF} {RAW_TEXT}"
    )
    result = adapter_type(FakeResolvedFileContentSource(exception=exception)).execute_step(
        _step(step_kind), _file_payload(file_kind), _resolved_file(file_kind)
    )

    assert result.status == "failed"
    assert result.failure is not None
    assert result.failure.code == "PARSER_WORKER_FAILED"
    _assert_private_values_hidden(result, caplog)


@pytest.mark.parametrize(
    ("adapter", "step", "payload", "resolved_file"),
    [
        (TextWrapperParserAdapter(), _step("code_parse"), _text_payload("text"), None),
        (
            NativeTextAdapter(FakeResolvedFileContentSource(b"text")),
            _step("code_parse"),
            _file_payload("plain_text"),
            _resolved_file("plain_text"),
        ),
        (
            CodeTextParserAdapter(FakeResolvedFileContentSource(b"code")),
            _step("code_parse"),
            _file_payload("plain_text"),
            _resolved_file("plain_text"),
        ),
    ],
)
def test_text_adapters_reject_unsupported_step_input_or_file_kind(
    adapter, step, payload, resolved_file
):
    result = adapter.execute_step(step, payload, resolved_file)

    assert result.status == "failed"
    assert result.failure is not None
    assert result.failure.code == "UNSUPPORTED_FILE_KIND"


def test_text_plain_code_adapters_do_not_import_forbidden_pipeline_or_parser_modules():
    adapter_root = Path(__file__).parents[2] / "app" / "parser" / "adapters"
    forbidden_roots = {
        "scanner", "normalization", "classifier", "verifier", "policy",
        "pypdf", "pypdfium2", "paddleocr", "pytesseract", "docx", "openpyxl", "pptx",
    }

    for filename in ("text_wrapper.py", "native_text.py", "code_text.py"):
        tree = ast.parse((adapter_root / filename).read_text(encoding="utf-8"))
        imported_roots = {
            alias.name.split(".")[0].lower()
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported_roots.update(
            node.module.split(".")[-1].lower()
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        )
        assert imported_roots.isdisjoint(forbidden_roots)
