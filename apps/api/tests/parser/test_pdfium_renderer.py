import logging
import io

import pytest
from pypdf import PdfWriter

from app.infrastructure.pdf.pdfium_renderer import PdfiumRenderer, PdfRendererError


class Source:
    def __init__(self):
        self.calls = []

    def read(self, runtime_ref):
        self.calls.append(runtime_ref)
        return b"%PDF-synthetic"


class Store:
    def __init__(self):
        self.items = {}
        self.released = []

    def put(self, page, width, height, stride, pixel_format, buffer):
        handle = f"rendered-{page}"
        self.items[handle] = bytes(buffer)
        return handle

    def release(self, handle):
        self.released.append(handle)
        self.items.pop(handle, None)


class Resource:
    def __init__(self, value=None, fail=False):
        self.value = value
        self.fail = fail
        self.closed = False

    def close(self):
        self.closed = True


class Bitmap(Resource):
    width = 2
    height = 2
    stride = 8
    buffer = b"0123456789abcdef"
    mode = "BGRA"


class Page(Resource):
    def __init__(self, bitmap, fail=False):
        super().__init__(fail=fail)
        self.bitmap = bitmap

    def render(self, scale):
        if self.fail:
            raise RuntimeError("PRIVATE_RENDER_EXCEPTION C:\\private\\secret.pdf")
        return self.bitmap


class Document(Resource):
    def __init__(self, pages):
        super().__init__()
        self.pages = pages

    def __len__(self):
        return len(self.pages)

    def __getitem__(self, index):
        return self.pages[index]


class Pdfium:
    def __init__(self, document):
        self.document = document

    def PdfDocument(self, content):
        return self.document


def _renderer(document):
    source, store = Source(), Store()
    return PdfiumRenderer(source, store, pdfium_module=Pdfium(document)), source, store


def test_selected_pages_render_in_ascending_order_with_one_based_indexes():
    bitmaps = [Bitmap(), Bitmap(), Bitmap()]
    pages = [Page(bitmap) for bitmap in bitmaps]
    document = Document(pages)
    renderer, source, store = _renderer(document)
    images = renderer.render_selected_pages("PRIVATE_RUNTIME_REF", (3, 1))
    assert [image.page for image in images] == [1, 3]
    assert [image.image_handle for image in images] == ["rendered-1", "rendered-3"]
    assert source.calls == ["PRIVATE_RUNTIME_REF"]
    assert pages[1].closed is False
    assert pages[0].closed and pages[2].closed
    assert bitmaps[0].closed and bitmaps[2].closed
    assert document.closed


def test_unselected_page_is_never_opened_or_rendered():
    selected, unselected = Page(Bitmap()), Page(Bitmap())
    renderer, _, _ = _renderer(Document([selected, unselected]))
    renderer.render_selected_pages("runtime", (1,))
    assert selected.closed
    assert unselected.closed is False


@pytest.mark.parametrize("page", [0, 3])
def test_invalid_page_raises_sanitized_pdf_render_failure(page):
    renderer, _, _ = _renderer(Document([Page(Bitmap()), Page(Bitmap())]))
    with pytest.raises(PdfRendererError) as error:
        renderer.render_selected_pages("runtime", (page,))
    assert error.value.failure.code == "PDF_RENDER_FAILED"
    assert error.value.failure.metadata == {"failure_code": "PDF_RENDER_FAILED"}


def test_mid_render_failure_cleans_resources_and_sanitizes_logs(caplog):
    caplog.set_level(logging.ERROR)
    first_bitmap = Bitmap()
    first, second = Page(first_bitmap), Page(Bitmap(), fail=True)
    document = Document([first, second])
    renderer, _, store = _renderer(document)
    with pytest.raises(PdfRendererError) as error:
        renderer.render_selected_pages("PRIVATE_RUNTIME_REF", (1, 2))
    assert first.closed and second.closed and first_bitmap.closed and document.closed
    assert store.items == {}
    exposed = error.value.failure.message + repr(error.value.failure.metadata) + caplog.text
    for forbidden in ("PRIVATE_RENDER_EXCEPTION", "secret.pdf", "PRIVATE_RUNTIME_REF", "image_bytes", "base64"):
        assert forbidden not in exposed


def test_release_removes_runtime_only_rendered_image():
    renderer, _, store = _renderer(Document([Page(Bitmap())]))
    image = renderer.render_page("runtime", 1)
    assert image.image_handle in store.items
    renderer.release(image)
    assert image.image_handle not in store.items


def test_real_pdfium_renders_synthetic_blank_pdf_without_path_or_pillow():
    output = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(output)
    source, store = Source(), Store()
    source.read = lambda runtime_ref: output.getvalue()
    renderer = PdfiumRenderer(source, store, scale=1)
    image = renderer.render_page("runtime-only-ref", 1)
    assert image.page == 1
    assert store.items[image.image_handle]
    renderer.release(image)
    assert store.items == {}
