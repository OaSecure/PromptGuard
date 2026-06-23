"""Explicit, local-only smoke for one synthetic Tesseract OCR image."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

API_ROOT = Path(__file__).parents[2]
TESTS_ROOT = API_ROOT / "tests"
sys.path.insert(0, str(API_ROOT))
sys.path.insert(0, str(TESTS_ROOT / "parser"))
sys.path.insert(0, str(TESTS_ROOT / "ocr"))

from app.domain.types.parser import OcrOptions  # noqa: E402
from app.infrastructure.ocr.parser_composition import select_parser_ocr_engine  # noqa: E402
from app.parser.adapters.pdf_ocr_fake import PdfSelectedPageOcrIntegrator  # noqa: E402
from app.parser.fakes import FakeOcrEngine  # noqa: E402
from test_tesseract_internal_opt_in_pdf_ocr import (  # noqa: E402
    FileHashVerifier,
    LocalRenderedImageRenderer,
    _coverage,
    _native_document,
    _policy,
    _preflight,
    _selection_config,
)
from test_tesseract_isolated_real_run_validation import SYNTHETIC_HELLO_OCR_PNG  # noqa: E402

OPT_IN_ENV = "PROMPTGUARD_RUN_TESSERACT_REAL_VALIDATION"
BINARY_ENV = "PROMPTGUARD_TESSERACT_BINARY"
TESSDATA_ENV = "PROMPTGUARD_TESSERACT_TESSDATA_DIR"
LANG_ENV = "PROMPTGUARD_TESSERACT_LANG"
PSM_ENV = "PROMPTGUARD_TESSERACT_PSM"
SAFE_REASON = "LOCAL_TESSERACT_SMOKE"


class LocalInputLifecycle:
    def __init__(self) -> None:
        self.released = False

    def stage(self, image_handle: str, max_input_bytes: int):
        from app.infrastructure.ocr.temp_file import StagedOcrInput

        return StagedOcrInput(runtime_ref=image_handle)

    def release(self, staged_input) -> None:
        self.released = True


def _summary(status: str, stage: str, blocks: int, cleanup: bool) -> dict[str, object]:
    return {
        "status": status,
        "stage_status": stage,
        "ocr_block_count": blocks,
        "cleanup_success": cleanup,
        "reason_code": SAFE_REASON,
        "readiness": status == "success",
    }


def run(*, local_only: bool, synthetic_only: bool) -> tuple[int, dict[str, object]]:
    if not local_only or not synthetic_only or os.environ.get(OPT_IN_ENV) != "1":
        return 2, _summary("blocked", "guard", 0, True)

    temporary_path: Path | None = None
    result_summary = _summary("failed", "preflight", 0, False)
    try:
        binary = Path(os.environ[BINARY_ENV])
        tessdata = Path(os.environ[TESSDATA_ENV])
        language = os.environ.get(LANG_ENV, "eng")
        psm = int(os.environ.get(PSM_ENV, "6"))
        traineddata = tessdata / f"{language}.traineddata"
        binary_sha = hashlib.sha256(binary.read_bytes()).hexdigest()
        traineddata_sha = hashlib.sha256(traineddata.read_bytes()).hexdigest()

        with tempfile.TemporaryDirectory(prefix="promptguard_tesseract_smoke_") as directory:
            temporary_path = Path(directory)
            image = temporary_path / "synthetic.png"
            image.write_bytes(base64.b64decode(SYNTHETIC_HELLO_OCR_PNG))
            lifecycle = LocalInputLifecycle()
            engine = select_parser_ocr_engine(
                _selection_config(
                    use_tesseract=True,
                    tesseract_enabled=True,
                    preflight=_preflight(
                        binary_path=str(binary),
                        binary_sha256=binary_sha,
                        tessdata_directory=str(tessdata),
                        traineddata_sha256={language: traineddata_sha},
                        language_allowlist=frozenset({language}),
                        platform="windows",
                        platform_binary_verified=True,
                        page_segmentation_mode=psm,
                    ),
                ),
                default_engine=FakeOcrEngine(text_by_page={1: "unused"}),
                verifier=FileHashVerifier(),
                temporary_files=lifecycle,
                backend=None,
                process_policy=_policy(),
            )
            renderer = LocalRenderedImageRenderer(temporary_path)
            result = PdfSelectedPageOcrIntegrator(renderer, engine).integrate(
                _native_document(),
                "synthetic-local-only-ref",
                _coverage(),
                OcrOptions(languages=[language], timeout_ms=1000),
            )
            blocks = [] if result.document is None else [
                block for block in result.document.blocks if block.source_type == "pdf_ocr_page"
            ]
            if result.failure is not None:
                result_summary = _summary("failed", "ocr", 0, False)
            else:
                result_summary = _summary("success", "ocr", len(blocks), False)
    except Exception:
        result_summary = _summary("failed", "preflight", 0, False)

    cleaned = temporary_path is None or not temporary_path.exists()
    result_summary["cleanup_success"] = cleaned
    return (0 if result_summary["status"] == "success" and cleaned else 1), result_summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--local-only", action="store_true")
    parser.add_argument("--synthetic-only", action="store_true")
    args = parser.parse_args(argv)
    code, summary = run(local_only=args.local_only, synthetic_only=args.synthetic_only)
    print(json.dumps(summary, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
