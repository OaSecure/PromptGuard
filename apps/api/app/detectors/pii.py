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

BANK_ACCOUNT_PATTERN = re.compile(
    r"(?<!\d)"
    r"(?:\d{2,6}[-\s]?){2,4}\d{2,6}"
    r"(?!\d)"
)

BANK_CONTEXT_PATTERN = re.compile(r"(?:계좌|은행|국민|신한|우리|하나|농협|기업|카카오|토스|부산|대구|광주|전북|경남|수협|새마을|우체국)")

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
    bank_accounts = detect_korean_bank_account(text)
    rrns = detect_rrn(text)
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
        and not any(_ranges_overlap(match.start(), match.end(), account.start, account.end) for account in bank_accounts)
        and not any(_ranges_overlap(match.start(), match.end(), rrn.start, rrn.end) for rrn in rrns)
    ]


def detect_korean_bank_account(text: str) -> list[Detection]:
    detections: list[Detection] = []
    for match in BANK_ACCOUNT_PATTERN.finditer(text):
        digits = digits_only(match.group(0))
        if not 10 <= len(digits) <= 16:
            continue
        window_start = max(0, match.start() - 24)
        window_end = min(len(text), match.end() + 12)
        if not BANK_CONTEXT_PATTERN.search(text[window_start:window_end]):
            continue
        detections.append(
            Detection(
                detector_key="BANK_ACCOUNT",
                category="Payment",
                start=match.start(),
                end=match.end(),
                placeholder="BANK_ACCOUNT",
                value_length=match.end() - match.start(),
            )
        )
    return detections


def detect_pii(text: str) -> list[Detection]:
    detections = [
        *detect_email(text),
        *detect_phone(text),
        *detect_rrn(text),
        *detect_korean_bank_account(text),
        *detect_card(text),
    ]
    return sorted(detections, key=lambda detection: (detection.start, detection.end, detection.detector_key))


def _ranges_overlap(left_start: int, left_end: int, right_start: int, right_end: int) -> bool:
    return left_start < right_end and right_start < left_end
