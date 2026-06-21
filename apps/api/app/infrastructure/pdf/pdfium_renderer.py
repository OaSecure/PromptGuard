import logging
import secrets
from typing import Any, Protocol

import pypdfium2

from app.domain.types.parser import OcrImageInput
from app.parser.models import sanitized_failure


logger = logging.getLogger(__name__)


class RuntimePdfSourcePort(Protocol):
    def read(self, runtime_ref: str) -> bytes: ...


class RenderedImageStorePort(Protocol):
    def put(
        self,
        page: int,
        width: int,
        height: int,
        stride: int,
        pixel_format: str,
        buffer: bytes,
    ) -> str: ...

    def release(self, handle: str) -> None: ...


class RenderedImage:
    def __init__(
        self, width: int, height: int, stride: int, pixel_format: str, buffer: bytes
    ) -> None:
        self.width = width
        self.height = height
        self.stride = stride
        self.pixel_format = pixel_format
        self.buffer = buffer


class InMemoryRenderedImageStore:
    def __init__(self) -> None:
        self._images: dict[str, RenderedImage] = {}

    def put(
        self,
        page: int,
        width: int,
        height: int,
        stride: int,
        pixel_format: str,
        buffer: bytes,
    ) -> str:
        handle = f"rendered-image-{secrets.token_urlsafe(18)}"
        self._images[handle] = RenderedImage(width, height, stride, pixel_format, bytes(buffer))
        return handle

    def get(self, handle: str) -> RenderedImage:
        return self._images[handle]

    def release(self, handle: str) -> None:
        self._images.pop(handle, None)


class PdfRendererError(Exception):
    def __init__(self) -> None:
        self.failure = sanitized_failure("PDF_RENDER_FAILED")
        super().__init__(self.failure.code)


class PdfiumRenderer:
    def __init__(
        self,
        source: RuntimePdfSourcePort,
        image_store: RenderedImageStorePort,
        *,
        scale: float = 2.0,
        pdfium_module: Any = pypdfium2,
    ) -> None:
        self._source = source
        self._image_store = image_store
        self._scale = scale
        self._pdfium = pdfium_module

    def render_page(self, runtime_ref: str, page: int) -> OcrImageInput:
        return self.render_selected_pages(runtime_ref, (page,))[0]

    def render_selected_pages(
        self, runtime_ref: str, selected_pages: tuple[int, ...] | list[int]
    ) -> tuple[OcrImageInput, ...]:
        document = None
        stored_handles: list[str] = []
        try:
            content = self._source.read(runtime_ref)
            document = self._pdfium.PdfDocument(content)
            ordered_pages = tuple(sorted(set(selected_pages)))
            if any(page < 1 or page > len(document) for page in ordered_pages):
                raise PdfRendererError()
            results = []
            for page_index in ordered_pages:
                page = None
                bitmap = None
                try:
                    page = document[page_index - 1]
                    bitmap = page.render(scale=self._scale)
                    handle = self._image_store.put(
                        page_index,
                        bitmap.width,
                        bitmap.height,
                        bitmap.stride,
                        bitmap.mode,
                        bytes(bitmap.buffer),
                    )
                    stored_handles.append(handle)
                    results.append(OcrImageInput(image_handle=handle, page=page_index))
                finally:
                    if bitmap is not None:
                        bitmap.close()
                    if page is not None:
                        page.close()
            return tuple(results)
        except PdfRendererError:
            self._release_all(stored_handles)
            raise
        except Exception:
            self._release_all(stored_handles)
            logger.error("PDF page rendering failed", extra={"failure_code": "PDF_RENDER_FAILED"})
            raise PdfRendererError() from None
        finally:
            if document is not None:
                document.close()

    def release(self, image: OcrImageInput) -> None:
        self._image_store.release(image.image_handle)

    def _release_all(self, handles: list[str]) -> None:
        for handle in handles:
            self._image_store.release(handle)
