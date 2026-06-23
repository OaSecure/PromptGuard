import ast
from pathlib import Path

from app.domain.types.parser import OcrImageInput, OcrOptions
from app.infrastructure.ocr.process_port import OcrProcessRequest, OcrProcessResult
from app.infrastructure.ocr.tesseract_adapter import TesseractOcrEngine
from app.infrastructure.ocr.tesseract_preflight import TesseractPreflightConfig

API_ROOT = Path(__file__).parents[2]


class FakeVerifier:
    def path_exists(self, path: str) -> bool:
        return True

    def checksum_matches(self, path: str, expected_sha256: str) -> bool:
        return True


class SensitiveFailureRunner:
    def run(self, request: OcrProcessRequest) -> OcrProcessResult:
        raise RuntimeError("PRIVATE_STDERR_SENTINEL partial OCR text")


def _engine() -> TesseractOcrEngine:
    config = TesseractPreflightConfig(
        binary_path="/opt/tesseract/bin/tesseract",
        binary_sha256="a" * 64,
        tessdata_directory="/opt/tesseract/tessdata",
        traineddata_sha256={"kor": "b" * 64},
        language_allowlist=frozenset({"kor"}),
        production_package_pin_verified=True,
        native_dependency_pins_verified=True,
        platform="linux",
        platform_binary_verified=True,
        max_timeout_ms=1000,
        max_input_bytes=1000,
        max_output_bytes=1000,
    )
    return TesseractOcrEngine(config, FakeVerifier(), SensitiveFailureRunner())


def test_failure_does_not_expose_ocr_text_path_handle_or_subprocess_output(caplog):
    sensitive_handle = "PRIVATE_FILENAME_SENTINEL/customer-document.png"
    result = _engine().recognize(
        OcrImageInput(image_handle=sensitive_handle),
        OcrOptions(languages=["kor"], timeout_ms=500),
    )
    serialized = result.model_dump_json() + caplog.text
    for secret in ("PRIVATE_STDERR_SENTINEL", "partial OCR text", sensitive_handle):
        assert secret not in serialized
    assert result.blocks == []
    assert result.failure is not None
    assert result.failure.code == "OCR_FAILED"
    assert result.failure.message == "OCR_FAILED"
    assert result.failure.module == "tesseract-isolated"


def test_ocr_infrastructure_has_only_isolated_subprocess_and_no_download_install_or_cache():
    root = API_ROOT / "app" / "infrastructure" / "ocr"
    imported = set()
    source = ""
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        source += text.lower()
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
    subprocess_importers = []
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if any(
            isinstance(node, ast.Import) and any(alias.name == "subprocess" for alias in node.names)
            for node in ast.walk(tree)
        ):
            subprocess_importers.append(path.name)
    assert subprocess_importers == ["process_backend.py"]
    assert "pytesseract" not in imported
    assert "requests" not in imported
    assert "urllib" not in imported
    assert "pip install" not in source
    assert "download(" not in source
    assert "cache" not in source
    assert "subprocess.run" not in source
    assert "subprocess.call" not in source


def test_parser_and_production_runtime_do_not_register_concrete_tesseract_adapter():
    app_root = API_ROOT / "app"
    production_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in app_root.rglob("*.py")
        if "infrastructure/ocr" not in path.relative_to(app_root).as_posix()
    )
    assert "infrastructure.ocr" not in production_source
    assert "TesseractOcrEngine" not in production_source
