import re
from dataclasses import dataclass


EMAIL_PATTERN = re.compile(
    r"(?<![A-Za-z0-9._%+-])"
    r"[A-Za-z0-9][A-Za-z0-9._%+-]{0,63}"
    r"@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+"
    r"(?![A-Za-z0-9_%+-])"
)

PHONE_PATTERN = re.compile(
    r"(?<!\d)"
    r"(?:"
    r"(?:\+82[-.\s]?(?:10|2|[3-6][1-5]|70)[-.\s]?\d{3,4}[-.\s]?\d{4})"
    r"|(?:0(?:10|2|[3-6][1-5]|70)[-.\s]?\d{3,4}[-.\s]?\d{4})"
    r")"
    r"(?!\d)"
)

RRN_PATTERN = re.compile(r"(?<!\d)(\d{6})[-\s]?([1-4]\d{6})(?!\d)")

CARD_PATTERN = re.compile(
    r"(?<!\d)"
    r"(?:\d[ -]?){13,19}"
    r"(?!\d)"
)

RRN_CHECKSUM_WEIGHTS = [2, 3, 4, 5, 6, 7, 8, 9, 2, 3, 4, 5]


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


def digits_only(value: str) -> str:
    return "".join(character for character in value if character.isdigit())


def is_valid_rrn(value: str) -> bool:
    digits = digits_only(value)
    if len(digits) != 13:
        return False

    checksum = (11 - sum(int(digit) * weight for digit, weight in zip(digits[:12], RRN_CHECKSUM_WEIGHTS)) % 11) % 10
    return checksum == int(digits[-1])


def is_valid_luhn(value: str) -> bool:
    digits = digits_only(value)
    if not 13 <= len(digits) <= 19:
        return False

    total = 0
    parity = len(digits) % 2
    for index, character in enumerate(digits):
        number = int(character)
        if index % 2 == parity:
            number *= 2
            if number > 9:
                number -= 9
        total += number

    return total % 10 == 0


def detect_rrn(text: str) -> list[Detection]:
    return [
        Detection(
            detector_key="RRN",
            category="PII",
            start=match.start(),
            end=match.end(),
            placeholder="RRN",
            value_length=match.end() - match.start(),
        )
        for match in RRN_PATTERN.finditer(text)
        if is_valid_rrn(match.group(0))
    ]


def detect_card(text: str) -> list[Detection]:
    return [
        Detection(
            detector_key="CARD",
            category="PAYMENT",
            start=match.start(),
            end=match.end(),
            placeholder="CARD",
            value_length=match.end() - match.start(),
        )
        for match in CARD_PATTERN.finditer(text)
        if is_valid_luhn(match.group(0))
    ]


def detect_pii(text: str) -> list[Detection]:
    detections = [*detect_email(text), *detect_phone(text), *detect_rrn(text), *detect_card(text)]
    return sorted(detections, key=lambda detection: (detection.start, detection.end, detection.detector_key))
