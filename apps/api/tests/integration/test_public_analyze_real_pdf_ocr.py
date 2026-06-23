import base64
import contextlib
import io
import json
import os
import sys
import tempfile
from collections.abc import Iterator
from uuid import UUID

import pytest
from app.infrastructure.temp_storage import EncryptedTemporaryFileStorage
from app.models.filters import FilterRule
from app.routes import analyze as analyze_route
from app.routes.temp_files import get_temp_storage
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject, NumberObject

from tests.test_analyze import _analyze_payload, _bearer_header, _client, _user


@pytest.mark.skipif(
    os.getenv("PROMPTGUARD_RUN_REAL_API_OCR_TESTS") != "1",
    reason="real API OCR integration is opt-in",
)
@pytest.mark.filterwarnings("ignore:No ccache found.*:UserWarning")
def test_public_analyze_scanned_pdf_file_reference_uses_real_paddleocr_without_raw_persistence(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("PROMPTGUARD_ML_INFERENCE_QUEUE_TIMEOUT_MS", "120000")
    analyze_route.get_settings.cache_clear()
    user = _user()
    client, session = _client(user, rules=[_keyword_rule("WARN")])
    storage = EncryptedTemporaryFileStorage(tmp_path, base64.b64encode(b"K" * 32).decode(), 900)
    marker_text = "ORION"
    stored = storage.store(
        _synthetic_scanned_pdf(marker_text),
        subject_id=str(user.id),
        request_id="req_123",
        file_kind="pdf",
        mime_hint="application/pdf",
        extension_hint="pdf",
        size_bucket="tiny",
    )
    client.app.dependency_overrides[get_temp_storage] = lambda: storage
    item = {
        "input_id": "pdf_real_ocr",
        "kind": "file_reference",
        "source": "attached_file",
        "size_bytes": 42,
        "content_included": False,
        "file_ref": stored["file_ref"],
        "temp_scope_id": stored["temp_scope_id"],
        "file_kind": "pdf",
        "mime": "application/pdf",
        "extension": "pdf",
        "size_bucket": "tiny",
    }

    with _suppress_native_output():
        response = client.post(
            "/prompts/analyze",
            headers=_bearer_header(user.id),
            json=_analyze_payload(item),
        )

    body = response.json()
    persisted = json.dumps([getattr(row, "__dict__", {}) for row in session.added], default=str, ensure_ascii=False)
    encoded_body = json.dumps(body, ensure_ascii=False)

    assert response.status_code == 200
    assert body["action"] == "Warn"
    assert body["input_results"][0]["content_scanned"] is True
    assert body["input_results"][0]["decision_basis"] == "detection"
    assert body["detections"][0]["kind"] == "file_reference"
    assert body["detections"][0]["action"] == "Warn"
    assert body["detections"][0]["type"] == "PDF_OCR_MARKER"
    assert body["detections"][0]["placeholder"] == "PDF_OCR_MARKER"
    assert body["detections"][0]["reason_code"] == "CUSTOM_KEYWORD_PDF_OCR_MARKER"
    assert marker_text.casefold() not in encoded_body.casefold()
    assert marker_text.casefold() not in persisted.casefold()
    assert stored["file_ref"] not in persisted
    assert stored["temp_scope_id"] not in persisted
    assert "original_filename" not in persisted
    assert "ocr_text" not in encoded_body.casefold()
    assert "ocr_text" not in persisted.casefold()


def _keyword_rule(action: str) -> FilterRule:
    return FilterRule(
        id=UUID("20000000-0000-0000-0000-000000000001"),
        origin="custom",
        kind="keyword",
        category="Custom",
        label="Pdf OCR marker",
        keyword="orion",
        placeholder="PDF_OCR_MARKER",
        severity="high",
        action=action,
        enabled=True,
        editable_fields={"enabled": True},
        version=1,
    )


@contextlib.contextmanager
def _suppress_native_output() -> Iterator[None]:
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


def _synthetic_scanned_pdf(text: str) -> bytes:
    Image = pytest.importorskip("PIL.Image")
    ImageDraw = pytest.importorskip("PIL.ImageDraw")
    ImageFont = pytest.importorskip("PIL.ImageFont")

    width = 1200
    height = 320
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    font_path = "C:/Windows/Fonts/arial.ttf"
    font = ImageFont.truetype(font_path, 104) if os.path.exists(font_path) else None
    draw.text((80, 96), text, fill="black", font=font)

    output = io.BytesIO()
    writer = PdfWriter()
    page = writer.add_blank_page(width=720, height=260)
    pdf_image = DecodedStreamObject()
    pdf_image.set_data(image.tobytes())
    pdf_image.update({
        NameObject("/Type"): NameObject("/XObject"),
        NameObject("/Subtype"): NameObject("/Image"),
        NameObject("/Width"): NumberObject(width),
        NameObject("/Height"): NumberObject(height),
        NameObject("/ColorSpace"): NameObject("/DeviceRGB"),
        NameObject("/BitsPerComponent"): NumberObject(8),
    })
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/XObject"): DictionaryObject({NameObject("/Im1"): writer._add_object(pdf_image)})
    })
    content = DecodedStreamObject()
    content.set_data(b"q 620 0 0 165 50 52 cm /Im1 Do Q")
    page[NameObject("/Contents")] = writer._add_object(content)
    writer.write(output)
    return output.getvalue()
