"""Isolated OCR infrastructure adapters."""

from .tesseract_adapter import TesseractOcrEngine
from .tesseract_preflight import TesseractPreflightConfig

__all__ = ["TesseractOcrEngine", "TesseractPreflightConfig"]
