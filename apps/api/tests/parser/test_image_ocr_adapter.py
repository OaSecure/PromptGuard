from pathlib import Path

import pytest
from app.domain.types.parser import OcrResult, OcrTextBlock
from app.parser.adapters.image_ocr import ImageOcrAdapter
from app.parser.models import ParserPlanStep, ParserWorkerPayload, ResolvedTemporaryFile

PRIVATE_BYTES = b"PRIVATE_IMAGE_BYTES"
PRIVATE_PATH = r"C:\private\original-upload.png"
PRIVATE_EXCEPTION = "PRIVATE OCR EXCEPTION"


class FakeResolvedFileContentSource:
    def __init__(self, content: bytes = b"\x89PNG\r\n\x1a\n", exception: Exception | None = None) -> None:
        self.content = content
        self.exception = exception
        self.calls: list[ResolvedTemporaryFile] = []

    def read(self, resolved_file: ResolvedTemporaryFile) -> bytes:
        self.calls.append(resolved_file)
        if self.exception is not None:
            raise self.exception
        return self.content


class FakeOcrEngine:
    engine_id = "paddleocr-runtime"

    def __init__(self, result: OcrResult | None = None, exception: Exception | None = None) -> None:
        self.result = result or OcrResult(
            status="text_found",
            blocks=[OcrTextBlock(text="detected runtime text", confidence_bucket="high")],
            engine_id=self.engine_id,
        )
        self.exception = exception
        self.handles_seen: list[str] = []
        self.exists_during_call: list[bool] = []

    def recognize(self, image, options):
        self.handles_seen.append(image.image_handle)
        self.exists_during_call.append(Path(image.image_handle).is_file())
        assert options.languages == ["kor", "eng"]
        if self.exception is not None:
            raise self.exception
        return self.result


def _payload(file_kind: str = "image") -> ParserWorkerPayload:
    return ParserWorkerPayload(
        input_id="input-1",
        request_id="request-1",
        input_kind="file_reference",
        extraction_requirement="ocr_required",
        file_ref="opaque-file-ref",
        file_kind=file_kind,
        access_context={
            "authenticated_subject_id": "subject-1",
            "session_id": "session-1",
            "request_id": "request-1",
        },
    )


def _resolved_file(file_kind: str = "image") -> ResolvedTemporaryFile:
    return ResolvedTemporaryFile(
        file_ref="opaque-file-ref",
        file_kind=file_kind,
        local_runtime_ref=PRIVATE_PATH,
    )


def _step(step_kind: str = "image_ocr") -> ParserPlanStep:
    return ParserPlanStep(
        step_id="image-ocr-primary",
        ordinal=0,
        step_kind=step_kind,
        capability_id="image-ocr-v1",
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


def test_image_ocr_adapter_writes_runtime_temp_file_and_deletes_it_after_ocr():
    source = FakeResolvedFileContentSource()
    engine = FakeOcrEngine()

    result = ImageOcrAdapter(source, engine).execute_step(_step(), _payload(), _resolved_file())

    assert result.status == "success"
    assert result.document is not None
    assert result.document.parser_id == "paddleocr-runtime"
    assert result.document.file_type == "image"
    assert result.document.ocr_status == "text_found"
    assert result.document.blocks[0].text == "detected runtime text"
    assert result.document.blocks[0].source_type == "image_ocr"
    assert source.calls == [_resolved_file()]
    assert engine.exists_during_call == [True]
    assert engine.handles_seen and not Path(engine.handles_seen[0]).exists()


def test_image_ocr_adapter_returns_no_text_status_for_empty_ocr_result():
    result = ImageOcrAdapter(
        FakeResolvedFileContentSource(),
        FakeOcrEngine(OcrResult(status="no_text_detected", blocks=[], engine_id="paddleocr-runtime")),
    ).execute_step(_step(), _payload(), _resolved_file())

    assert result.status == "success"
    assert result.document is not None
    assert result.document.blocks == []
    assert result.document.ocr_status == "no_text_detected"


@pytest.mark.parametrize(
    ("payload", "resolved"),
    [
        (_payload(file_kind="plain_text"), _resolved_file()),
        (_payload(), _resolved_file(file_kind="plain_text")),
        (_payload(), None),
    ],
)
def test_image_ocr_adapter_rejects_non_image_shapes_without_reading_content(payload, resolved):
    source = FakeResolvedFileContentSource(PRIVATE_BYTES)

    result = ImageOcrAdapter(source, FakeOcrEngine()).execute_step(_step(), payload, resolved)

    assert result.status == "failed"
    assert result.failure is not None
    assert result.failure.code == "UNSUPPORTED_FILE_KIND"
    assert source.calls == []


@pytest.mark.parametrize(
    ("source", "engine", "expected_code"),
    [
        (
            FakeResolvedFileContentSource(exception=RuntimeError(f"{PRIVATE_EXCEPTION} {PRIVATE_PATH}")),
            FakeOcrEngine(),
            "OCR_FAILED",
        ),
        (
            FakeResolvedFileContentSource(PRIVATE_BYTES),
            FakeOcrEngine(exception=RuntimeError(f"{PRIVATE_EXCEPTION} {PRIVATE_PATH}")),
            "OCR_FAILED",
        ),
        (
            FakeResolvedFileContentSource(PRIVATE_BYTES),
            FakeOcrEngine(OcrResult(status="timeout", blocks=[], engine_id="paddleocr-runtime")),
            "OCR_TIMEOUT",
        ),
    ],
)
def test_image_ocr_adapter_sanitizes_failures(source, engine, expected_code, caplog):
    result = ImageOcrAdapter(source, engine).execute_step(_step(), _payload(), _resolved_file())

    assert result.status == "failed"
    assert result.failure is not None
    assert result.failure.code == expected_code
    exposed = _exposed(result, caplog)
    assert PRIVATE_BYTES.decode("utf-8") not in exposed
    assert PRIVATE_PATH not in exposed
    assert PRIVATE_EXCEPTION not in exposed
