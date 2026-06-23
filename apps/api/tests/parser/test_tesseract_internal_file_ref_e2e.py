import hashlib
import os
from pathlib import Path

import pytest
from app.domain.types.parser import OcrOptions
from app.infrastructure.ocr.parser_composition import select_parser_ocr_engine
from app.parser.adapters.pdf_ocr_fake import PdfSelectedPageOcrIntegrator
from app.parser.executor import ParserPlanExecutor
from app.parser.fakes import FakeOcrEngine
from app.parser.models import (
    FileParserResult,
    ParserAdapterCapability,
    ParserExecutionPlan,
    ParserPlanResolution,
    ParserPlanStep,
    ParserStepResult,
    ParserWorkerPayload,
    ResolvedTemporaryFile,
    TempFileAccessContext,
)
from app.parser.registry import InMemoryParserAdapterRegistry, ParserAdapterRegistration
from app.parser.runner import FileParserRunner
from test_tesseract_internal_opt_in_pdf_ocr import (
    RUN_REAL_VALIDATION_FLAG,
    TESSDATA_DIR_ENV,
    TESSERACT_BINARY_ENV,
    TESSERACT_LANG_ENV,
    TESSERACT_PSM_ENV,
    FakeBackend,
    FakeTempFiles,
    FakeVerifier,
    FileHashVerifier,
    LocalRenderedImageRenderer,
    _assert_not_exposed,
    _coverage,
    _native_document,
    _policy,
    _preflight,
    _selection_config,
)

FILE_REF = "opaque-internal-file-ref"
RUNTIME_REF = "PRIVATE_RUNTIME_REF"
CAPABILITY = ParserAdapterCapability(
    capability_id="internal-pdf-ocr-v1",
    step_kinds=("ocr_primary",),
)


class SyntheticTemporaryFileResolver:
    def __init__(self) -> None:
        self.calls: list[tuple[str, TempFileAccessContext]] = []

    def resolve(
        self, file_ref: str, access_context: TempFileAccessContext
    ) -> ResolvedTemporaryFile:
        self.calls.append((file_ref, access_context))
        return ResolvedTemporaryFile(
            file_ref=file_ref,
            file_kind="pdf",
            local_runtime_ref=RUNTIME_REF,
        )


class SyntheticPdfOcrPlanResolver:
    def __init__(self) -> None:
        self.resolved_files: list[ResolvedTemporaryFile | None] = []

    def resolve(self, request) -> ParserPlanResolution:
        self.resolved_files.append(request.resolved_file)
        return ParserPlanResolution(
            plan=ParserExecutionPlan(
                plan_id="internal-pdf-ocr",
                plan_kind="pdf_native_then_page_ocr",
                steps=(
                    ParserPlanStep(
                        step_id="ocr-primary",
                        ordinal=0,
                        step_kind="ocr_primary",
                        capability_id=CAPABILITY.capability_id,
                    ),
                ),
            )
        )


class InternalPdfOcrStepAdapter:
    def __init__(self, integrator: PdfSelectedPageOcrIntegrator) -> None:
        self._integrator = integrator
        self.resolved_files: list[ResolvedTemporaryFile | None] = []

    def execute_step(self, step, payload, resolved_file) -> ParserStepResult:
        self.resolved_files.append(resolved_file)
        if resolved_file is None:
            return ParserStepResult(step_id=step.step_id, status="failed")
        integrated = self._integrator.integrate(
            _native_document().model_copy(
                update={"input_id": payload.input_id, "file_ref": resolved_file.file_ref}
            ),
            resolved_file.local_runtime_ref,
            _coverage(),
            OcrOptions(languages=["eng"], timeout_ms=1000),
        )
        status = "partial" if integrated.failure is not None else "success"
        return ParserStepResult(
            step_id=step.step_id,
            status=status,
            document=integrated.document,
            failure=integrated.failure,
        )


def _payload() -> ParserWorkerPayload:
    return ParserWorkerPayload(
        input_id="internal-file-ref-input",
        request_id="internal-file-ref-request",
        input_kind="file_reference",
        extraction_requirement="native_parse_then_ocr_fallback",
        file_ref=FILE_REF,
        file_kind="pdf",
        access_context=TempFileAccessContext(
            authenticated_subject_id="internal-subject",
            session_id="internal-session",
            request_id="internal-file-ref-request",
        ),
    )


def _runner(renderer, engine):
    resolver = SyntheticTemporaryFileResolver()
    plan_resolver = SyntheticPdfOcrPlanResolver()
    adapter = InternalPdfOcrStepAdapter(PdfSelectedPageOcrIntegrator(renderer, engine))
    registry = InMemoryParserAdapterRegistry(
        (ParserAdapterRegistration(capability=CAPABILITY, adapter=adapter),)
    )
    runner = FileParserRunner(
        temporary_file_resolver=resolver,
        plan_resolver=plan_resolver,
        plan_executor=ParserPlanExecutor(registry),
    )
    return runner, resolver, plan_resolver, adapter


def _assert_runner_boundary(result: FileParserResult, resolver, plan_resolver, adapter) -> None:
    assert resolver.calls[0][0] == FILE_REF
    assert plan_resolver.resolved_files[0] is not None
    assert plan_resolver.resolved_files[0].local_runtime_ref == RUNTIME_REF
    assert adapter.resolved_files == plan_resolver.resolved_files
    assert result.document is not None
    assert result.document.file_ref == FILE_REF


def _non_text_surface(result: FileParserResult) -> dict:
    surface = result.model_dump()
    if surface["document"] is not None:
        for block in surface["document"]["blocks"]:
            block.pop("text", None)
    return surface


def test_internal_file_ref_runner_keeps_default_fake_engine_and_returns_document(tmp_path):
    default_engine = FakeOcrEngine(text_by_page={1: "default fake text"})
    backend = FakeBackend()
    engine = select_parser_ocr_engine(
        _selection_config(),
        default_engine=default_engine,
        verifier=FakeVerifier(),
        temporary_files=FakeTempFiles(),
        backend=backend,
        process_policy=_policy(),
    )
    renderer = LocalRenderedImageRenderer(tmp_path)
    runner, resolver, plan_resolver, adapter = _runner(renderer, engine)

    result = runner.run(_payload())

    _assert_runner_boundary(result, resolver, plan_resolver, adapter)
    assert backend.calls == 0
    assert [block.text for block in result.document.blocks if block.source_type == "pdf_ocr_page"] == [
        "default fake text"
    ]
    assert renderer.released


def test_internal_file_ref_runner_uses_tesseract_only_with_explicit_opt_in(tmp_path):
    backend = FakeBackend()
    temporary_files = FakeTempFiles()
    engine = select_parser_ocr_engine(
        _selection_config(use_tesseract=True, tesseract_enabled=True),
        default_engine=FakeOcrEngine(text_by_page={1: "must not use fake"}),
        verifier=FakeVerifier(),
        temporary_files=temporary_files,
        backend=backend,
        process_policy=_policy(),
    )
    renderer = LocalRenderedImageRenderer(tmp_path)
    runner, resolver, plan_resolver, adapter = _runner(renderer, engine)

    result = runner.run(_payload())

    _assert_runner_boundary(result, resolver, plan_resolver, adapter)
    assert backend.calls == 1
    assert [block.text for block in result.document.blocks if block.source_type == "pdf_ocr_page"] == [
        "internal opt in text"
    ]
    assert temporary_files.released == temporary_files.staged
    assert renderer.released
    surface = _non_text_surface(result)
    _assert_not_exposed(surface, *renderer.released)
    assert "internal opt in text" not in str(surface)


@pytest.mark.parametrize(
    ("verifier", "temporary_files"),
    [(None, FakeTempFiles()), (FakeVerifier(exists=False), FakeTempFiles()), (FakeVerifier(), None)],
)
def test_internal_file_ref_runner_fails_closed_before_backend_execution(
    tmp_path, verifier, temporary_files
):
    backend = FakeBackend()
    engine = select_parser_ocr_engine(
        _selection_config(use_tesseract=True, tesseract_enabled=True),
        default_engine=FakeOcrEngine(text_by_page={1: "must not use fake"}),
        verifier=verifier,
        temporary_files=temporary_files,
        backend=backend,
        process_policy=_policy(),
    )
    renderer = LocalRenderedImageRenderer(tmp_path)
    runner, resolver, plan_resolver, adapter = _runner(renderer, engine)

    result = runner.run(_payload())

    _assert_runner_boundary(result, resolver, plan_resolver, adapter)
    assert result.parser_status == "partial"
    assert result.failure is not None
    assert result.failure.code == "OCR_FAILED"
    assert backend.calls == 0
    assert renderer.released
    _assert_not_exposed(_non_text_surface(result), *renderer.released)


def test_local_only_internal_file_ref_runner_real_ocr_is_skip_by_default():
    if os.environ.get(RUN_REAL_VALIDATION_FLAG) != "1":
        pytest.skip(f"set {RUN_REAL_VALIDATION_FLAG}=1 to run local-only internal file_ref OCR")


def test_local_only_internal_file_ref_runner_returns_real_ocr_document(tmp_path):
    if os.environ.get(RUN_REAL_VALIDATION_FLAG) != "1":
        pytest.skip(f"set {RUN_REAL_VALIDATION_FLAG}=1 to run local-only internal file_ref OCR")
    binary = Path(os.environ.get(TESSERACT_BINARY_ENV, ""))
    tessdata = Path(os.environ.get(TESSDATA_DIR_ENV, ""))
    language = os.environ.get(TESSERACT_LANG_ENV, "eng")
    psm = os.environ.get(TESSERACT_PSM_ENV, "6")
    if not binary.exists() or not (tessdata / f"{language}.traineddata").exists():
        pytest.skip("configured local-only Tesseract artifacts are unavailable")
    renderer = LocalRenderedImageRenderer(tmp_path)
    temporary_files = FakeTempFiles()
    engine = select_parser_ocr_engine(
        _selection_config(
            use_tesseract=True,
            tesseract_enabled=True,
            preflight=_preflight(
                binary_path=str(binary),
                binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                tessdata_directory=str(tessdata),
                traineddata_sha256={
                    language: hashlib.sha256(
                        (tessdata / f"{language}.traineddata").read_bytes()
                    ).hexdigest()
                },
                language_allowlist=frozenset({language}),
                platform="windows",
                platform_binary_verified=True,
                max_timeout_ms=1000,
                page_segmentation_mode=int(psm),
            ),
        ),
        default_engine=FakeOcrEngine(text_by_page={1: "must not use fake"}),
        verifier=FileHashVerifier(),
        temporary_files=temporary_files,
        backend=None,
        process_policy=_policy(),
    )
    runner, resolver, plan_resolver, adapter = _runner(renderer, engine)

    result = runner.run(_payload())

    _assert_runner_boundary(result, resolver, plan_resolver, adapter)
    assert result.failure is None
    assert result.parser_status == "parsed"
    ocr_blocks = [block for block in result.document.blocks if block.source_type == "pdf_ocr_page"]
    assert " ".join(block.text for block in ocr_blocks) == "HELLO OCR"
    assert temporary_files.staged == renderer.released
    assert all(not Path(path).exists() for path in renderer.released)
    surface = _non_text_surface(result)
    _assert_not_exposed(surface, binary, tessdata, *renderer.released)
    assert "HELLO" not in str(surface)
    assert "OCR" not in str(surface)
