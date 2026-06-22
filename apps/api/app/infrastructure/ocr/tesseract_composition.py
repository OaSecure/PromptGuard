"""Disabled-safe composition for the injected Tesseract fake process stack."""

from dataclasses import dataclass

from app.domain.types.common import PipelineFailure
from app.domain.types.parser import OcrImageInput, OcrOptions, OcrResult

from .process_policy import ProcessExecutionPolicy
from .process_port import OcrProcessBackendPort
from .process_runner import PolicyBoundOcrProcessRunner
from .temp_file import OcrTemporaryFilePort, SecureTemporaryFileProcessRunner
from .tesseract_adapter import TesseractOcrEngine
from .tesseract_preflight import TesseractArtifactVerifierPort, TesseractPreflightConfig


@dataclass(frozen=True)
class TesseractCompositionConfig:
    enabled: bool
    preflight: TesseractPreflightConfig


class DisabledTesseractOcrEngine:
    engine_id = "tesseract-disabled"

    def recognize(self, image: OcrImageInput, options: OcrOptions) -> OcrResult:
        return OcrResult(
            status="failed",
            blocks=[],
            engine_id=self.engine_id,
            failure=PipelineFailure(
                code="OCR_ENGINE_UNAVAILABLE",
                message="OCR_ENGINE_UNAVAILABLE",
                retryable=False,
                module=self.engine_id,
            ),
        )


def compose_tesseract_engine(
    config: TesseractCompositionConfig,
    *,
    verifier: TesseractArtifactVerifierPort | None,
    temporary_files: OcrTemporaryFilePort | None,
    backend: OcrProcessBackendPort | None,
    process_policy: ProcessExecutionPolicy | None,
) -> TesseractOcrEngine | DisabledTesseractOcrEngine:
    if (
        not config.enabled
        or verifier is None
        or temporary_files is None
        or backend is None
        or process_policy is None
    ):
        return DisabledTesseractOcrEngine()

    process_runner = PolicyBoundOcrProcessRunner(backend, process_policy)
    secure_runner = SecureTemporaryFileProcessRunner(temporary_files, process_runner)
    return TesseractOcrEngine(config.preflight, verifier, secure_runner)
