import pytest

from app.parser.adapters.native_text import NativeTextAdapter
from app.parser.executor import ParserPlanExecutor
from app.parser.models import (
    ParserAdapterCapability,
    ParserBoundaryError,
    ParserWorkerPayload,
    ResolvedTemporaryFile,
    TempFileAccessContext,
    sanitized_failure,
)
from app.parser.planning import ParserPlanResolver
from app.parser.registry import InMemoryParserAdapterRegistry, ParserAdapterRegistration
from app.parser.runner import FileParserRunner


RAW_TEXT = "PRIVATE RAW TEXT"
RAW_BYTES = b"PRIVATE RAW BYTES"
LOCAL_RUNTIME_REF = "private-runtime-ref"
FILE_PATH = r"C:\private\original-secret.txt"
ORIGINAL_FILENAME = "original-secret.txt"
PRIVATE_EXCEPTION = "PRIVATE RESOLVER OR CONTENT EXCEPTION"


class FakeTemporaryFileResolver:
    def __init__(self, failure: bool = False) -> None:
        self.failure = failure

    def resolve(
        self, file_ref: str, access_context: TempFileAccessContext
    ) -> ResolvedTemporaryFile:
        if self.failure:
            raise ParserBoundaryError(sanitized_failure("TEMP_FILE_RESOLVE_FAILED"))
        return ResolvedTemporaryFile(
            file_ref=file_ref,
            file_kind="plain_text",
            local_runtime_ref=LOCAL_RUNTIME_REF,
        )


class FakeResolvedFileContentSource:
    def __init__(self, content: bytes = b"", failure: bool = False) -> None:
        self.content = content
        self.failure = failure

    def read(self, resolved_file: ResolvedTemporaryFile) -> bytes:
        if self.failure:
            raise RuntimeError(
                f"{PRIVATE_EXCEPTION} {resolved_file.local_runtime_ref} "
                f"{FILE_PATH} {ORIGINAL_FILENAME} {RAW_TEXT} {RAW_BYTES!r}"
            )
        return self.content


def _payload(file_ref: str = "opaque-file-ref") -> ParserWorkerPayload:
    return ParserWorkerPayload(
        input_id="opaque-input",
        request_id="opaque-request",
        input_kind="file_reference",
        extraction_requirement="native_parse",
        file_ref=file_ref,
        file_kind="plain_text",
        access_context=TempFileAccessContext(
            authenticated_subject_id="opaque-subject",
            session_id="opaque-session",
            request_id="opaque-request",
        ),
    )


def _runner(
    content: bytes = b"", *, resolver_failure: bool = False, content_failure: bool = False
) -> FileParserRunner:
    capability = ParserAdapterCapability(
        capability_id="native-text-v1",
        step_kinds=("native_text_extract",),
    )
    adapter = NativeTextAdapter(
        FakeResolvedFileContentSource(content=content, failure=content_failure)
    )
    registry = InMemoryParserAdapterRegistry((
        ParserAdapterRegistration(capability=capability, adapter=adapter),
    ))
    return FileParserRunner(
        temporary_file_resolver=FakeTemporaryFileResolver(failure=resolver_failure),
        plan_resolver=ParserPlanResolver(capabilities=(capability,)),
        plan_executor=ParserPlanExecutor(registry),
    )


def _exposed(result, caplog) -> str:
    failure = result.failure
    values = [
        failure.message if failure else "",
        repr(failure.metadata) if failure else "",
        repr(result.document.metadata) if result.document else "",
        " ".join(block.block_id for block in result.document.blocks)
        if result.document
        else "",
        caplog.text,
    ]
    return " ".join(values)


def _assert_private_values_hidden(result, caplog) -> None:
    exposed = _exposed(result, caplog)
    for private_value in (
        RAW_TEXT,
        RAW_BYTES.decode("ascii"),
        repr(RAW_BYTES),
        LOCAL_RUNTIME_REF,
        FILE_PATH,
        ORIGINAL_FILENAME,
        PRIVATE_EXCEPTION,
    ):
        assert private_value not in exposed


def test_file_parser_runner_native_text_vertical_slice_returns_parsed_document():
    result = _runner("hello 한글".encode("utf-8")).run(_payload())

    assert result.parser_status == "parsed"
    assert result.document is not None
    assert result.document.file_ref == "opaque-file-ref"
    assert result.document.file_type == "plain_text"
    assert len(result.document.blocks) == 1
    assert result.document.blocks[0].text == "hello 한글"
    assert result.document.blocks[0].block_id == "native-text-0"


def test_file_parser_runner_native_text_vertical_slice_accepts_empty_file():
    result = _runner(b"").run(_payload())

    assert result.parser_status == "parsed"
    assert result.document is not None
    assert result.document.blocks == []


def test_file_parser_runner_sanitizes_resolver_boundary_failure(caplog):
    result = _runner(resolver_failure=True).run(
        _payload(file_ref=f"opaque-ref-{ORIGINAL_FILENAME}")
    )

    assert result.parser_status == "failed"
    assert result.failure is not None
    assert result.failure.code == "TEMP_FILE_RESOLVE_FAILED"
    _assert_private_values_hidden(result, caplog)


def test_file_parser_runner_sanitizes_content_read_failure(caplog):
    result = _runner(RAW_BYTES, content_failure=True).run(_payload())

    assert result.parser_status == "failed"
    assert result.failure is not None
    assert result.failure.code == "PARSER_WORKER_FAILED"
    _assert_private_values_hidden(result, caplog)


def test_file_parser_runner_sanitizes_invalid_utf8_failure(caplog):
    invalid_utf8 = b"\xff\xfe" + RAW_BYTES

    result = _runner(invalid_utf8).run(_payload())

    assert result.parser_status == "failed"
    assert result.failure is not None
    assert result.failure.code == "TEXT_DECODE_FAILED"
    _assert_private_values_hidden(result, caplog)
    assert repr(invalid_utf8) not in _exposed(result, caplog)
