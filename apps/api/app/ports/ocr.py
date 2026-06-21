from typing import Protocol

from app.domain.types.parser import OcrImageInput, OcrOptions, OcrResult


class OcrEnginePort(Protocol):
    engine_id: str

    def recognize(self, image: OcrImageInput, options: OcrOptions) -> OcrResult: ...


class PdfRendererPort(Protocol):
    def render_page(self, runtime_ref: str, page: int) -> OcrImageInput: ...
