from dataclasses import asdict

import pytest

from app.detectors.pii import detect_card, detect_email, detect_phone, detect_pii, detect_rrn


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("email member@example.com here", ["member@example.com"]),
        ("Contact security.team+alerts@sub.example.co.kr now.", ["security.team+alerts@sub.example.co.kr"]),
        ("Sentence punctuation abc.member@example.com.", ["abc.member@example.com"]),
        ("two emails a@test.io and b.user@example.org", ["a@test.io", "b.user@example.org"]),
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
    ],
)
def test_detect_email_ignores_invalid_candidates(text: str) -> None:
    assert detect_email(text) == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("phone 010-1234-5678 here", ["010-1234-5678"]),
        ("office 02-123-4567 / branch 031-1234-5678", ["02-123-4567", "031-1234-5678"]),
        ("Intl +82 10 1234 5678", ["+82 10 1234 5678"]),
        ("070.1234.5678 contact", ["070.1234.5678"]),
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
        "contract 2026-1234-5678",
    ],
)
def test_detect_phone_ignores_invalid_candidates(text: str) -> None:
    assert detect_phone(text) == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("dummy rrn 900101-1234568", ["900101-1234568"]),
        ("space separated 900101 1234568", ["900101 1234568"]),
    ],
)
def test_detect_rrn_finds_checksum_valid_dummy_numbers(text: str, expected: list[str]) -> None:
    detections = detect_rrn(text)

    assert [text[item.start : item.end] for item in detections] == expected
    assert all(item.detector_key == "RRN" for item in detections)
    assert all(item.placeholder == "RRN" for item in detections)


@pytest.mark.parametrize(
    "text",
    [
        "900101-1234567",
        "900101-5234568",
        "123456",
        "order 202605-3012345",
    ],
)
def test_detect_rrn_ignores_invalid_candidates(text: str) -> None:
    assert detect_rrn(text) == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("card 4111 1111 1111 1111", ["4111 1111 1111 1111"]),
        ("hyphen card 5555-5555-5555-4444", ["5555-5555-5555-4444"]),
        ("compact card 378282246310005", ["378282246310005"]),
    ],
)
def test_detect_card_finds_luhn_valid_numbers(text: str, expected: list[str]) -> None:
    detections = detect_card(text)

    assert [text[item.start : item.end] for item in detections] == expected
    assert all(item.detector_key == "CARD" for item in detections)
    assert all(item.placeholder == "CARD" for item in detections)


@pytest.mark.parametrize(
    "text",
    [
        "4111 1111 1111 1112",
        "1234-5678-9012-3456",
        "123456789012",
        "contract 2026-1234-5678",
    ],
)
def test_detect_card_ignores_luhn_invalid_candidates(text: str) -> None:
    assert detect_card(text) == []


def test_detect_pii_returns_sorted_detections() -> None:
    text = "phone 010-1234-5678, email member@example.com, rrn 900101-1234568, card 4111 1111 1111 1111"

    detections = detect_pii(text)

    assert [item.detector_key for item in detections] == ["PHONE", "EMAIL", "RRN", "CARD"]


def test_detections_do_not_store_raw_values() -> None:
    text = "member@example.com / 010-1234-5678 / 900101-1234568 / 4111 1111 1111 1111"
    raw_values = ["member@example.com", "010-1234-5678", "900101-1234568", "4111 1111 1111 1111"]

    serialized = [asdict(item) for item in detect_pii(text)]

    assert serialized
    for item in serialized:
        assert "value" not in item
        assert "raw" not in item
        assert "text" not in item
        assert item["detector_key"] in {"EMAIL", "PHONE", "RRN", "CARD"}
        assert item["value_length"] > 0
        for raw_value in raw_values:
            assert raw_value not in str(item)
