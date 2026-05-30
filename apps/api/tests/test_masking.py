from dataclasses import asdict

from app.detectors.pii import Detection, detect_pii
from app.masking.placeholder import apply_placeholders


def test_apply_placeholders_masks_detected_pii_values() -> None:
    text = "Contact member@example.com or 010-1234-5678."

    masked = apply_placeholders(text, detect_pii(text))

    assert masked.text == "Contact [EMAIL_1] or [PHONE_1]."
    assert masked.applied_count == 2
    assert masked.placeholder_counts == {"[EMAIL_1]": 1, "[PHONE_1]": 1}


def test_apply_placeholders_reuses_placeholder_for_repeated_same_value() -> None:
    text = "member@example.com sent mail to member@example.com again."

    masked = apply_placeholders(text, detect_pii(text))

    assert masked.text == "[EMAIL_1] sent mail to [EMAIL_1] again."
    assert masked.placeholder_counts == {"[EMAIL_1]": 2}


def test_apply_placeholders_uses_distinct_placeholders_for_distinct_values() -> None:
    text = "a@test.io and b@test.io"

    masked = apply_placeholders(text, detect_pii(text))

    assert masked.text == "[EMAIL_1] and [EMAIL_2]"
    assert masked.placeholder_counts == {"[EMAIL_1]": 1, "[EMAIL_2]": 1}


def test_apply_placeholders_masks_rrn_and_card_numbers() -> None:
    text = "rrn 900101-1234568 card 4111 1111 1111 1111"

    masked = apply_placeholders(text, detect_pii(text))

    assert masked.text == "rrn [RRN_1] card [CARD_1]"
    assert masked.applied_count == 2


def test_apply_placeholders_does_not_store_raw_values_in_result_metadata() -> None:
    text = "member@example.com / 010-1234-5678 / 900101-1234568 / 4111 1111 1111 1111"
    raw_values = ["member@example.com", "010-1234-5678", "900101-1234568", "4111 1111 1111 1111"]

    masked = apply_placeholders(text, detect_pii(text))
    serialized = asdict(masked)

    assert masked.text == "[EMAIL_1] / [PHONE_1] / [RRN_1] / [CARD_1]"
    assert "placeholder_counts" in serialized
    for raw_value in raw_values:
        assert raw_value not in str(serialized["placeholder_counts"])


def test_apply_placeholders_keeps_longer_overlapping_detection() -> None:
    text = "token-1234567890"
    detections = [
        Detection("SHORT", "SECRET", 0, 5, "SECRET", 5),
        Detection("LONG", "SECRET", 0, len(text), "SECRET", len(text)),
    ]

    masked = apply_placeholders(text, detections)

    assert masked.text == "[SECRET_1]"
    assert masked.applied_count == 1


def test_apply_placeholders_keeps_longer_detection_when_overlap_starts_later() -> None:
    text = "abc-secret-value"
    detections = [
        Detection("SHORT", "SECRET", 0, 6, "SECRET", 6),
        Detection("LONG", "SECRET", 4, len(text), "SECRET", len(text) - 4),
    ]

    masked = apply_placeholders(text, detections)

    assert masked.text == "abc-[SECRET_1]"
    assert masked.applied_count == 1
