import hashlib
import re
import uuid
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.detectors.pii import Detection, detect_pii
from app.models.filters import FilterRule

RuleAction = Literal["ALLOW", "WARN", "MASK", "BLOCK"]
RuleSeverity = Literal["low", "medium", "high", "critical"]

ACTION_PRIORITY = {"ALLOW": 0, "WARN": 1, "MASK": 2, "BLOCK": 3}
SEVERITY_SCORE = {"low": 25, "medium": 55, "high": 80, "critical": 95}


@dataclass(frozen=True)
class RuleMatch:
    rule_id: uuid.UUID | None
    category: str
    type: str
    source: str
    severity: RuleSeverity
    action: RuleAction
    placeholder: str | None
    confidence: int
    count: int
    reason_code: str
    match_count: int
    safe_evidence: dict[str, Any]
    detections: list[Detection]


BUILT_IN_RULES: list[FilterRule] = [
    FilterRule(
        id=uuid.UUID("00000000-0000-4000-8000-000000000101"),
        origin="built_in",
        kind="detector",
        category="PII",
        label="Email Address",
        description="Detects email address patterns.",
        detector_key="EMAIL",
        placeholder="EMAIL",
        severity="medium",
        action="MASK",
        enabled=True,
        editable_fields={"severity": True, "action": True, "enabled": True},
        version=1,
    ),
    FilterRule(
        id=uuid.UUID("00000000-0000-4000-8000-000000000102"),
        origin="built_in",
        kind="detector",
        category="PII",
        label="Phone Number",
        description="Detects Korean phone number patterns.",
        detector_key="PHONE",
        placeholder="PHONE",
        severity="medium",
        action="MASK",
        enabled=True,
        editable_fields={"severity": True, "action": True, "enabled": True},
        version=1,
    ),
    FilterRule(
        id=uuid.UUID("00000000-0000-4000-8000-000000000103"),
        origin="built_in",
        kind="detector",
        category="PII",
        label="Resident Registration Number",
        description="Detects valid dummy resident registration numbers.",
        detector_key="RRN",
        placeholder="RRN",
        severity="high",
        action="MASK",
        enabled=True,
        editable_fields={"severity": True, "action": True, "enabled": True},
        version=1,
    ),
    FilterRule(
        id=uuid.UUID("00000000-0000-4000-8000-000000000104"),
        origin="built_in",
        kind="detector",
        category="Payment",
        label="Card Number",
        description="Detects Luhn-valid card numbers.",
        detector_key="CARD",
        placeholder="CARD",
        severity="high",
        action="MASK",
        enabled=True,
        editable_fields={"severity": True, "action": True, "enabled": True},
        version=1,
    ),
]


async def load_active_filter_rules(session: AsyncSession) -> list[FilterRule]:
    try:
        result = await session.execute(
            select(FilterRule).where(FilterRule.enabled.is_(True), FilterRule.archived_at.is_(None))
        )
    except Exception:
        return [rule for rule in BUILT_IN_RULES if rule.enabled]

    rules = list(result.scalars().all())
    return rules or [rule for rule in BUILT_IN_RULES if rule.enabled]


def filter_rule_set_version(rules: list[FilterRule]) -> str:
    if not rules:
        return "filter-rules:none"
    pieces = [f"{rule.id}:{rule.version}" for rule in sorted(rules, key=lambda item: str(item.id))]
    digest = hashlib.sha256("|".join(pieces).encode("utf-8")).hexdigest()[:16]
    return f"filter-rules:{digest}"


def score_for_matches(matches: list[RuleMatch]) -> int:
    if not matches:
        return 0
    return min(100, max(SEVERITY_SCORE[match.severity] for match in matches))


def action_for_matches(matches: list[RuleMatch]) -> RuleAction:
    if not matches:
        return "ALLOW"
    return max((match.action for match in matches), key=lambda action: ACTION_PRIORITY[action])


def _reason_code(rule: FilterRule) -> str:
    source = "BUILT_IN" if rule.origin == "built_in" else "CUSTOM"
    return f"{source}_{rule.kind.upper()}_{(rule.detector_key or rule.label).upper().replace(' ', '_')}"


def _built_in_matches(prompt: str, rules: list[FilterRule]) -> list[RuleMatch]:
    detections = detect_pii(prompt)
    grouped: dict[str, list[Detection]] = {}
    for detection in detections:
        grouped.setdefault(detection.detector_key, []).append(detection)

    matches: list[RuleMatch] = []
    for rule in rules:
        if rule.origin != "built_in" or rule.kind != "detector" or not rule.detector_key:
            continue
        rule_detections = grouped.get(rule.detector_key, [])
        if not rule_detections:
            continue
        matches.append(
            RuleMatch(
                rule_id=rule.id,
                category=rule.category,
                type=rule.detector_key,
                source="built_in_detector",
                severity=rule.severity,  # type: ignore[arg-type]
                action=rule.action,  # type: ignore[arg-type]
                placeholder=rule.placeholder,
                confidence=100,
                count=len(rule_detections),
                reason_code=_reason_code(rule),
                match_count=len(rule_detections),
                safe_evidence={"value_lengths": [item.value_length for item in rule_detections]},
                detections=rule_detections,
            )
        )
    return matches


def _custom_keyword_match(prompt: str, rule: FilterRule) -> RuleMatch | None:
    if not rule.keyword:
        return None
    detections: list[Detection] = []
    prompt_folded = prompt.casefold()
    keyword_folded = rule.keyword.casefold()
    start = 0
    while True:
        index = prompt_folded.find(keyword_folded, start)
        if index < 0:
            break
        end = index + len(rule.keyword)
        detections.append(
            Detection(
                detector_key=rule.placeholder or "CUSTOM_KEYWORD",
                category=rule.category,
                start=index,
                end=end,
                placeholder=rule.placeholder or "CUSTOM_KEYWORD",
                value_length=end - index,
            )
        )
        start = end
    if not detections:
        return None
    return RuleMatch(
        rule_id=rule.id,
        category=rule.category,
        type=rule.placeholder or "CUSTOM_KEYWORD",
        source="custom_keyword",
        severity=rule.severity,  # type: ignore[arg-type]
        action=rule.action,  # type: ignore[arg-type]
        placeholder=rule.placeholder,
        confidence=90,
        count=len(detections),
        reason_code=_reason_code(rule),
        match_count=len(detections),
        safe_evidence={"value_lengths": [item.value_length for item in detections]},
        detections=detections,
    )


def _custom_regex_match(prompt: str, rule: FilterRule) -> RuleMatch | None:
    if not rule.pattern:
        return None
    compiled = re.compile(rule.pattern)
    detections = [
        Detection(
            detector_key=rule.placeholder or "CUSTOM_REGEX",
            category=rule.category,
            start=match.start(),
            end=match.end(),
            placeholder=rule.placeholder or "CUSTOM_REGEX",
            value_length=match.end() - match.start(),
        )
        for match in compiled.finditer(prompt)
    ]
    if not detections:
        return None
    return RuleMatch(
        rule_id=rule.id,
        category=rule.category,
        type=rule.placeholder or "CUSTOM_REGEX",
        source="custom_regex",
        severity=rule.severity,  # type: ignore[arg-type]
        action=rule.action,  # type: ignore[arg-type]
        placeholder=rule.placeholder,
        confidence=90,
        count=len(detections),
        reason_code=_reason_code(rule),
        match_count=len(detections),
        safe_evidence={"value_lengths": [item.value_length for item in detections]},
        detections=detections,
    )


def _context_rule_match(prompt: str, rule: FilterRule) -> RuleMatch | None:
    config = rule.config_json or {}
    groups = config.get("keyword_groups", {})
    if not isinstance(groups, dict):
        return None
    min_count = int(config.get("min_condition_count", 1))
    matched_terms = 0
    for terms in groups.values():
        if isinstance(terms, list):
            matched_terms += sum(1 for term in terms if isinstance(term, str) and term and term.casefold() in prompt.casefold())
    if matched_terms < min_count:
        return None
    return RuleMatch(
        rule_id=rule.id,
        category=rule.category,
        type=rule.placeholder or "CONTEXT_RULE",
        source="custom_context_rule",
        severity=rule.severity,  # type: ignore[arg-type]
        action=rule.action,  # type: ignore[arg-type]
        placeholder=rule.placeholder,
        confidence=80,
        count=matched_terms,
        reason_code=_reason_code(rule),
        match_count=matched_terms,
        safe_evidence={"matched_condition_count": matched_terms},
        detections=[],
    )


def evaluate_filter_rules(prompt: str, rules: list[FilterRule]) -> list[RuleMatch]:
    rules = [rule for rule in rules if rule.enabled and rule.archived_at is None]
    matches = _built_in_matches(prompt, rules)
    for rule in rules:
        if rule.origin != "custom":
            continue
        if rule.kind == "keyword":
            match = _custom_keyword_match(prompt, rule)
        elif rule.kind == "regex":
            match = _custom_regex_match(prompt, rule)
        elif rule.kind == "context_rule":
            match = _context_rule_match(prompt, rule)
        else:
            match = None
        if match is not None:
            matches.append(match)
    return matches


def detections_for_masking(matches: list[RuleMatch]) -> list[Detection]:
    detections: list[Detection] = []
    for match in matches:
        if match.action == "MASK":
            detections.extend(match.detections)
    return detections
