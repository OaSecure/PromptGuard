from app.infrastructure.ocr.failures import TesseractFailureReason
from app.infrastructure.ocr.process_port import OcrProcessRequest, OcrProcessResult
from app.infrastructure.ocr.temp_file import (
    SecureTemporaryFileProcessRunner,
    StagedOcrInput,
    TemporaryFileLifecycleError,
)


class FakeTemporaryFilePort:
    def __init__(self, *, stage_error: Exception | None = None, release_error: Exception | None = None) -> None:
        self.stage_error = stage_error
        self.release_error = release_error
        self.staged: list[tuple[str, int]] = []
        self.released: list[StagedOcrInput] = []

    def stage(self, image_handle: str, max_input_bytes: int) -> StagedOcrInput:
        self.staged.append((image_handle, max_input_bytes))
        if self.stage_error is not None:
            raise self.stage_error
        return StagedOcrInput(runtime_ref="opaque-runtime-ref")

    def release(self, staged_input: StagedOcrInput) -> None:
        self.released.append(staged_input)
        if self.release_error is not None:
            raise self.release_error


class FakeProcessRunner:
    def __init__(self, result: OcrProcessResult | None = None, error: Exception | None = None) -> None:
        self.result = result or OcrProcessResult(stdout="safe-output")
        self.error = error
        self.requests: list[OcrProcessRequest] = []

    def run(self, request: OcrProcessRequest) -> OcrProcessResult:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.result


def _request() -> OcrProcessRequest:
    return OcrProcessRequest(
        image_handle="PRIVATE_ORIGINAL_HANDLE:/PRIVATE_TEMP_PATH/original.png",
        argv=("/verified/tesseract", "stdin", "stdout", "tsv"),
        timeout_ms=500,
        max_input_bytes=1000,
        max_output_bytes=1000,
    )


def test_stages_opaque_input_and_releases_it_after_success():
    files = FakeTemporaryFilePort()
    process = FakeProcessRunner()

    result = SecureTemporaryFileProcessRunner(files, process).run(_request())

    assert result == OcrProcessResult(stdout="safe-output")
    assert files.staged == [(_request().image_handle, 1000)]
    assert process.requests[0].image_handle == "opaque-runtime-ref"
    assert files.released == [StagedOcrInput(runtime_ref="opaque-runtime-ref")]


def test_releases_staged_input_when_process_fails_or_raises():
    for process in (
        FakeProcessRunner(OcrProcessResult(failure_reason=TesseractFailureReason.TIMEOUT)),
        FakeProcessRunner(error=RuntimeError("PRIVATE_RAW_EXCEPTION:/PRIVATE_TEMP_PATH")),
    ):
        files = FakeTemporaryFilePort()
        result = SecureTemporaryFileProcessRunner(files, process).run(_request())
        assert files.released == [StagedOcrInput(runtime_ref="opaque-runtime-ref")]
        assert result.stdout == ""
        assert result.failure_reason in {
            TesseractFailureReason.TIMEOUT,
            TesseractFailureReason.PROCESS_SPAWN_FAILURE,
        }


def test_stage_failure_is_sanitized_and_does_not_call_process_or_release():
    files = FakeTemporaryFilePort(
        stage_error=TemporaryFileLifecycleError("PRIVATE_RAW_EXCEPTION:/PRIVATE_TEMP_PATH")
    )
    process = FakeProcessRunner()

    result = SecureTemporaryFileProcessRunner(files, process).run(_request())

    assert result == OcrProcessResult(
        exit_code=None,
        stdout="",
        failure_reason=TesseractFailureReason.TEMP_FILE_FAILURE,
    )
    assert process.requests == []
    assert files.released == []


def test_release_failure_discards_success_or_partial_output_and_is_sanitized():
    files = FakeTemporaryFilePort(
        release_error=TemporaryFileLifecycleError("PRIVATE_RAW_EXCEPTION:/PRIVATE_TEMP_PATH")
    )
    process = FakeProcessRunner(OcrProcessResult(stdout="PRIVATE_OCR_TEXT"))

    result = SecureTemporaryFileProcessRunner(files, process).run(_request())

    assert result == OcrProcessResult(
        exit_code=None,
        stdout="",
        failure_reason=TesseractFailureReason.TEMP_FILE_FAILURE,
    )
    assert files.released == [StagedOcrInput(runtime_ref="opaque-runtime-ref")]


def test_runtime_ref_never_appears_in_sanitized_lifecycle_failure():
    private_runtime_ref = "/PRIVATE_TEMP_PATH/generated-input.png"

    class PrivateRefPort(FakeTemporaryFilePort):
        def stage(self, image_handle: str, max_input_bytes: int) -> StagedOcrInput:
            return StagedOcrInput(runtime_ref=private_runtime_ref)

    result = SecureTemporaryFileProcessRunner(
        PrivateRefPort(release_error=RuntimeError(private_runtime_ref)),
        FakeProcessRunner(OcrProcessResult(stdout="PRIVATE_OCR_TEXT")),
    ).run(_request())

    assert private_runtime_ref not in repr(result)
    assert "PRIVATE_OCR_TEXT" not in repr(result)
