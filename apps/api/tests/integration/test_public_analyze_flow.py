import base64
import io
import json

import pytest
from app.atoms.models import ParsedBlock, ParsedDocument
from app.domain.types.parser import OcrResult, OcrTextBlock
from app.infrastructure.temp_storage import EncryptedTemporaryFileStorage
from app.parser.models import FileParserResult
from app.routes import analyze as analyze_route
from app.routes.temp_files import get_temp_storage
from app.runtime import parser_worker_factory
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject, NumberObject

from tests.contract.current_behavior.test_analyze_golden import (
    post_snapshot,
    rule,
    text,
)
from tests.test_analyze import _analyze_payload, _bearer_header, _client, _user


def _stable(value):
    value = json.loads(json.dumps(value, default=str))
    value.get("response", {}).pop("checked_at", None)
    value.get("response", {}).pop("event_id", None)
    return value


@pytest.mark.parametrize(
    ("action", "expected"),
    [("ALLOW", "Allow"), ("WARN", "Warn"), ("MASK", "Mask"), ("BLOCK", "Block")],
)
def test_public_analyze_actions_are_deterministic_and_storage_is_private(action, expected):
    rules = [] if action == "ALLOW" else [rule(action)]
    content = "ordinary deterministic note" if action == "ALLOW" else "snapshot marker"

    first = post_snapshot(rules, [text("input_1", content)])
    second = post_snapshot(rules, [text("input_1", content)])

    assert _stable(first) == _stable(second)
    assert first["response"]["action"] == expected
    serialized_storage = json.dumps(first["storage"], default=str)
    assert content not in serialized_storage
    assert "masked_prompt" not in serialized_storage


def test_converted_paste_mask_fails_closed_without_persisting_masked_prompt():
    actual = post_snapshot(
        [rule("MASK")],
        [text("paste_1", "snapshot marker", source="converted_paste")],
    )

    assert actual["response"]["action"] == "Block"
    assert "masked_prompt" not in actual["response"]
    assert "masked_prompt" not in json.dumps(actual["storage"], default=str)


def test_file_reference_http_boundary_warns_without_persisting_reference():
    user = _user()
    client, session = _client(user, rules=[])
    opaque_ref = "fref_abcdefghijklmnopqrstuvwxyzABCDEFG123456"
    temp_scope_id = "tscope_abcdefghijklmnopqrstuvwxyz123456"
    item = {
        "input_id": "file_1",
        "kind": "file_reference",
        "source": "attached_file",
        "size_bytes": 42,
        "content_included": False,
        "file_ref": opaque_ref,
        "temp_scope_id": temp_scope_id,
        "file_kind": "plain_text",
        "mime": "text/plain",
        "extension": "txt",
        "size_bucket": "tiny",
    }

    response = client.post(
        "/prompts/analyze",
        headers=_bearer_header(user.id),
        json=_analyze_payload(item),
    )

    assert response.status_code == 200
    assert response.json()["action"] == "Warn"
    assert response.json()["input_results"][0]["content_scanned"] is False
    persisted = json.dumps([getattr(row, "__dict__", {}) for row in session.added], default=str)
    assert opaque_ref not in persisted
    assert temp_scope_id not in persisted
    assert "size_bytes" not in persisted
    assert "masked_prompt" not in persisted


def test_file_reference_routes_through_parser_worker_without_persisting_runtime_text():
    user = _user()
    client, session = _client(user, rules=[])
    opaque_ref = "fref_abcdefghijklmnopqrstuvwxyzABCDEFG123456"
    temp_scope_id = "tscope_abcdefghijklmnopqrstuvwxyz123456"
    runtime_text = "runtime parsed admin@example.com"
    parser_pool = _FakeParserWorkerPool(runtime_text)
    client.app.dependency_overrides[analyze_route.get_parser_worker_pool] = lambda: parser_pool
    item = {
        "input_id": "file_1",
        "kind": "file_reference",
        "source": "attached_file",
        "size_bytes": 42,
        "content_included": False,
        "file_ref": opaque_ref,
        "temp_scope_id": temp_scope_id,
        "file_kind": "plain_text",
        "mime": "text/plain",
        "extension": "txt",
        "size_bucket": "tiny",
    }

    response = client.post(
        "/prompts/analyze",
        headers=_bearer_header(user.id),
        json=_analyze_payload(item),
    )

    body = response.json()
    assert response.status_code == 200
    assert body["action"] == "Block"
    assert body["input_results"][0]["content_scanned"] is True
    assert body["input_results"][0]["decision_basis"] == "detection"
    assert body["content_unavailable_inputs"] == []
    assert body["user_message"] == "Sensitive or governed content was detected and should not be sent."
    assert "masked_prompt" not in body
    assert body["detections"][0]["kind"] == "file_reference"
    assert parser_pool.payloads[0].file_ref == opaque_ref
    assert parser_pool.payloads[0].access_context.temp_scope_id == temp_scope_id
    encoded_body = json.dumps(body, ensure_ascii=False)
    persisted = json.dumps([getattr(row, "__dict__", {}) for row in session.added], default=str, ensure_ascii=False)
    assert runtime_text not in encoded_body
    assert runtime_text not in persisted
    assert opaque_ref not in persisted
    assert temp_scope_id not in persisted


def test_file_reference_default_parser_pool_reads_temp_storage_without_raw_persistence(tmp_path):
    user = _user()
    client, session = _client(user, rules=[])
    storage = EncryptedTemporaryFileStorage(tmp_path, base64.b64encode(b"K" * 32).decode(), 900)
    runtime_text = "runtime temp storage admin@example.com"
    stored = storage.store(
        runtime_text.encode(),
        subject_id=str(user.id),
        request_id="req_123",
        file_kind="plain_text",
        mime_hint="text/plain",
        extension_hint="txt",
        size_bucket="tiny",
    )
    client.app.dependency_overrides[get_temp_storage] = lambda: storage
    item = {
        "input_id": "file_1",
        "kind": "file_reference",
        "source": "attached_file",
        "size_bytes": 42,
        "content_included": False,
        "file_ref": stored["file_ref"],
        "temp_scope_id": stored["temp_scope_id"],
        "file_kind": "plain_text",
        "mime": "text/plain",
        "extension": "txt",
        "size_bucket": "tiny",
    }

    response = client.post(
        "/prompts/analyze",
        headers=_bearer_header(user.id),
        json=_analyze_payload(item),
    )

    body = response.json()
    persisted = json.dumps([getattr(row, "__dict__", {}) for row in session.added], default=str, ensure_ascii=False)
    assert response.status_code == 200
    assert body["input_results"][0]["content_scanned"] is True
    assert body["content_unavailable_inputs"] == []
    assert body["user_message"] == "Sensitive or governed content was detected and should not be sent."
    assert "masked_prompt" not in body
    assert body["detections"][0]["kind"] == "file_reference"
    assert runtime_text not in json.dumps(body, ensure_ascii=False)
    assert runtime_text not in persisted
    assert stored["file_ref"] not in persisted
    assert stored["temp_scope_id"] not in persisted


def test_pdf_file_reference_default_parser_pool_reads_native_text_without_raw_persistence(tmp_path):
    user = _user()
    client, session = _client(user, rules=[rule("WARN")])
    storage = EncryptedTemporaryFileStorage(tmp_path, base64.b64encode(b"K" * 32).decode(), 900)
    runtime_text = "snapshot marker " + ("native pdf filler " * 10)
    stored = storage.store(
        _synthetic_text_pdf(runtime_text),
        subject_id=str(user.id),
        request_id="req_123",
        file_kind="pdf",
        mime_hint="application/pdf",
        extension_hint="pdf",
        size_bucket="tiny",
    )
    client.app.dependency_overrides[get_temp_storage] = lambda: storage
    item = {
        "input_id": "pdf_1",
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
    assert body["detections"][0]["type"] == "SNAPSHOT_MARKER"
    assert body["detections"][0]["placeholder"] == "SNAPSHOT_MARKER"
    assert body["detections"][0]["reason_code"] == "CUSTOM_KEYWORD_SNAPSHOT_MARKER"
    assert runtime_text not in encoded_body
    assert runtime_text not in persisted
    assert stored["file_ref"] not in persisted
    assert stored["temp_scope_id"] not in persisted
    assert "original_filename" not in persisted


def test_scanned_pdf_file_reference_default_parser_pool_ocr_detects_fixture_text_without_raw_persistence(
    tmp_path, monkeypatch
):
    user = _user()
    client, session = _client(user, rules=[rule("WARN")])
    storage = EncryptedTemporaryFileStorage(tmp_path, base64.b64encode(b"K" * 32).decode(), 900)
    fixture_text = "SNAPSHOT MARKER"
    stored = storage.store(
        _synthetic_scanned_pdf(fixture_text),
        subject_id=str(user.id),
        request_id="req_123",
        file_kind="pdf",
        mime_hint="application/pdf",
        extension_hint="pdf",
        size_bucket="tiny",
    )
    monkeypatch.setattr(
        parser_worker_factory,
        "compose_paddle_ocr_engine",
        lambda *_args, **_kwargs: _FakeOcrEngine(fixture_text),
    )
    client.app.dependency_overrides[get_temp_storage] = lambda: storage
    item = {
        "input_id": "pdf_scan_1",
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

    response = client.post(
        "/prompts/analyze",
        headers=_bearer_header(user.id),
        json=_analyze_payload(item),
    )

    body = response.json()
    encoded_body = json.dumps(body, ensure_ascii=False)
    persisted = json.dumps([getattr(row, "__dict__", {}) for row in session.added], default=str, ensure_ascii=False)
    assert response.status_code == 200
    assert body["action"] == "Warn"
    assert body["input_results"][0]["content_scanned"] is True
    assert body["input_results"][0]["decision_basis"] == "detection"
    assert body["detections"][0]["kind"] == "file_reference"
    assert body["detections"][0]["type"] == "SNAPSHOT_MARKER"
    assert body["detections"][0]["placeholder"] == "SNAPSHOT_MARKER"
    assert body["detections"][0]["reason_code"] == "CUSTOM_KEYWORD_SNAPSHOT_MARKER"
    assert fixture_text not in encoded_body
    assert fixture_text not in persisted
    assert stored["file_ref"] not in persisted
    assert stored["temp_scope_id"] not in persisted
    assert "original_filename" not in persisted


def test_image_file_reference_default_parser_pool_uses_ocr_without_raw_persistence(tmp_path, monkeypatch):
    user = _user()
    client, session = _client(user, rules=[])
    storage = EncryptedTemporaryFileStorage(tmp_path, base64.b64encode(b"K" * 32).decode(), 900)
    raw_image_bytes = b"\x89PNG\r\n\x1a\nprivate-image-bytes"
    runtime_ocr_text = "runtime image OCR admin@example.com"
    stored = storage.store(
        raw_image_bytes,
        subject_id=str(user.id),
        request_id="req_123",
        file_kind="image",
        mime_hint="image/png",
        extension_hint="png",
        size_bucket="tiny",
    )
    monkeypatch.setattr(
        parser_worker_factory,
        "compose_paddle_ocr_engine",
        lambda *_args, **_kwargs: _FakeOcrEngine(runtime_ocr_text),
    )
    client.app.dependency_overrides[get_temp_storage] = lambda: storage
    item = {
        "input_id": "image_1",
        "kind": "file_reference",
        "source": "pasted_image",
        "size_bytes": 42,
        "content_included": False,
        "file_ref": stored["file_ref"],
        "temp_scope_id": stored["temp_scope_id"],
        "file_kind": "image",
        "mime": "image/png",
        "extension": "png",
        "size_bucket": "tiny",
    }

    response = client.post(
        "/prompts/analyze",
        headers=_bearer_header(user.id),
        json=_analyze_payload(item),
    )

    body = response.json()
    encoded_body = json.dumps(body, ensure_ascii=False)
    persisted = json.dumps([getattr(row, "__dict__", {}) for row in session.added], default=str, ensure_ascii=False)
    assert response.status_code == 200
    assert body["input_results"][0]["content_scanned"] is True
    assert body["input_results"][0]["decision_basis"] == "detection"
    assert body["detections"][0]["kind"] == "file_reference"
    assert runtime_ocr_text not in encoded_body
    assert runtime_ocr_text not in persisted
    assert "private-image-bytes" not in encoded_body
    assert "private-image-bytes" not in persisted
    assert stored["file_ref"] not in persisted
    assert stored["temp_scope_id"] not in persisted


class _FakeParserWorkerPool:
    def __init__(self, text: str) -> None:
        self.text = text
        self.payloads = []

    def execute(self, payload, timeout_ms):
        self.payloads.append(payload)
        return FileParserResult(
            input_id=payload.input_id,
            parser_status="parsed",
            document=ParsedDocument(
                input_id=payload.input_id,
                blocks=[ParsedBlock(block_id="block_1", input_id=payload.input_id, text=self.text)],
            ),
        )


class _FakeOcrEngine:
    engine_id = "fake-paddleocr"

    def __init__(self, text: str) -> None:
        self.text = text

    def recognize(self, image, options):
        return OcrResult(
            status="text_found",
            blocks=[OcrTextBlock(text=self.text, confidence_bucket="high")],
            engine_id=self.engine_id,
        )


def _synthetic_text_pdf(text: str) -> bytes:
    output = io.BytesIO()
    writer = PdfWriter()
    page = writer.add_blank_page(width=360, height=180)
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})
    })
    content = DecodedStreamObject()
    content.set_data(f"BT /F1 18 Tf 32 90 Td ({text}) Tj ET".encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(content)
    writer.write(output)
    return output.getvalue()


def _synthetic_scanned_pdf(text: str) -> bytes:
    output = io.BytesIO()
    writer = PdfWriter()
    page = writer.add_blank_page(width=360, height=160)
    width, height, pixels = _raster_text(text)
    image = DecodedStreamObject()
    image.set_data(pixels)
    image.update({
        NameObject("/Type"): NameObject("/XObject"),
        NameObject("/Subtype"): NameObject("/Image"),
        NameObject("/Width"): NumberObject(width),
        NameObject("/Height"): NumberObject(height),
        NameObject("/ColorSpace"): NameObject("/DeviceRGB"),
        NameObject("/BitsPerComponent"): NumberObject(8),
    })
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/XObject"): DictionaryObject({NameObject("/Im1"): writer._add_object(image)})
    })
    content = DecodedStreamObject()
    content.set_data(f"q {width} 0 0 {height} 32 64 cm /Im1 Do Q".encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(content)
    writer.write(output)
    return output.getvalue()


def _raster_text(text: str) -> tuple[int, int, bytes]:
    scale = 4
    glyph_w, glyph_h, gap = 5, 7, 1
    width = (len(text) * (glyph_w + gap) - gap) * scale
    height = glyph_h * scale
    canvas = bytearray([255] * width * height * 3)
    for char_index, character in enumerate(text.upper()):
        pattern = _FONT.get(character, _FONT[" "])
        x0 = char_index * (glyph_w + gap) * scale
        for row, bits in enumerate(pattern):
            for col, bit in enumerate(bits):
                if bit == "0":
                    continue
                for y in range(row * scale, (row + 1) * scale):
                    for x in range(x0 + col * scale, x0 + (col + 1) * scale):
                        offset = (y * width + x) * 3
                        canvas[offset:offset + 3] = b"\x00\x00\x00"
    return width, height, bytes(canvas)


_FONT = {
    " ": ("00000", "00000", "00000", "00000", "00000", "00000", "00000"),
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "C": ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
}
