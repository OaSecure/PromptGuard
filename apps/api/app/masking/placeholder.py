from dataclasses import dataclass

from app.detectors.pii import Detection


@dataclass(frozen=True)
class MaskedText:
    text: str
    placeholder_counts: dict[str, int]
    applied_count: int


def normalized_sensitive_value(value: str) -> str:
    return " ".join(value.split())


def placeholder_prefix(detection: Detection) -> str:
    return detection.placeholder or detection.detector_key


def non_overlapping_detections(detections: list[Detection]) -> list[Detection]:
    ordered = sorted(detections, key=lambda item: (-(item.end - item.start), item.start, item.detector_key))
    accepted: list[Detection] = []

    for detection in ordered:
        if detection.start < 0 or detection.end <= detection.start:
            continue
        if any(detection.start < item.end and item.start < detection.end for item in accepted):
            continue
        accepted.append(detection)

    return sorted(accepted, key=lambda item: item.start)


def build_placeholder(
    detection: Detection,
    raw_value: str,
    assigned: dict[tuple[str, str], str],
    counters: dict[str, int],
) -> str:
    prefix = placeholder_prefix(detection)
    key = (prefix, normalized_sensitive_value(raw_value))
    if key in assigned:
        return assigned[key]

    counters[prefix] = counters.get(prefix, 0) + 1
    placeholder = f"[{prefix}_{counters[prefix]}]"
    assigned[key] = placeholder
    return placeholder


def apply_placeholders(text: str, detections: list[Detection]) -> MaskedText:
    accepted = non_overlapping_detections(detections)
    assigned: dict[tuple[str, str], str] = {}
    counters: dict[str, int] = {}
    replacements: list[tuple[int, int, str, str]] = []
    placeholder_counts: dict[str, int] = {}

    for detection in accepted:
        raw_value = text[detection.start : detection.end]
        placeholder = build_placeholder(detection, raw_value, assigned, counters)
        replacements.append((detection.start, detection.end, placeholder, raw_value))
        placeholder_counts[placeholder] = placeholder_counts.get(placeholder, 0) + 1

    masked = text
    for start, end, placeholder, _raw_value in reversed(replacements):
        masked = f"{masked[:start]}{placeholder}{masked[end:]}"

    return MaskedText(
        text=masked,
        placeholder_counts=placeholder_counts,
        applied_count=len(replacements),
    )
