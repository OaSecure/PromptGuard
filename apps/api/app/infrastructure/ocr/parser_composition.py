"""Internal parser-facing OCR engine selection seams.

This module intentionally does not register or activate production OCR. It only
centralizes the disabled-by-default choice between the current parser OCR engine
and an explicitly opted-in Tesseract composition candidate.
"""

from dataclasses import dataclass
from typing import Callable

from app.ports.ocr import OcrEnginePort

from .process_policy import ProcessExecutionPolicy
from .process_port import OcrProcessBackendPort
from .temp_file import OcrTemporaryFilePort
from .tesseract_composition import TesseractCompositionConfig, compose_tesseract_engine
from .tesseract_preflight import TesseractArtifactVerifierPort


@dataclass(frozen=True)
class ParserOcrEngineSelectionConfig:
    tesseract: TesseractCompositionConfig
    use_tesseract: bool = False


def select_parser_ocr_engine(
    config: ParserOcrEngineSelectionConfig,
    *,
    default_engine: OcrEnginePort,
    verifier: TesseractArtifactVerifierPort | None = None,
    temporary_files: OcrTemporaryFilePort | None = None,
    backend: OcrProcessBackendPort | None = None,
    backend_factory: Callable[[], OcrProcessBackendPort] | None = None,
    process_policy: ProcessExecutionPolicy | None = None,
) -> OcrEnginePort:
    if not config.use_tesseract:
        return default_engine
    return compose_tesseract_engine(
        config.tesseract,
        verifier=verifier,
        temporary_files=temporary_files,
        backend=backend,
        backend_factory=backend_factory,
        process_policy=process_policy,
    )
