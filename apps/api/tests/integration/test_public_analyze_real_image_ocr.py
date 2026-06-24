import base64
import contextlib
import io
import json
import os
import sys
import tempfile
from collections.abc import Iterator
from urllib.request import urlopen
from uuid import UUID

import pytest
from app.infrastructure.temp_storage import EncryptedTemporaryFileStorage
from app.models.filters import FilterRule
from app.routes import analyze as analyze_route
from app.routes.temp_files import get_temp_storage

from tests.test_analyze import _analyze_payload, _bearer_header, _client, _user

WEB_IMAGE_FIXTURE_URL = "https://jeroen.github.io/images/testocr.png"
WEB_IMAGE_EXPECTED_KEYWORD = "quick brown dog"


@pytest.mark.skipif(
    os.getenv("PROMPTGUARD_RUN_REAL_API_OCR_TESTS") != "1",
    reason="real API OCR integration is opt-in",
)
@pytest.mark.filterwarnings("ignore:No ccache found.*:UserWarning")
def test_public_analyze_image_file_reference_uses_real_paddleocr_without_raw_persistence(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTGUARD_ML_INFERENCE_QUEUE_TIMEOUT_MS", "120000")
    analyze_route.get_settings.cache_clear()
    user = _user()
    client, session = _client(user, rules=[_keyword_rule("BLOCK")])
    storage = EncryptedTemporaryFileStorage(tmp_path, base64.b64encode(b"K" * 32).decode(), 900)
    image_bytes = _download_web_fixture(WEB_IMAGE_FIXTURE_URL, max_bytes=1_000_000)
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
    assert body["action"] == "Block"
    assert body["input_results"][0]["content_scanned"] is True
    assert body["input_results"][0]["decision_basis"] == "detection"
    assert body["detections"][0]["kind"] == "file_reference"
    assert body["detections"][0]["action"] == "Block"
    assert body["detections"][0]["type"] == "WEB_IMAGE_OCR_MARKER"
    assert body["detections"][0]["placeholder"] == "WEB_IMAGE_OCR_MARKER"
    assert body["detections"][0]["reason_code"] == "CUSTOM_KEYWORD_WEB_IMAGE_OCR_MARKER"
    assert WEB_IMAGE_EXPECTED_KEYWORD not in encoded_body.casefold()
    assert WEB_IMAGE_EXPECTED_KEYWORD not in persisted.casefold()
    assert "private-image-bytes" not in encoded_body
    assert "private-image-bytes" not in persisted
    assert stored["file_ref"] not in persisted
    assert stored["temp_scope_id"] not in persisted
    assert "ocr_text" not in encoded_body.casefold()
    assert "ocr_text" not in persisted.casefold()


def _keyword_rule(action: str) -> FilterRule:
    return FilterRule(
        id=UUID("21000000-0000-0000-0000-000000000001"),
        origin="custom",
        kind="keyword",
        category="Custom",
        label="Web image OCR marker",
        keyword=WEB_IMAGE_EXPECTED_KEYWORD,
        placeholder="WEB_IMAGE_OCR_MARKER",
        severity="high",
        action=action,
        enabled=True,
        editable_fields={"enabled": True},
        version=1,
    )


def _download_web_fixture(url: str, *, max_bytes: int) -> bytes:
    with urlopen(url, timeout=30) as response:
        content = response.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise AssertionError("web OCR fixture exceeded test byte limit")
    return content


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
