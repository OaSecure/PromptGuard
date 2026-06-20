import ast
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest
from pydantic import ValidationError

from app.parser.fakes import FakeFileParserRunner
from app.parser.models import FileParserResult, ParserWorkerPayload, TempFileAccessContext
from app.runtime.parser_worker import ParserWorkerPool


def _text_payload(**overrides) -> ParserWorkerPayload:
    values = {
        "input_id": "input-1",
        "request_id": "request-1",
        "input_kind": "text_wrapper",
        "extraction_requirement": "wrap_text",
        "text": "representative text",
    }
    values.update(overrides)
    return ParserWorkerPayload(**values)


def test_parser_worker_pool_invokes_file_parser_runner():
    runner = FakeFileParserRunner()
    pool = ParserWorkerPool(runner=runner, max_workers=1, max_queue_size=1)

    result = pool.execute(_text_payload(), timeout_ms=100)

    assert result.parser_status == "parsed"
    assert runner.payloads == [_text_payload()]
    pool.shutdown()


def test_parser_worker_payload_contains_coarse_extraction_requirement_only():
    fields = set(ParserWorkerPayload.model_fields)

    assert "extraction_requirement" in fields
    assert fields.isdisjoint({"parser_id", "adapter_id", "plan", "steps", "fallback_rules"})


@pytest.mark.parametrize("field", ["raw_bytes", "original_filename", "temp_path", "ocr_text", "extracted_text"])
def test_parser_worker_payload_rejects_forbidden_content_fields(field: str):
    with pytest.raises(ValidationError):
        _text_payload(**{field: "PRIVATE_SENTINEL"})


def test_text_wrapper_accepts_empty_text_boundary():
    assert _text_payload(text="").text == ""


def test_file_reference_accepts_unknown_file_kind():
    payload = ParserWorkerPayload(
        input_id="input-2",
        request_id="request-2",
        input_kind="file_reference",
        extraction_requirement="native_parse",
        file_ref="opaque-ref-123",
        file_kind="unknown",
        access_context=TempFileAccessContext(
            authenticated_subject_id="subject-1",
            session_id="session-1",
            request_id="request-2",
        ),
    )
    assert payload.file_kind == "unknown"


def test_file_reference_requires_file_ref():
    with pytest.raises(ValidationError):
        ParserWorkerPayload(
            input_id="input-2",
            request_id="request-2",
            input_kind="file_reference",
            extraction_requirement="native_parse",
            file_kind="unknown",
        )


def test_parser_worker_payload_rejects_unsupported_extraction_requirement():
    with pytest.raises(ValidationError):
        _text_payload(extraction_requirement="invented_requirement")


def test_parser_worker_pool_returns_structured_failure_on_timeout():
    pool = ParserWorkerPool(runner=FakeFileParserRunner(delay_seconds=0.02), max_workers=1, max_queue_size=1)

    result = pool.execute(_text_payload(), timeout_ms=1)

    assert result.parser_status == "timeout"
    assert result.failure is not None
    assert result.failure.code == "PARSER_TIMEOUT"
    pool.shutdown()


def test_parser_worker_pool_uses_registered_failure_when_capacity_is_exceeded():
    release = Event()

    class BlockingRunner:
        def run(self, payload):
            release.wait(timeout=1)
            return FileParserResult(input_id=payload.input_id, parser_status="parsed")

    pool = ParserWorkerPool(runner=BlockingRunner(), max_workers=1, max_queue_size=1)
    with ThreadPoolExecutor(max_workers=2) as callers:
        first = callers.submit(pool.execute, _text_payload(input_id="first"), 500)
        second = callers.submit(pool.execute, _text_payload(input_id="second"), 500)
        result = pool.execute(_text_payload(input_id="third"), timeout_ms=100)
        release.set()
        first.result()
        second.result()

    assert result.parser_status == "failed"
    assert result.failure is not None
    assert result.failure.code == "PARSER_LIMIT_EXCEEDED"
    pool.shutdown()


def test_timeout_ms_minimum_boundary():
    pool = ParserWorkerPool(runner=FakeFileParserRunner(), max_workers=1, max_queue_size=1)
    assert pool.execute(_text_payload(), timeout_ms=1).parser_status == "parsed"
    with pytest.raises(ValueError):
        pool.execute(_text_payload(), timeout_ms=0)
    pool.shutdown()


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_parser_worker_pool_does_not_import_concrete_parser_libraries():
    path = Path(__file__).parents[2] / "app" / "runtime" / "parser_worker.py"
    imports = _imports(path)
    forbidden = {"pypdf", "pypdfium2", "paddleocr", "pytesseract", "docx", "openpyxl", "pptx"}
    assert not {name for name in imports if name.split(".")[0].lower() in forbidden}


def test_parser_worker_pool_does_not_select_adapter_directly():
    path = Path(__file__).parents[2] / "app" / "runtime" / "parser_worker.py"
    source = path.read_text(encoding="utf-8").lower()
    assert "adapter" not in source


def test_parser_worker_pool_result_has_no_policy_fields():
    assert set(FileParserResult.model_fields).isdisjoint(
        {"action", "recommended_action", "reason_code", "user_notice"}
    )
