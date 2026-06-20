import pytest

from app.parser.fakes import FakeParserPlanExecutor, FakeParserPlanResolver, FakeTemporaryFileResolver
from app.parser.models import FileParserResult, ParserWorkerPayload, TempFileAccessContext
from app.parser.runner import FileParserRunner


def _context() -> TempFileAccessContext:
    return TempFileAccessContext(
        authenticated_subject_id="subject-1",
        session_id="session-1",
        request_id="request-1",
    )


def _file_payload() -> ParserWorkerPayload:
    return ParserWorkerPayload(
        input_id="file-1",
        request_id="request-1",
        input_kind="file_reference",
        extraction_requirement="native_parse",
        file_ref="opaque-ref-1",
        file_kind="unknown",
        access_context=_context(),
    )


def _text_payload() -> ParserWorkerPayload:
    return ParserWorkerPayload(
        input_id="text-1",
        request_id="request-1",
        input_kind="text_wrapper",
        extraction_requirement="wrap_text",
        text="hello",
    )


def _runner():
    resolver = FakeTemporaryFileResolver()
    plan_resolver = FakeParserPlanResolver()
    executor = FakeParserPlanExecutor()
    return FileParserRunner(resolver, plan_resolver, executor), resolver, plan_resolver, executor


def test_file_parser_runner_invokes_temp_file_resolver_inside_worker_runtime():
    runner, resolver, _, _ = _runner()
    runner.run(_file_payload())
    assert resolver.calls == [("opaque-ref-1", _context())]


def test_file_parser_runner_invokes_plan_resolver():
    runner, _, resolver, _ = _runner()
    payload = _file_payload()
    runner.run(payload)
    assert resolver.calls[0].payload == payload
    assert resolver.calls[0].resolved_file is not None


def test_file_parser_runner_invokes_plan_executor():
    runner, _, _, executor = _runner()
    payload = _file_payload()
    result = runner.run(payload)
    assert executor.calls[0].payload == payload
    assert result.parser_status == "parsed"


def test_text_wrapper_skips_temp_file_resolver():
    runner, resolver, plan_resolver, executor = _runner()
    result = runner.run(_text_payload())
    assert resolver.calls == []
    assert plan_resolver.calls[0].resolved_file is None
    assert executor.calls[0].resolved_file is None
    assert result.parser_status == "parsed"


@pytest.mark.parametrize("failure_owner", ["resolver", "plan_resolver", "executor"])
def test_runner_returns_structured_failure_from_collaborator(failure_owner: str):
    resolver = FakeTemporaryFileResolver(failure_code="TEMP_FILE_RESOLVE_FAILED" if failure_owner == "resolver" else None)
    plan_resolver = FakeParserPlanResolver(failure_code="PARSER_PLAN_RESOLVE_FAILED" if failure_owner == "plan_resolver" else None)
    executor = FakeParserPlanExecutor(failure_code="PARSER_EXECUTION_FAILED" if failure_owner == "executor" else None)
    runner = FileParserRunner(resolver, plan_resolver, executor)
    result = runner.run(_file_payload())
    assert isinstance(result, FileParserResult)
    assert result.failure is not None


def test_file_parser_runner_does_not_import_concrete_parser_libraries():
    import ast
    from pathlib import Path

    path = Path(__file__).parents[2] / "app" / "parser" / "runner.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = {
        alias.name.split(".")[0].lower()
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert imports.isdisjoint({"pypdf", "pypdfium2", "paddleocr", "pytesseract", "docx", "openpyxl", "pptx"})
