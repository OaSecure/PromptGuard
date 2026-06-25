import hashlib
import uuid
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.atoms.models import ParsedBlock, ParsedDocument
from app.detectors.pii import Detection, detect_pii
from app.models.filters import FilterRule
from app.normalization import NormalizerRequest, normalize_document
from app.scanner import LexicalRule, LexicalScanRequest, scan_lexical_signals

RuleAction = Literal["ALLOW", "WARN", "MASK", "BLOCK"]
RuleSeverity = Literal["low", "medium", "high", "critical"]

ACTION_PRIORITY = {"ALLOW": 0, "WARN": 1, "MASK": 2, "BLOCK": 3}
SEVERITY_SCORE = {"low": 25, "medium": 55, "high": 80, "critical": 95}


@dataclass(frozen=True)
class RuleMatch:
    rule_id: str
    detector_id: str | None
    category: str
    type: str
    source: str
    severity: RuleSeverity
    action: RuleAction
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
    FilterRule(
        id=uuid.UUID("00000000-0000-4000-8000-000000000105"),
        origin="built_in",
        kind="detector",
        category="Payment",
        label="Korean Bank Account",
        description="Detects Korean bank account numbers near bank/account context.",
        detector_key="BANK_ACCOUNT",
        placeholder="BANK_ACCOUNT",
        severity="high",
        action="MASK",
        enabled=True,
        editable_fields={"severity": True, "action": True, "enabled": True},
        version=1,
    ),
    FilterRule(
        id=uuid.UUID("00000000-0000-4000-8000-000000000106"),
        origin="built_in",
        kind="regex",
        category="Secret",
        label="Public API Key or Token",
        description="Detects exposed API keys, access tokens, webhook tokens, and private-key headers.",
        pattern=(
            r"(?i)(?:"
            r"sk-[A-Za-z0-9_-]{20,}|"
            r"gh[pousr]_[A-Za-z0-9_]{20,}|"
            r"github_pat_[A-Za-z0-9_]{22,}|"
            r"xox[baprs]-[A-Za-z0-9-]{20,}|"
            r"AKIA[0-9A-Z]{16}|"
            r"AIza[0-9A-Za-z_-]{35}|"
            r"SG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}|"
            r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----|"
            r"(?:api[_-]?key|access[_-]?token|secret[_-]?key|client[_-]?secret|bearer)\s*[:=]\s*['\"]?[A-Za-z0-9._~+/=-]{16,}"
            r")"
        ),
        placeholder="API_SECRET",
        severity="critical",
        action="BLOCK",
        enabled=True,
        editable_fields={"severity": True, "action": True, "enabled": True},
        version=1,
    ),
    FilterRule(
        id=uuid.UUID("00000000-0000-4000-8000-000000000201"),
        origin="built_in",
        kind="detector",
        category="Context Risk",
        label="계정/인증 정보 맥락",
        description="Controls ML-confirmed secret or credential context.",
        detector_key="SECRET_CREDENTIAL_CONTEXT",
        placeholder="SECRET_CREDENTIAL_CONTEXT",
        severity="critical",
        action="BLOCK",
        enabled=True,
        editable_fields={"severity": True, "action": True, "enabled": True},
        version=1,
    ),
    FilterRule(
        id=uuid.UUID("00000000-0000-4000-8000-000000000202"),
        origin="built_in",
        kind="detector",
        category="Context Risk",
        label="개인정보 맥락",
        description="Controls ML-confirmed personal data context.",
        detector_key="PERSONAL_DATA_CONTEXT",
        placeholder="PERSONAL_DATA_CONTEXT",
        severity="high",
        action="WARN",
        enabled=True,
        editable_fields={"severity": True, "action": True, "enabled": True},
        version=1,
    ),
    FilterRule(
        id=uuid.UUID("00000000-0000-4000-8000-000000000203"),
        origin="built_in",
        kind="detector",
        category="Context Risk",
        label="금융 식별 정보 맥락",
        description="Controls ML-confirmed financial identifier context.",
        detector_key="FINANCIAL_IDENTIFIER_CONTEXT",
        placeholder="FINANCIAL_IDENTIFIER_CONTEXT",
        severity="high",
        action="WARN",
        enabled=True,
        editable_fields={"severity": True, "action": True, "enabled": True},
        version=1,
    ),
    FilterRule(
        id=uuid.UUID("00000000-0000-4000-8000-000000000204"),
        origin="built_in",
        kind="detector",
        category="Context Risk",
        label="기밀 비즈니스 정보 맥락",
        description="Controls ML-confirmed confidential business context.",
        detector_key="CONFIDENTIAL_BUSINESS_CONTEXT",
        placeholder="CONFIDENTIAL_BUSINESS_CONTEXT",
        severity="critical",
        action="BLOCK",
        enabled=True,
        editable_fields={"severity": True, "action": True, "enabled": True},
        version=1,
    ),
    FilterRule(
        id=uuid.UUID("00000000-0000-4000-8000-000000000205"),
        origin="built_in",
        kind="detector",
        category="Context Risk",
        label="전용 기술 정보 맥락",
        description="Controls ML-confirmed proprietary technical context.",
        detector_key="PROPRIETARY_TECHNICAL_CONTEXT",
        placeholder="PROPRIETARY_TECHNICAL_CONTEXT",
        severity="critical",
        action="BLOCK",
        enabled=True,
        editable_fields={"severity": True, "action": True, "enabled": True},
        version=1,
    ),
    FilterRule(
        id=uuid.UUID("00000000-0000-4000-8000-000000000206"),
        origin="built_in",
        kind="detector",
        category="Context Risk",
        label="보안 통제 정보 맥락",
        description="Controls ML-confirmed security control context.",
        detector_key="SECURITY_CONTROL_CONTEXT",
        placeholder="SECURITY_CONTROL_CONTEXT",
        severity="critical",
        action="BLOCK",
        enabled=True,
        editable_fields={"severity": True, "action": True, "enabled": True},
        version=1,
    ),
    FilterRule(
        id=uuid.UUID("00000000-0000-4000-8000-000000000207"),
        origin="built_in",
        kind="detector",
        category="Context Risk",
        label="내부 운영 정보 맥락",
        description="Controls ML-confirmed internal operation context.",
        detector_key="INTERNAL_OPERATION_CONTEXT",
        placeholder="INTERNAL_OPERATION_CONTEXT",
        severity="high",
        action="WARN",
        enabled=True,
        editable_fields={"severity": True, "action": True, "enabled": True},
        version=1,
    ),
    FilterRule(
        id=uuid.UUID("00000000-0000-4000-8000-000000000208"),
        origin="built_in",
        kind="detector",
        category="Context Risk",
        label="대량 민감 기록 맥락",
        description="Controls ML-confirmed bulk sensitive record context.",
        detector_key="BULK_SENSITIVE_RECORD_CONTEXT",
        placeholder="BULK_SENSITIVE_RECORD_CONTEXT",
        severity="critical",
        action="BLOCK",
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

    return _merge_built_in_and_stored_rules(list(result.scalars().all()))


async def load_manageable_filter_rules(session: AsyncSession) -> list[FilterRule]:
    try:
        result = await session.execute(select(FilterRule).where(FilterRule.archived_at.is_(None)))
    except Exception:
        return [rule for rule in BUILT_IN_RULES if rule.archived_at is None]

    return _merge_built_in_and_stored_rules(list(result.scalars().all()), active_only=False)


def _merge_built_in_and_stored_rules(stored_rules: list[FilterRule], *, active_only: bool = True) -> list[FilterRule]:
    active_stored = _active_rules(stored_rules)
    stored_built_in_by_key = _stored_built_in_overrides(active_stored)
    merged = [_rule_with_override(rule, stored_built_in_by_key) for rule in BUILT_IN_RULES]
    merged.extend(_custom_rules(active_stored))
    if active_only:
        return [rule for rule in merged if rule.enabled]
    return merged


def _active_rules(rules: list[FilterRule]) -> list[FilterRule]:
    return [rule for rule in rules if rule.archived_at is None]


def _stored_built_in_overrides(rules: list[FilterRule]) -> dict[str, FilterRule]:
    overrides: dict[str, FilterRule] = {}
    for rule in rules:
        key = _built_in_override_key(rule)
        if key is not None:
            overrides[key] = rule
    return overrides


def _custom_rules(rules: list[FilterRule]) -> list[FilterRule]:
    return [rule for rule in rules if rule.origin != "built_in"]


def _rule_with_override(rule: FilterRule, overrides: dict[str, FilterRule]) -> FilterRule:
    key = _built_in_override_key(rule)
    if key is None:
        return rule
    return overrides.get(key, rule)


def _built_in_override_key(rule: FilterRule) -> str | None:
    if rule.origin != "built_in":
        return None
    if rule.detector_key:
        return f"detector:{rule.detector_key}"
    return f"id:{rule.id}"


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
                rule_id=str(rule.id),
                detector_id=rule.detector_key,
                category=rule.category,
                type=rule.detector_key,
                source="built_in_detector",
                severity=rule.severity,  # type: ignore[arg-type]
                action=rule.action,  # type: ignore[arg-type]
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
    detections = _lexical_detections(prompt, rule, "keyword", rule.keyword)
    if not detections:
        return None
    return RuleMatch(
        rule_id=str(rule.id),
        detector_id=rule.placeholder or "CUSTOM_KEYWORD",
        category=rule.category,
        type=rule.placeholder or "CUSTOM_KEYWORD",
        source="custom_keyword",
        severity=rule.severity,  # type: ignore[arg-type]
        action=rule.action,  # type: ignore[arg-type]
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
    detections = _lexical_detections(prompt, rule, "regex", rule.pattern)
    if not detections:
        return None
    return RuleMatch(
        rule_id=str(rule.id),
        detector_id=rule.placeholder or "CUSTOM_REGEX",
        category=rule.category,
        type=rule.placeholder or "CUSTOM_REGEX",
        source="custom_regex",
        severity=rule.severity,  # type: ignore[arg-type]
        action=rule.action,  # type: ignore[arg-type]
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
    matched_pattern_ids: list[str] = []
    matched_group_ids: set[str] = set()
    for group_id, terms in groups.items():
        safe_group_id = f"group:{hashlib.sha256(str(group_id).encode()).hexdigest()[:12]}"
        if isinstance(terms, list):
            for index, term in enumerate(terms):
                if isinstance(term, str) and term:
                    pattern_id = f"rule:{rule.id}:{safe_group_id}:pattern:{index}"
                    lexical_rule = LexicalRule(
                        pattern_id=pattern_id,
                        kind="keyword",
                        expression=term,
                        signal_type="CONTEXT",
                    )
                    if _scan(prompt, lexical_rule):
                        matched_pattern_ids.append(pattern_id)
                        matched_group_ids.add(safe_group_id)
    matched_terms = len(matched_pattern_ids)
    if matched_terms < min_count:
        return None
    return RuleMatch(
        rule_id=str(rule.id),
        detector_id=rule.placeholder or "CONTEXT_RULE",
        category=rule.category,
        type=rule.placeholder or "CONTEXT_RULE",
        source="custom_context_rule",
        severity=rule.severity,  # type: ignore[arg-type]
        action=rule.action,  # type: ignore[arg-type]
        confidence=80,
        count=matched_terms,
        reason_code=_reason_code(rule),
        match_count=matched_terms,
        safe_evidence={
            "matched_condition_count": matched_terms,
            "matched_group_ids": sorted(matched_group_ids),
            "matched_pattern_ids": sorted(matched_pattern_ids),
        },
        detections=[],
    )


def _scan(prompt: str, lexical_rule: LexicalRule) -> list:
    document = ParsedDocument(
        input_id="legacy-input",
        blocks=[ParsedBlock(block_id="legacy-block", input_id="legacy-input", text=prompt)],
    )
    normalized = normalize_document(NormalizerRequest(document=document))
    return scan_lexical_signals(LexicalScanRequest(normalized_document=normalized, rules=[lexical_rule])).signals


def _lexical_detections(
    prompt: str,
    rule: FilterRule,
    kind: Literal["keyword", "regex"],
    expression: str,
) -> list[Detection]:
    detector_key = rule.placeholder or ("CUSTOM_KEYWORD" if kind == "keyword" else "CUSTOM_REGEX")
    lexical_rule = LexicalRule(
        pattern_id=f"rule:{rule.id}", kind=kind, expression=expression, signal_type=detector_key
    )
    return [
        Detection(
            detector_key=detector_key,
            category=rule.category,
            start=signal.original_range.start,
            end=signal.original_range.end,
            placeholder=detector_key,
            value_length=signal.original_range.end - signal.original_range.start,
        )
        for signal in _scan(prompt, lexical_rule)
    ]


def evaluate_filter_rules(prompt: str, rules: list[FilterRule]) -> list[RuleMatch]:
    rules = [rule for rule in rules if rule.enabled and rule.archived_at is None]
    matches = _built_in_matches(prompt, rules)
    for rule in rules:
        if rule.origin not in {"custom", "built_in"}:
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
