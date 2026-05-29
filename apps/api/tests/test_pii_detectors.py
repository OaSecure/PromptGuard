from dataclasses import asdict

import pytest

from app.detectors.pii import detect_email, detect_phone, detect_pii


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("담당자 이메일은 member@example.com 입니다.", ["member@example.com"]),
        ("Contact security.team+alerts@sub.example.co.kr now.", ["security.team+alerts@sub.example.co.kr"]),
        ("두 주소 a@test.io 와 b.user@example.org 확인", ["a@test.io", "b.user@example.org"]),
    ],
)
def test_detect_email_finds_valid_email_addresses(text: str, expected: list[str]) -> None:
    detections = detect_email(text)

    assert [text[item.start : item.end] for item in detections] == expected
    assert all(item.detector_key == "EMAIL" for item in detections)
    assert all(item.placeholder == "EMAIL" for item in detections)


@pytest.mark.parametrize(
    "text",
    [
        "not-an-email@example",
        "example.com",
        "member@@example.com",
        "abc.member@example.com.",
    ],
)
def test_detect_email_ignores_invalid_candidates(text: str) -> None:
    assert detect_email(text) == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("전화번호는 010-1234-5678 입니다.", ["010-1234-5678"]),
        ("대표번호 02-123-4567 / 보조 031-1234-5678", ["02-123-4567", "031-1234-5678"]),
        ("Intl +82 10 1234 5678", ["+82 10 1234 5678"]),
        ("070.1234.5678 로 연락", ["070.1234.5678"]),
    ],
)
def test_detect_phone_finds_korean_phone_numbers(text: str, expected: list[str]) -> None:
    detections = detect_phone(text)

    assert [text[item.start : item.end] for item in detections] == expected
    assert all(item.detector_key == "PHONE" for item in detections)
    assert all(item.placeholder == "PHONE" for item in detections)


@pytest.mark.parametrize(
    "text",
    [
        "123456",
        "010-12-5678",
        "999-9999-9999",
        "계약번호 2026-1234-5678",
    ],
)
def test_detect_phone_ignores_invalid_candidates(text: str) -> None:
    assert detect_phone(text) == []


def test_detect_pii_returns_sorted_email_and_phone_detections() -> None:
    text = "연락처 010-1234-5678, 메일 member@example.com"

    detections = detect_pii(text)

    assert [item.detector_key for item in detections] == ["PHONE", "EMAIL"]


def test_detections_do_not_store_raw_values() -> None:
    text = "member@example.com / 010-1234-5678"
    raw_values = ["member@example.com", "010-1234-5678"]

    serialized = [asdict(item) for item in detect_pii(text)]

    assert serialized
    for item in serialized:
        assert "value" not in item
        assert "raw" not in item
        assert "text" not in item
        assert item["detector_key"] in {"EMAIL", "PHONE"}
        assert item["value_length"] > 0
        for raw_value in raw_values:
            assert raw_value not in str(item)
