from app.domain.types.parser import OcrOptions
from app.infrastructure.ocr.failures import TesseractFailureReason
from app.infrastructure.ocr.tesseract_preflight import TesseractPreflightConfig, validate_preflight


class FakeVerifier:
    def __init__(self, *, missing: set[str] | None = None, mismatched: set[str] | None = None) -> None:
        self.missing = missing or set()
        self.mismatched = mismatched or set()

    def path_exists(self, path: str) -> bool:
        return path not in self.missing

    def checksum_matches(self, path: str, expected_sha256: str) -> bool:
        return path not in self.mismatched and bool(expected_sha256)


def _config(**updates: object) -> TesseractPreflightConfig:
    values = {
        "binary_path": "/opt/tesseract/bin/tesseract",
        "binary_sha256": "a" * 64,
        "tessdata_directory": "/opt/tesseract/tessdata",
        "traineddata_sha256": {"kor": "b" * 64, "eng": "c" * 64},
        "language_allowlist": frozenset({"kor", "eng"}),
        "production_package_pin_verified": True,
        "native_dependency_pins_verified": True,
        "platform": "linux",
        "platform_binary_verified": True,
        "max_timeout_ms": 1000,
        "max_input_bytes": 1000,
        "max_output_bytes": 1000,
    }
    values.update(updates)
    return TesseractPreflightConfig(**values)  # type: ignore[arg-type]


def test_valid_preflight_accepts_explicit_pinned_artifacts_and_allowed_languages():
    assert validate_preflight(_config(), OcrOptions(languages=["kor", "eng"], timeout_ms=500), FakeVerifier()) is None


def test_preflight_rejects_missing_binary_and_traineddata():
    binary = "/opt/tesseract/bin/tesseract"
    traineddata = "/opt/tesseract/tessdata/kor.traineddata"
    assert validate_preflight(_config(), OcrOptions(languages=["kor"], timeout_ms=500), FakeVerifier(missing={binary})) is TesseractFailureReason.BINARY_MISSING
    assert validate_preflight(_config(), OcrOptions(languages=["kor"], timeout_ms=500), FakeVerifier(missing={traineddata})) is TesseractFailureReason.TRAINEDDATA_MISSING


def test_preflight_rejects_unsupported_language_checksum_and_pin_failures():
    options = OcrOptions(languages=["kor"], timeout_ms=500)
    assert validate_preflight(_config(), OcrOptions(languages=["fra"], timeout_ms=500), FakeVerifier()) is TesseractFailureReason.UNSUPPORTED_LANGUAGE
    assert validate_preflight(_config(), options, FakeVerifier(mismatched={"/opt/tesseract/bin/tesseract"})) is TesseractFailureReason.CHECKSUM_MISMATCH
    assert validate_preflight(_config(native_dependency_pins_verified=False), options, FakeVerifier()) is TesseractFailureReason.NATIVE_PIN_MISMATCH


def test_preflight_requires_absolute_paths_bounded_values_and_verified_windows_binary():
    options = OcrOptions(languages=["kor"], timeout_ms=500)
    assert validate_preflight(_config(binary_path="tesseract"), options, FakeVerifier()) is TesseractFailureReason.INVALID_PATH
    assert validate_preflight(_config(max_output_bytes=0), options, FakeVerifier()) is TesseractFailureReason.INVALID_PATH
    assert validate_preflight(_config(), OcrOptions(languages=["kor"], timeout_ms=1001), FakeVerifier()) is TesseractFailureReason.TIMEOUT
    windows = _config(platform="windows", platform_binary_verified=False)
    assert validate_preflight(windows, options, FakeVerifier()) is TesseractFailureReason.UNVERIFIED_WINDOWS_BINARY
