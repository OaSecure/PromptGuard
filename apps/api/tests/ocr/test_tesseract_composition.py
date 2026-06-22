from app.domain.types.parser import OcrImageInput, OcrOptions
from app.infrastructure.ocr.process_policy import ProcessExecutionPolicy
from app.infrastructure.ocr.process_port import ProcessBoundaryResult, ProcessLifecycleState
from app.infrastructure.ocr.temp_file import StagedOcrInput
from app.infrastructure.ocr.tesseract_composition import TesseractCompositionConfig, compose_tesseract_engine
from app.infrastructure.ocr.tesseract_preflight import TesseractPreflightConfig

TSV = "level\tpage_num\tleft\ttop\twidth\theight\tconf\ttext\n5\t1\t1\t2\t3\t4\t91\tsafe text\n"
SENSITIVE = (
    "/PRIVATE_TEMP_PATH",
    "PRIVATE_ORIGINAL_FILENAME",
    "PRIVATE_OCR_TEXT",
    "PRIVATE_PARTIAL_OUTPUT",
    "PRIVATE_RAW_EXCEPTION",
    "PRIVATE_STDOUT",
    "PRIVATE_STDERR",
    "PRIVATE_RUNTIME_REF",
)


class FakeVerifier:
    def path_exists(self, path: str) -> bool:
        return True

    def checksum_matches(self, path: str, expected_sha256: str) -> bool:
        return True


class FakeTempFiles:
    def __init__(self, events: list[str], *, stage_error=None, release_error=None):
        self.events, self.stage_error, self.release_error = events, stage_error, release_error

    def stage(self, image_handle: str, max_input_bytes: int) -> StagedOcrInput:
        self.events.append("stage")
        if self.stage_error:
            raise self.stage_error
        return StagedOcrInput(runtime_ref="PRIVATE_RUNTIME_REF")

    def release(self, staged_input: StagedOcrInput) -> None:
        self.events.append("release")
        if self.release_error:
            raise self.release_error


class FakeBackend:
    def __init__(self, events: list[str], result=None, error=None):
        self.events, self.result, self.error = events, result, error

    def execute(self, request):
        self.events.append("process")
        if self.error:
            raise self.error
        return self.result or ProcessBoundaryResult(
            state=ProcessLifecycleState.EXITED, exit_code=0, stdout=TSV, input_bytes=10
        )


def _preflight() -> TesseractPreflightConfig:
    return TesseractPreflightConfig(
        "/fake/tesseract",
        "a" * 64,
        "/fake/tessdata",
        {"kor": "b" * 64},
        frozenset({"kor"}),
        True,
        True,
        "linux",
        True,
        1000,
        1000,
        1000,
    )


def _compose(*, enabled=True, files=True, backend=True, policy=True, events=None):
    events = events if events is not None else []
    process_policy = ProcessExecutionPolicy(frozenset({"LANG"}), {"LANG": "C.UTF-8"}) if policy is True else policy
    return compose_tesseract_engine(
        TesseractCompositionConfig(enabled=enabled, preflight=_preflight()),
        verifier=FakeVerifier() if files is not None else None,
        temporary_files=FakeTempFiles(events) if files is True else files,
        backend=FakeBackend(events) if backend is True else backend,
        process_policy=process_policy,
    )


def _recognize(engine):
    return engine.recognize(
        OcrImageInput(image_handle="PRIVATE_ORIGINAL_FILENAME:/PRIVATE_TEMP_PATH"),
        OcrOptions(languages=["kor"], timeout_ms=500),
    )


def test_enabled_fake_composition_preserves_stage_process_release_order():
    events = []
    result = _recognize(_compose(events=events))
    assert events == ["stage", "process", "release"]
    assert result.status == "text_found"


def test_disabled_composition_is_fail_safe_and_does_not_execute_ports():
    events = []
    result = _recognize(_compose(enabled=False, events=events))
    assert events == []
    assert result.failure is not None and result.failure.code == "OCR_ENGINE_UNAVAILABLE"


def test_missing_required_port_is_fail_safe():
    for files, backend, policy in ((None, True, True), (True, None, True), (True, True, None)):
        result = _recognize(_compose(files=files, backend=backend, policy=policy))
        assert result.failure is not None and result.failure.code == "OCR_ENGINE_UNAVAILABLE"


def test_stage_process_release_and_partial_output_failures_are_sanitized():
    cases = (
        (FakeTempFiles([], stage_error=RuntimeError(":".join(SENSITIVE))), FakeBackend([])),
        (FakeTempFiles([]), FakeBackend([], error=RuntimeError(":".join(SENSITIVE)))),
        (
            FakeTempFiles([], release_error=RuntimeError(":".join(SENSITIVE))),
            FakeBackend(
                [],
                ProcessBoundaryResult(state=ProcessLifecycleState.EXITED, exit_code=0, stdout="PRIVATE_PARTIAL_OUTPUT"),
            ),
        ),
        (
            FakeTempFiles([]),
            FakeBackend(
                [],
                ProcessBoundaryResult(
                    state=ProcessLifecycleState.EXITED, exit_code=2, stdout="PRIVATE_STDOUT", stderr="PRIVATE_STDERR"
                ),
            ),
        ),
        (
            FakeTempFiles([]),
            FakeBackend(
                [],
                ProcessBoundaryResult(state=ProcessLifecycleState.EXITED, exit_code=0, stdout="PRIVATE_PARTIAL_OUTPUT"),
            ),
        ),
    )
    for files, backend in cases:
        result = _recognize(_compose(files=files, backend=backend))
        serialized = result.model_dump_json()
        assert result.blocks == []
        assert all(value not in serialized for value in SENSITIVE)
