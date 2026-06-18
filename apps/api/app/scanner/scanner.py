import hashlib
import re

from app.atoms.models import TextRange
from app.normalization.normalizer import restore_original_range
from app.scanner.models import LexicalRule, LexicalScanRequest, LexicalScanResult, LexicalSignal, ScannerFailure

SCANNER_VERSION = "lexical-signal-scanner-v1"


def _compile(rule: LexicalRule) -> re.Pattern[str]:
    pattern = re.escape(rule.expression) if rule.kind == "keyword" else rule.expression
    flags = 0 if rule.case_sensitive else re.IGNORECASE
    return re.compile(pattern, flags)


def _signal_id(input_id: str, block_id: str, pattern_id: str, start: int, end: int) -> str:
    digest = hashlib.sha256(f"{input_id}:{block_id}:{pattern_id}:{start}:{end}".encode()).hexdigest()[:20]
    return f"sig_{digest}"


def scan_lexical_signals(request: LexicalScanRequest) -> LexicalScanResult:
    signals: list[LexicalSignal] = []
    warnings: list[str] = []
    failures: list[ScannerFailure] = []
    for rule in request.rules:
        try:
            compiled = _compile(rule)
        except re.error:
            warnings.append(f"INVALID_REGEX:{rule.pattern_id}")
            continue
        for block in request.normalized_document.blocks:
            for match in compiled.finditer(block.normalized_text):
                normalized_range = TextRange(start=match.start(), end=match.end())
                original_range = restore_original_range(normalized_range, block.offset_map)
                if original_range is None:
                    failures.append(ScannerFailure(code="OFFSET_MAPPING_FAILED", pattern_id=rule.pattern_id, block_id=block.block_id))
                    continue
                signals.append(
                    LexicalSignal(
                        signal_id=_signal_id(request.normalized_document.input_id, block.block_id, rule.pattern_id, match.start(), match.end()),
                        input_id=request.normalized_document.input_id,
                        block_id=block.block_id,
                        signal_type=rule.signal_type,
                        pattern_id=rule.pattern_id,
                        match_basis=rule.kind,
                        normalized_range=normalized_range,
                        original_range=original_range,
                    )
                )
    status = "partial" if warnings or failures else "ok"
    return LexicalScanResult(
        input_id=request.normalized_document.input_id,
        signals=signals,
        scanner_status=status,
        scanner_version=SCANNER_VERSION,
        warnings=warnings,
        failures=failures,
    )
