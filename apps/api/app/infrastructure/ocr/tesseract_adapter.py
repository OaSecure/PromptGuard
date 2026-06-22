import csv
import io
from typing import Literal

from app.domain.types.common import PipelineFailure
from app.domain.types.parser import BlockLocation, OcrImageInput, OcrOptions, OcrResult, OcrTextBlock

from .failures import TesseractFailureReason, public_failure_code
from .process_port import OcrProcessRequest, OcrProcessRunnerPort
from .tesseract_preflight import TesseractArtifactVerifierPort, TesseractPreflightConfig, validate_preflight


class TesseractOcrEngine:
    engine_id = "tesseract-isolated"

    def __init__(
        self,
        config: TesseractPreflightConfig,
        verifier: TesseractArtifactVerifierPort,
        runner: OcrProcessRunnerPort,
    ) -> None:
        self._config = config
        self._verifier = verifier
        self._runner = runner

    def recognize(self, image: OcrImageInput, options: OcrOptions) -> OcrResult:
        reason = validate_preflight(self._config, options, self._verifier)
        if reason is not None:
            return self._failure(reason)
        request = OcrProcessRequest(
            image_handle=image.image_handle,
            argv=self._safe_argv(options.languages),
            timeout_ms=options.timeout_ms,
            max_input_bytes=self._config.max_input_bytes,
            max_output_bytes=self._config.max_output_bytes,
        )
        try:
            result = self._runner.run(request)
        except Exception:
            return self._failure(TesseractFailureReason.PROCESS_SPAWN_FAILURE)
        if result.failure_reason is not None:
            return self._failure(result.failure_reason)
        if result.exit_code != 0:
            return self._failure(TesseractFailureReason.UNEXPECTED_EXIT)
        if len(result.stdout.encode("utf-8")) > self._config.max_output_bytes:
            return self._failure(TesseractFailureReason.OUTPUT_LIMIT_EXCEEDED)
        try:
            blocks = parse_tesseract_tsv(result.stdout)
        except ValueError:
            return self._failure(TesseractFailureReason.MALFORMED_OUTPUT)
        return OcrResult(
            status="text_found" if blocks else "no_text_detected",
            blocks=blocks,
            engine_id=self.engine_id,
        )

    def _safe_argv(self, languages: list[str]) -> tuple[str, ...]:
        return (
            self._config.binary_path,
            "stdin",
            "stdout",
            "--tessdata-dir",
            self._config.tessdata_directory,
            "-l",
            "+".join(languages),
            "tsv",
        )

    def _failure(self, reason: TesseractFailureReason) -> OcrResult:
        code = public_failure_code(reason)
        status: Literal["timeout", "failed"] = "timeout" if code == "OCR_TIMEOUT" else "failed"
        return OcrResult(
            status=status,
            blocks=[],
            engine_id=self.engine_id,
            failure=PipelineFailure(
                code=code,
                message=code,
                retryable=code in {"OCR_TIMEOUT", "OCR_FAILED"},
                module="tesseract-isolated",
            ),
        )


def parse_tesseract_tsv(output: str) -> list[OcrTextBlock]:
    if not output:
        return []
    reader = csv.DictReader(io.StringIO(output), delimiter="\t")
    required = {"level", "page_num", "left", "top", "width", "height", "conf", "text"}
    if reader.fieldnames is None or not required.issubset(reader.fieldnames):
        raise ValueError("invalid tesseract output")
    blocks: list[OcrTextBlock] = []
    try:
        for row in reader:
            text = row["text"].strip()
            if not text:
                continue
            confidence = float(row["conf"])
            page = int(row["page_num"])
            blocks.append(OcrTextBlock(
                text=text,
                confidence_bucket=_confidence_bucket(confidence),
                location=BlockLocation(page=page if page > 0 else None),
            ))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("invalid tesseract output") from exc
    return blocks


def _confidence_bucket(confidence: float) -> Literal["low", "medium", "high", "unknown"]:
    if confidence < 0:
        return "unknown"
    if confidence < 50:
        return "low"
    if confidence < 80:
        return "medium"
    return "high"
