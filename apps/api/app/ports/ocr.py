from typing import Protocol

from app.domain.types.parser import OcrImageInput, OcrOptions, OcrResult


class OcrEnginePort(Protocol):
    def recognize(self, image: OcrImageInput, options: OcrOptions) -> OcrResult: ...
class PdfRendererPort(Protocol):
    def render_page(self, file_handle: str, page: int) -> OcrImageInput: ...
