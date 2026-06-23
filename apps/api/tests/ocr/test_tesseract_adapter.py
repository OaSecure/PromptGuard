from app.domain.types.parser import OcrImageInput, OcrOptions
from app.infrastructure.ocr.failures import TesseractFailureReason
from app.infrastructure.ocr.process_port import OcrProcessRequest, OcrProcessResult
from app.infrastructure.ocr.tesseract_adapter import TesseractOcrEngine, parse_tesseract_tsv
from app.infrastructure.ocr.tesseract_preflight import TesseractPreflightConfig

TSV = "level\tpage_num\tleft\ttop\twidth\theight\tconf\ttext\n5\t1\t1\t2\t3\t4\t91\tverified text\n"


class FakeVerifier:
    def path_exists(self, path: str) -> bool:
        return True

    def checksum_matches(self, path: str, expected_sha256: str) -> bool:
        return True


class FakeRunner:
    def __init__(self, result: OcrProcessResult | None = None, error: Exception | None = None) -> None:
        self.result = result or OcrProcessResult(stdout=TSV)
        self.error = error
        self.requests: list[OcrProcessRequest] = []

    def run(self, request: OcrProcessRequest) -> OcrProcessResult:
        self.requests.append(request)
        if self.error:
            raise self.error
        return self.result


def _config(**updates: object) -> TesseractPreflightConfig:
    values = {
        "binary_path": "/opt/tesseract/bin/tesseract",
        "binary_sha256": "a" * 64,
        "tessdata_directory": "/opt/tesseract/tessdata",
        "traineddata_sha256": {"kor": "b" * 64},
        "language_allowlist": frozenset({"kor"}),
        "production_package_pin_verified": True,
        "native_dependency_pins_verified": True,
        "platform": "linux",
        "platform_binary_verified": True,
        "max_timeout_ms": 1000,
        "max_input_bytes": 1000,
        "max_output_bytes": 1000,
        "page_segmentation_mode": 6,
        "allowed_page_segmentation_modes": frozenset({3, 6}),
    }
    values.update(updates)
    return TesseractPreflightConfig(**values)  # type: ignore[arg-type]


def _recognize(runner: FakeRunner, config: TesseractPreflightConfig | None = None):
    engine = TesseractOcrEngine(config or _config(), FakeVerifier(), runner)
    return engine.recognize(OcrImageInput(image_handle="opaque-image", page=1), OcrOptions(languages=["kor"], timeout_ms=500))


def test_adapter_is_ocr_port_compatible_and_returns_parsed_tsv_blocks():
    runner = FakeRunner()
    result = _recognize(runner)
    assert result.status == "text_found"
    assert result.blocks[0].text == "verified text"
    request = runner.requests[0]
    assert isinstance(request.argv, tuple)
    assert request.argv == ("/opt/tesseract/bin/tesseract", "stdin", "stdout", "--tessdata-dir", "/opt/tesseract/tessdata", "-l", "kor", "--psm", "6", "tsv")
    assert request.shell is False
    assert request.allow_network_fallback is False
    assert request.allow_automatic_download is False


def test_preflight_failure_does_not_call_runner():
    runner = FakeRunner()
    result = _recognize(runner, _config(production_package_pin_verified=False))
    assert result.failure is not None
    assert result.failure.code == "OCR_ENGINE_UNAVAILABLE"
    assert runner.requests == []


def test_unsafe_page_segmentation_mode_fails_closed_before_process():
    runner = FakeRunner()
    result = _recognize(runner, _config(page_segmentation_mode=7))
    assert result.failure is not None
    assert result.failure.code == "OCR_ENGINE_UNAVAILABLE"
    assert runner.requests == []


def test_adapter_maps_timeout_spawn_network_and_exit_failures_to_existing_codes():
    cases = [
        (OcrProcessResult(failure_reason=TesseractFailureReason.TIMEOUT), None, "OCR_TIMEOUT"),
        (None, RuntimeError("private stderr"), "OCR_FAILED"),
        (OcrProcessResult(failure_reason=TesseractFailureReason.NETWORK_ATTEMPT), None, "OCR_FAILED"),
        (OcrProcessResult(exit_code=2), None, "OCR_FAILED"),
    ]
    for process_result, error, expected in cases:
        result = _recognize(FakeRunner(process_result, error))
        assert result.failure is not None
        assert result.failure.code == expected
        assert result.blocks == []


def test_adapter_fails_closed_for_malformed_and_oversized_partial_output():
    malformed = _recognize(FakeRunner(OcrProcessResult(stdout="partial secret")))
    oversized = _recognize(FakeRunner(OcrProcessResult(stdout=TSV)), _config(max_output_bytes=10))
    assert malformed.failure is not None and malformed.failure.code == "OCR_FAILED"
    assert oversized.failure is not None and oversized.failure.code == "OCR_FAILED"
    assert malformed.blocks == []
    assert oversized.blocks == []


def test_tsv_parser_returns_no_blocks_for_empty_output_and_rejects_invalid_rows():
    assert parse_tesseract_tsv("") == []
    invalid = "level\tpage_num\tleft\ttop\twidth\theight\tconf\ttext\n5\tbad\t1\t2\t3\t4\t90\ttext\n"
    try:
        parse_tesseract_tsv(invalid)
    except ValueError:
        pass
    else:
        raise AssertionError("malformed TSV must fail closed")
