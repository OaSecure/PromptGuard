import ast
from pathlib import Path

import pytest

from app.parser.adapters.office_foundation import OfficeParserFoundationAdapter
from app.parser.adapters.pdf_foundation import PdfParserFoundationAdapter
from app.parser.executor import ParserPlanExecutor
from app.parser.models import (
    ParserAdapterCapability,
    ParserExecutionPlan,
    ParserPlanStep,
    ParserWorkerPayload,
    ResolvedTemporaryFile,
    TempFileAccessContext,
)
from app.parser.planning import ParserPlanResolver
from app.parser.registry import InMemoryParserAdapterRegistry, ParserAdapterRegistration
from app.parser.runner import FileParserRunner


RAW_BYTES = b"PRIVATE RAW BYTES"
PRIVATE_PATH = r"C:\private\confidential-report.pdf"
ORIGINAL_FILENAME = "confidential-report.pdf"
FILE_REF = "private-file-ref"
RUNTIME_REF = "private-runtime-ref"
PRIVATE_EXCEPTION = "PRIVATE PARSER EXCEPTION"


class FakeResolvedFileContentSource:
    def __init__(self, content: bytes = b"", exception: Exception | None = None) -> None:
        self.content = content
        self.exception = exception

    def read(self, resolved_file: ResolvedTemporaryFile) -> bytes:
        if self.exception is not None:
            raise self.exception
        return self.content


class FakeTemporaryFileResolver:
    def __init__(self, file_kind: str) -> None:
        self.file_kind = file_kind

    def resolve(self, file_ref: str, access_context: TempFileAccessContext):
        return ResolvedTemporaryFile(
            file_ref=file_ref,
            file_kind=self.file_kind,
            local_runtime_ref=RUNTIME_REF,
        )


class FoundationPlanResolver:
    def __init__(self, plan_kind: str, step_kind: str, capability_id: str) -> None:
        self.plan = ParserExecutionPlan(
            plan_id=f"foundation-{plan_kind}",
            plan_kind=plan_kind,
            steps=(ParserPlanStep(
                step_id=f"foundation-{step_kind}",
                ordinal=0,
                step_kind=step_kind,
                capability_id=capability_id,
            ),),
        )

    def resolve(self, request):
        from app.parser.models import ParserPlanResolution

        return ParserPlanResolution(plan=self.plan)


def _payload(file_kind: str) -> ParserWorkerPayload:
    return ParserWorkerPayload(
        input_id="opaque-input",
        request_id="opaque-request",
        input_kind="file_reference",
        extraction_requirement="native_parse",
        file_ref=FILE_REF,
        file_kind=file_kind,
        access_context=TempFileAccessContext(
            authenticated_subject_id="opaque-subject",
            session_id="opaque-session",
            request_id="opaque-request",
        ),
    )


def _resolved_file(file_kind: str) -> ResolvedTemporaryFile:
    return ResolvedTemporaryFile(
        file_ref=FILE_REF,
        file_kind=file_kind,
        local_runtime_ref=RUNTIME_REF,
    )


def _step(step_kind: str, capability_id: str = "foundation-capability") -> ParserPlanStep:
    return ParserPlanStep(
        step_id=f"foundation-{step_kind}",
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


def _assert_private_values_hidden(result, caplog) -> None:
    exposed = _exposed(result, caplog)
    for value in (
        RAW_BYTES.decode("ascii"),
        repr(RAW_BYTES),
        PRIVATE_PATH,
        ORIGINAL_FILENAME,
        FILE_REF,
        RUNTIME_REF,
        PRIVATE_EXCEPTION,
    ):
        assert value not in exposed


def _assert_partial_foundation(result, file_type: str) -> None:
    assert result.status == "partial"
    assert result.failure is not None
    assert result.failure.code == "PARSER_NOT_IMPLEMENTED"
    assert result.document is not None
    assert result.document.file_type == file_type
    assert result.document.parser_status == "partial"
    assert result.document.ocr_status == "not_applicable"
    assert result.document.blocks == []
    assert result.document.metadata == {}


def test_plan_resolver_selects_pdf_and_office_paths():
    cases = (
        ("pdf", "pdf_native_then_page_ocr"),
        ("office_document", "office_parse"),
        ("spreadsheet", "spreadsheet_parse"),
        ("slide", "slide_parse"),
    )
    for file_kind, expected_plan_kind in cases:
        capabilities = tuple(
            ParserAdapterCapability(capability_id=f"cap-{kind}", step_kinds=(kind,))
            for kind in {
                "pdf_native_text_extract", "pdf_coverage_evaluate", "render_ocr_candidate_pages",
                "ocr_primary", "ocr_fallback", "merge_blocks", "office_parse",
                "spreadsheet_parse", "slide_parse",
            }
        )
        resolver = ParserPlanResolver(capabilities=capabilities)
        resolution = resolver.resolve(type("Request", (), {
            "payload": _payload(file_kind), "resolved_file": _resolved_file(file_kind)
        })())
        assert resolution.plan is not None
        assert resolution.plan.plan_kind == expected_plan_kind


def test_pdf_foundation_recognizes_pdf_container_as_partial():
    result = PdfParserFoundationAdapter(FakeResolvedFileContentSource(b"%PDF-1.7\nbody")).execute_step(
        _step("pdf_native_text_extract"), _payload("pdf"), _resolved_file("pdf")
    )
    _assert_partial_foundation(result, "pdf")


@pytest.mark.parametrize(
    ("file_kind", "step_kind"),
    [
        ("office_document", "office_parse"),
        ("spreadsheet", "spreadsheet_parse"),
        ("slide", "slide_parse"),
    ],
)
def test_office_native_adapter_rejects_invalid_docx_xlsx_pptx_containers(file_kind, step_kind):
    result = OfficeParserFoundationAdapter(FakeResolvedFileContentSource(b"PK\x03\x04container")).execute_step(
        _step(step_kind), _payload(file_kind), _resolved_file(file_kind)
    )
    assert result.status == "failed"
    assert result.failure is not None
    assert result.failure.code == "PARSER_WORKER_FAILED"


@pytest.mark.parametrize(
    ("adapter", "step_kind", "file_kind"),
    [
        (PdfParserFoundationAdapter(FakeResolvedFileContentSource()), "pdf_native_text_extract", "pdf"),
        (OfficeParserFoundationAdapter(FakeResolvedFileContentSource()), "office_parse", "office_document"),
        (OfficeParserFoundationAdapter(FakeResolvedFileContentSource()), "spreadsheet_parse", "spreadsheet"),
        (OfficeParserFoundationAdapter(FakeResolvedFileContentSource()), "slide_parse", "slide"),
    ],
)
def test_empty_container_follows_existing_parsed_empty_contract(adapter, step_kind, file_kind):
    result = adapter.execute_step(_step(step_kind), _payload(file_kind), _resolved_file(file_kind))
    assert result.status == "success"
    assert result.document is not None
    assert result.document.parser_status == "parsed"
    assert result.document.blocks == []
    assert result.document.metadata == {}


@pytest.mark.parametrize(
    ("adapter", "step_kind", "file_kind"),
    [
        (PdfParserFoundationAdapter(FakeResolvedFileContentSource(b"not-pdf")), "pdf_native_text_extract", "pdf"),
        (OfficeParserFoundationAdapter(FakeResolvedFileContentSource(b"not-office")), "office_parse", "office_document"),
        (OfficeParserFoundationAdapter(FakeResolvedFileContentSource(b"PK malformed")), "spreadsheet_parse", "spreadsheet"),
        (OfficeParserFoundationAdapter(FakeResolvedFileContentSource(b"not-office")), "slide_parse", "slide"),
    ],
)
def test_malformed_container_returns_sanitized_failure(adapter, step_kind, file_kind, caplog):
    result = adapter.execute_step(_step(step_kind), _payload(file_kind), _resolved_file(file_kind))
    assert result.status == "failed"
    assert result.failure is not None
    assert result.failure.code == "PARSER_WORKER_FAILED"
    _assert_private_values_hidden(result, caplog)


@pytest.mark.parametrize(
    ("adapter_type", "step_kind", "file_kind"),
    [
        (PdfParserFoundationAdapter, "pdf_native_text_extract", "pdf"),
        (OfficeParserFoundationAdapter, "office_parse", "office_document"),
    ],
)
def test_parser_exception_is_sanitized(adapter_type, step_kind, file_kind, caplog):
    exception = RuntimeError(
        f"{PRIVATE_EXCEPTION} {RAW_BYTES!r} {PRIVATE_PATH} {ORIGINAL_FILENAME} {FILE_REF} {RUNTIME_REF}"
    )
    result = adapter_type(FakeResolvedFileContentSource(exception=exception)).execute_step(
        _step(step_kind), _payload(file_kind), _resolved_file(file_kind)
    )
    assert result.status == "failed"
    assert result.failure is not None
    assert result.failure.code == "PARSER_WORKER_FAILED"
    _assert_private_values_hidden(result, caplog)


@pytest.mark.parametrize(
    ("adapter", "step_kind", "file_kind", "resolved_file", "expected_code"),
    [
        (PdfParserFoundationAdapter(FakeResolvedFileContentSource()), "office_parse", "pdf", _resolved_file("pdf"), "UNSUPPORTED_FILE_KIND"),
        (OfficeParserFoundationAdapter(FakeResolvedFileContentSource()), "office_parse", "pdf", _resolved_file("pdf"), "UNSUPPORTED_FILE_KIND"),
        (PdfParserFoundationAdapter(FakeResolvedFileContentSource()), "pdf_native_text_extract", "pdf", None, "PARSER_WORKER_FAILED"),
        (OfficeParserFoundationAdapter(FakeResolvedFileContentSource()), "office_parse", "office_document", None, "PARSER_WORKER_FAILED"),
        (PdfParserFoundationAdapter(FakeResolvedFileContentSource()), "pdf_native_text_extract", "pdf", _resolved_file("plain_text"), "PARSER_WORKER_FAILED"),
        (OfficeParserFoundationAdapter(FakeResolvedFileContentSource()), "office_parse", "office_document", _resolved_file("spreadsheet"), "PARSER_WORKER_FAILED"),
    ],
)
def test_mismatch_and_missing_resolved_file_are_distinct(
    adapter, step_kind, file_kind, resolved_file, expected_code
):
    result = adapter.execute_step(_step(step_kind), _payload(file_kind), resolved_file)
    assert result.status == "failed"
    assert result.failure is not None
    assert result.failure.code == expected_code


@pytest.mark.parametrize(
    ("adapter", "step_kind", "plan_kind", "file_kind", "content"),
    [
        (PdfParserFoundationAdapter(FakeResolvedFileContentSource(b"%PDF-1.7")), "pdf_native_text_extract", "pdf_native_then_page_ocr", "pdf", b"%PDF-1.7"),
        (OfficeParserFoundationAdapter(FakeResolvedFileContentSource(b"PK\x03\x04")), "office_parse", "office_parse", "office_document", b"PK\x03\x04"),
    ],
)
def test_runner_executor_registry_foundation_smoke(
    adapter, step_kind, plan_kind, file_kind, content
):
    capability = ParserAdapterCapability(
        capability_id="foundation-capability", step_kinds=(step_kind,)
    )
    registry = InMemoryParserAdapterRegistry((
        ParserAdapterRegistration(capability=capability, adapter=adapter),
    ))
    runner = FileParserRunner(
        FakeTemporaryFileResolver(file_kind),
        FoundationPlanResolver(plan_kind, step_kind, capability.capability_id),
        ParserPlanExecutor(registry),
    )
    result = runner.run(_payload(file_kind))
    if file_kind == "pdf":
        assert result.parser_status == "partial"
        assert result.failure is not None
        assert result.failure.code == "PARSER_NOT_IMPLEMENTED"
    else:
        assert result.parser_status == "failed"
        assert result.failure is not None
        assert result.failure.code == "PARSER_WORKER_FAILED"


def test_office_pdf_adapters_do_not_import_forbidden_pipeline_or_parser_dependencies():
    adapter_root = Path(__file__).parents[2] / "app" / "parser" / "adapters"
    forbidden = {
        "scanner", "normalization", "classifier", "verifier", "policy",
        "pypdf", "pypdfium2", "pdfplumber", "fitz", "docx", "openpyxl", "pptx",
    }
    for filename in ("pdf_foundation.py", "office_foundation.py"):
        tree = ast.parse((adapter_root / filename).read_text(encoding="utf-8"))
        imports = {
            alias.name.split(".")[0].lower()
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imports.update(
            node.module.split(".")[-1].lower()
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        )
        assert imports.isdisjoint(forbidden)
