from pathlib import Path
from tempfile import NamedTemporaryFile

from app.atoms.models import ParsedBlock, ParsedDocument
from app.domain.types.parser import OcrImageInput, OcrOptions, OcrResult
from app.parser.models import (
    FallbackTrigger,
    ParserPlanStep,
    ParserStepResult,
    ParserWorkerPayload,
    ResolvedTemporaryFile,
    sanitized_failure,
)
from app.parser.ports import ResolvedFileContentSourcePort
from app.ports.ocr import OcrEnginePort


class ImageOcrAdapter:
    def __init__(
        self,
        content_source: ResolvedFileContentSourcePort,
        ocr_engine: OcrEnginePort,
        *,
        timeout_ms: int = 60_000,
        languages: tuple[str, ...] = ("kor", "eng"),
    ) -> None:
        self._content_source = content_source
        self._ocr_engine = ocr_engine
        self._timeout_ms = timeout_ms
        self._languages = languages

    def execute_step(
        self,
        step: ParserPlanStep,
        payload: ParserWorkerPayload,
        resolved_file: ResolvedTemporaryFile | None,
    ) -> ParserStepResult:
        if not _supports_image_ocr(step, payload, resolved_file):
            return self._failure(step.step_id, "UNSUPPORTED_FILE_KIND")
        assert resolved_file is not None

        try:
            result = self._recognize(resolved_file)
        except Exception:
            return self._failure(step.step_id, "OCR_FAILED")

        if result.status == "timeout":
            return self._failure(step.step_id, "OCR_TIMEOUT", trigger="step_failed")
        if result.status == "failed":
            return self._failure(step.step_id, "OCR_FAILED")

        return ParserStepResult(
            step_id=step.step_id,
            status="success",
            document=_to_parsed_document(payload, result, self._ocr_engine.engine_id),
        )

    def _recognize(self, resolved_file: ResolvedTemporaryFile) -> OcrResult:
        image_path: Path | None = None
        try:
            image_path = self._write_runtime_image(self._content_source.read(resolved_file))
            return self._ocr_engine.recognize(
                OcrImageInput(image_handle=str(image_path), page=1),
                OcrOptions(languages=list(self._languages), timeout_ms=self._timeout_ms),
            )
        finally:
            if image_path is not None:
                image_path.unlink(missing_ok=True)

    @staticmethod
    def _write_runtime_image(content: bytes) -> Path:
        with NamedTemporaryFile(prefix="promptguard_ocr_", suffix=_image_suffix(content), delete=False) as handle:
            handle.write(content)
            return Path(handle.name)

    @staticmethod
    def _failure(step_id: str, code: str, *, trigger: FallbackTrigger = "step_failed") -> ParserStepResult:
        return ParserStepResult(
            step_id=step_id,
            status="failed",
            trigger=trigger,
            failure=sanitized_failure(code),
        )


def _supports_image_ocr(
    step: ParserPlanStep,
    payload: ParserWorkerPayload,
    resolved_file: ResolvedTemporaryFile | None,
) -> bool:
    return (
        step.step_kind in {"image_ocr", "ocr_fallback"}
        and payload.file_kind == "image"
        and resolved_file is not None
        and resolved_file.file_kind == "image"
    )


def _to_parsed_document(payload: ParserWorkerPayload, result: OcrResult, parser_id: str) -> ParsedDocument:
        blocks = [
            ParsedBlock(
                block_id=f"image-ocr-{index}",
                input_id=payload.input_id,
                text=block.text,
                source_type="image_ocr",
                location=block.location.model_dump(exclude_none=True) if block.location else None,
            )
            for index, block in enumerate(result.blocks)
            if block.text
        ]
        return ParsedDocument(
            input_id=payload.input_id,
            blocks=blocks,
            file_ref=payload.file_ref,
            file_type="image",
            parser_id=parser_id,
            parser_status="parsed",
            ocr_status="text_found" if blocks else "no_text_detected",
        )


def _image_suffix(content: bytes) -> str:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if content.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return ".webp"
    if content.startswith(b"BM"):
        return ".bmp"
    return ".img"
