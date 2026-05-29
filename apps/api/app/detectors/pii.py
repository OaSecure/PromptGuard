import re
from dataclasses import dataclass


EMAIL_PATTERN = re.compile(
    r"(?<![A-Za-z0-9._%+-])"
    r"[A-Za-z0-9][A-Za-z0-9._%+-]{0,63}"
    r"@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+"
    r"(?![A-Za-z0-9._%+-])"
)

PHONE_PATTERN = re.compile(
    r"(?<!\d)"
    r"(?:"
    r"(?:\+82[-.\s]?(?:10|2|[3-6][1-5]|70)[-.\s]?\d{3,4}[-.\s]?\d{4})"
    r"|(?:0(?:10|2|[3-6][1-5]|70)[-.\s]?\d{3,4}[-.\s]?\d{4})"
    r")"
    r"(?!\d)"
)


@dataclass(frozen=True)
class Detection:
    detector_key: str
    category: str
    start: int
    end: int
    placeholder: str
    value_length: int


def detect_email(text: str) -> list[Detection]:
    return [
        Detection(
            detector_key="EMAIL",
            category="PII",
            start=match.start(),
            end=match.end(),
            placeholder="EMAIL",
            value_length=match.end() - match.start(),
        )
        for match in EMAIL_PATTERN.finditer(text)
    ]


def detect_phone(text: str) -> list[Detection]:
    return [
        Detection(
            detector_key="PHONE",
            category="PII",
            start=match.start(),
            end=match.end(),
            placeholder="PHONE",
            value_length=match.end() - match.start(),
        )
        for match in PHONE_PATTERN.finditer(text)
    ]


def detect_pii(text: str) -> list[Detection]:
    detections = [*detect_email(text), *detect_phone(text)]
    return sorted(detections, key=lambda detection: (detection.start, detection.end, detection.detector_key))
