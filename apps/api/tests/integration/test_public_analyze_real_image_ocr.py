import base64
import contextlib
import io
import json
import os
import sys
import tempfile
from collections.abc import Iterator

import pytest
from app.infrastructure.temp_storage import EncryptedTemporaryFileStorage
from app.routes import analyze as analyze_route
from app.routes.temp_files import get_temp_storage

from tests.contract.current_behavior.test_analyze_golden import rule
from tests.test_analyze import _analyze_payload, _bearer_header, _client, _user


@pytest.mark.skipif(
    os.getenv("PROMPTGUARD_RUN_REAL_API_OCR_TESTS") != "1",
    reason="real API OCR integration is opt-in",
)
@pytest.mark.filterwarnings("ignore:No ccache found.*:UserWarning")
def test_public_analyze_image_file_reference_uses_real_paddleocr_without_raw_persistence(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTGUARD_ML_INFERENCE_QUEUE_TIMEOUT_MS", "120000")
    analyze_route.get_settings.cache_clear()
    user = _user()
    client, session = _client(user, rules=[rule("WARN")])
    storage = EncryptedTemporaryFileStorage(tmp_path, base64.b64encode(b"K" * 32).decode(), 900)
    image_bytes = _synthetic_marker_image()
    stored = storage.store(
        image_bytes,
        subject_id=str(user.id),
        request_id="req_123",
        file_kind="image",
        mime_hint="image/png",
        extension_hint="png",
        size_bucket="tiny",
    )
    client.app.dependency_overrides[get_temp_storage] = lambda: storage
    item = {
        "input_id": "image_real_ocr",
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
    assert "snapshot marker" not in encoded_body.casefold()
    assert "snapshot marker" not in persisted.casefold()
    assert "private-image-bytes" not in encoded_body
    assert "private-image-bytes" not in persisted
    assert stored["file_ref"] not in persisted
    assert stored["temp_scope_id"] not in persisted
    assert "ocr_text" not in encoded_body.casefold()
    assert "ocr_text" not in persisted.casefold()


def _synthetic_marker_image() -> bytes:
    Image = pytest.importorskip("PIL.Image")
    ImageDraw = pytest.importorskip("PIL.ImageDraw")
    ImageFont = pytest.importorskip("PIL.ImageFont")

    output = io.BytesIO()
    image = Image.new("RGB", (720, 180), "white")
    draw = ImageDraw.Draw(image)
    font_path = "C:/Windows/Fonts/arial.ttf"
    font = ImageFont.truetype(font_path, 64) if os.path.exists(font_path) else None
    draw.text((32, 50), "snapshot marker", fill="black", font=font)
    image.save(output, format="PNG")
    return output.getvalue()


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
