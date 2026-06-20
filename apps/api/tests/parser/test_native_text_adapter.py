import logging

import pytest

from app.parser.adapters.native_text import NativeTextAdapter
from app.parser.executor import ParserPlanExecutor
from app.parser.models import (
    ParserAdapterCapability,
    ParserExecutionPlan,
    ParserPlanStep,
    ParserWorkerPayload,
    ResolvedTemporaryFile,
)
from app.parser.registry import InMemoryParserAdapterRegistry, ParserAdapterRegistration


PRIVATE_TEXT = "PRIVATE RAW TEXT"
PRIVATE_PATH = r"C:\private\original-secret.txt"
PRIVATE_EXCEPTION = "PRIVATE CONTENT SOURCE EXCEPTION"


class FakeResolvedFileContentSource:
    def __init__(self, content: bytes = b"", exception: Exception | None = None) -> None:
        self.content = content
        self.exception = exception
        self.calls: list[ResolvedTemporaryFile] = []

    def read(self, resolved_file: ResolvedTemporaryFile) -> bytes:
        self.calls.append(resolved_file)
        if self.exception is not None:
            raise self.exception
        return self.content


def _payload(input_id: str = "opaque-input-1") -> ParserWorkerPayload:
    return ParserWorkerPayload(
        input_id=input_id,
        request_id="request-1",
        input_kind="file_reference",
        extraction_requirement="native_parse",
        file_ref="opaque-file-ref",
        file_kind="plain_text",
        access_context={
            "authenticated_subject_id": "subject-1",
            "session_id": "session-1",
            "request_id": "request-1",
        },
    )


def _resolved_file() -> ResolvedTemporaryFile:
    return ResolvedTemporaryFile(
        file_ref="opaque-file-ref",
        file_kind="plain_text",
        local_runtime_ref=PRIVATE_PATH,
    )


def _step(step_kind: str = "native_text_extract", capability_id: str = "native-text-v1"):
    return ParserPlanStep(
        step_id="native-text",
        ordinal=0,
        step_kind=step_kind,
        capability_id=capability_id,
    )


def _exposed(result, caplog) -> str:
    failure = result.failure
    return " ".join((
        failure.message if failure else "",
        repr(failure.metadata) if failure else "",
        repr(result.document.metadata) if result.document else "",
        " ".join(block.block_id for block in result.document.blocks) if result.document else "",
        caplog.text,
    ))


def test_native_text_adapter_decodes_utf8_into_one_document_block():
    source = FakeResolvedFileContentSource("hello 한글".encode("utf-8"))

    result = NativeTextAdapter(source).execute_step(_step(), _payload(), _resolved_file())

    assert result.status == "success"
    assert result.document is not None
    assert result.document.input_id == "opaque-input-1"
    assert result.document.file_ref == "opaque-file-ref"
    assert result.document.file_type == "plain_text"
    assert len(result.document.blocks) == 1
    assert result.document.blocks[0].text == "hello 한글"
    assert result.document.blocks[0].block_id == "native-text-0"
    assert result.document.input_id not in result.document.blocks[0].block_id
    assert source.calls == [_resolved_file()]


def test_native_text_adapter_returns_empty_document_for_empty_content():
    result = NativeTextAdapter(FakeResolvedFileContentSource()).execute_step(
        _step(), _payload(), _resolved_file()
    )

    assert result.status == "success"
    assert result.document is not None
    assert result.document.blocks == []


@pytest.mark.parametrize(
    ("source", "expected_code"),
    [
        (FakeResolvedFileContentSource(b"\xff"), "TEXT_DECODE_FAILED"),
        (
            FakeResolvedFileContentSource(
                exception=RuntimeError(f"{PRIVATE_EXCEPTION} {PRIVATE_PATH} {PRIVATE_TEXT}")
            ),
            "PARSER_WORKER_FAILED",
        ),
    ],
)
def test_native_text_adapter_sanitizes_content_failures(source, expected_code, caplog):
    result = NativeTextAdapter(source).execute_step(_step(), _payload(), _resolved_file())

    assert result.status == "failed"
    assert result.failure is not None
    assert result.failure.code == expected_code
    exposed = _exposed(result, caplog)
    assert PRIVATE_TEXT not in exposed
    assert PRIVATE_PATH not in exposed
    assert PRIVATE_EXCEPTION not in exposed
    assert "b'\\xff'" not in exposed


def test_native_text_adapter_rejects_wrong_step_kind_without_reading_content():
    source = FakeResolvedFileContentSource(b"not read")

    result = NativeTextAdapter(source).execute_step(
        _step(step_kind="wrap_text"), _payload(), _resolved_file()
    )

    assert result.status == "failed"
    assert result.failure is not None
    assert result.failure.code == "UNSUPPORTED_FILE_KIND"
    assert source.calls == []


def test_registry_rejects_capability_mismatch():
    adapter = NativeTextAdapter(FakeResolvedFileContentSource(b"not read"))
    registry = InMemoryParserAdapterRegistry((ParserAdapterRegistration(
        ParserAdapterCapability(
            capability_id="native-text-v1",
            step_kinds=("native_text_extract",),
        ),
        adapter,
    ),))

    with pytest.raises(Exception) as error:
        registry.resolve_adapter("different-capability", "native_text_extract")

    assert str(error.value) == "UNSUPPORTED_FILE_KIND"


def test_registry_executor_native_text_adapter_returns_parsed_document(caplog):
    source = FakeResolvedFileContentSource(PRIVATE_TEXT.encode("utf-8"))
    adapter = NativeTextAdapter(source)
    registry = InMemoryParserAdapterRegistry((ParserAdapterRegistration(
        ParserAdapterCapability(
            capability_id="native-text-v1",
            step_kinds=("native_text_extract",),
        ),
        adapter,
    ),))
    plan = ParserExecutionPlan(
        plan_id="native-text",
        plan_kind="native_text",
        steps=(_step(),),
    )

    result = ParserPlanExecutor(registry).execute(_payload(), _resolved_file(), plan)

    assert result.parser_status == "parsed"
    assert result.document is not None
    assert result.document.blocks[0].text == PRIVATE_TEXT
    assert PRIVATE_TEXT not in result.document.blocks[0].block_id
    assert PRIVATE_PATH not in result.document.blocks[0].block_id
    assert caplog.text == ""
