"""Explicit, local-only smoke for one synthetic PaddleOCR image."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

API_ROOT = Path(__file__).parents[2]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.domain.types.parser import OcrImageInput, OcrOptions  # noqa: E402
from app.infrastructure.ocr.paddle_real_adapter import (  # noqa: E402
    PaddleOcrLazyRuntimeConfig,
    PaddleOcrLazyRuntimeSkeleton,
)
from app.infrastructure.ocr.paddle_runtime import PaddleOcrRuntimeConfig, compose_paddle_ocr_engine  # noqa: E402

OPT_IN_ENV = "PROMPTGUARD_RUN_PADDLEOCR_REAL_VALIDATION"
SAFE_REASON = "LOCAL_PADDLEOCR_SMOKE"
SYNTHETIC_TEXT = "TEST 123"


def _summary(
    status: str,
    stage: str,
    *,
    ocr_status: str = "not_run",
    blocks: int = 0,
    cleanup: bool = True,
    cuda_available: bool | None = None,
) -> dict[str, object]:
    return {
        "status": status,
        "stage_status": stage,
        "ocr_status": ocr_status,
        "ocr_block_count": blocks,
        "cuda_available": cuda_available,
        "cleanup_success": cleanup,
        "reason_code": SAFE_REASON,
        "readiness": status == "success",
        "production_activation": False,
    }


def run(*, local_only: bool, synthetic_only: bool) -> tuple[int, dict[str, object]]:
    if not local_only or not synthetic_only or os.environ.get(OPT_IN_ENV) != "1":
        return 2, _summary("blocked", "guard")

    temporary_path: Path | None = None
    cuda_available = None
    summary = _summary("failed", "preflight", cuda_available=cuda_available, cleanup=False)
    try:
        with tempfile.TemporaryDirectory(prefix="promptguard_paddleocr_smoke_") as directory:
            temporary_path = Path(directory)
            image_path = temporary_path / "synthetic.png"
            _write_synthetic_image(image_path)
            runtime = PaddleOcrLazyRuntimeSkeleton(
                PaddleOcrLazyRuntimeConfig(enabled=True),
                image_resolver=lambda handle: handle,
            )
            engine = compose_paddle_ocr_engine(PaddleOcrRuntimeConfig(enabled=True), runtime=runtime)
            result = engine.recognize(
                OcrImageInput(image_handle=str(image_path), page=1),
                OcrOptions(languages=["eng"], timeout_ms=120_000),
            )
            cuda_available = _paddle_cuda_available()
            summary = _summary(
                "success" if result.status == "text_found" and result.blocks else "failed",
                "ocr",
                ocr_status=result.status,
                blocks=len(result.blocks),
                cuda_available=cuda_available,
                cleanup=False,
            )
    except Exception:
        summary = _summary("failed", "ocr", cuda_available=cuda_available, cleanup=False)

    cleaned = temporary_path is None or not temporary_path.exists()
    summary["cleanup_success"] = cleaned
    return (0 if summary["status"] == "success" and cleaned else 1), summary


def _write_synthetic_image(path: Path) -> None:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (360, 120), "white")
    draw = ImageDraw.Draw(image)
    draw.text((24, 42), SYNTHETIC_TEXT, fill="black")
    image.save(path)


def _paddle_cuda_available() -> bool | None:
    try:
        import paddle

        return bool(paddle.device.is_compiled_with_cuda())
    except Exception:
        return None


@contextlib.contextmanager
def _suppress_probe_output() -> Iterator[None]:
    try:
        stdout_fd = sys.stdout.fileno()
        stderr_fd = sys.stderr.fileno()
    except (AttributeError, OSError, io.UnsupportedOperation):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            yield
        return

    saved_stdout = os.dup(stdout_fd)
    saved_stderr = os.dup(stderr_fd)
    try:
        with tempfile.TemporaryFile(mode="w+b") as sink:
            sys.stdout.flush()
            sys.stderr.flush()
            os.dup2(sink.fileno(), stdout_fd)
            os.dup2(sink.fileno(), stderr_fd)
            yield
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        os.dup2(saved_stdout, stdout_fd)
        os.dup2(saved_stderr, stderr_fd)
        os.close(saved_stdout)
        os.close(saved_stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run metadata-only local PaddleOCR smoke.")
    parser.add_argument("--local-only", action="store_true")
    parser.add_argument("--synthetic-only", action="store_true")
    args = parser.parse_args(argv)
    with _suppress_probe_output():
        code, summary = run(local_only=args.local_only, synthetic_only=args.synthetic_only)
    print(json.dumps(summary, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
