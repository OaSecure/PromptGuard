from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.atoms.models import TextRange
from app.normalization.models import NormalizedDocument

SeverityHint = Literal["info", "low", "medium", "high", "critical"]
ScannerStatus = Literal["not_started", "completed", "partial", "timeout", "failed"]
FORBIDDEN_SIGNAL_METADATA_KEYS = frozenset(
    {
        "raw_value",
        "matched_value",
        "value",
        "action",
        "recommended_action",
        "reason_code",
        "user_message",
        "user_notice",
        "confidence_hint",
    }
)


class LexicalRule(BaseModel):
    pattern_id: str = Field(min_length=1, max_length=80)
    kind: Literal["keyword", "regex"]
    expression: str = Field(min_length=1, max_length=2048)
    signal_type: str = Field(min_length=1, max_length=80)
    case_sensitive: bool = False


class LexicalScanRequest(BaseModel):
    normalized_document: NormalizedDocument
    rules: list[LexicalRule]


class LexicalSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_id: str
    input_id: str
    block_id: str
    signal_type: str
    pattern_id: str
    match_basis: Literal["keyword", "regex"]
    deterministic: bool = True
    normalized_range: TextRange
    original_range: TextRange
    severity_hint: SeverityHint | None = None
    value_fingerprint: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def reject_raw_or_policy_metadata(cls, value: dict[str, str]) -> dict[str, str]:
        forbidden = FORBIDDEN_SIGNAL_METADATA_KEYS.intersection(value)
        if forbidden:
            raise ValueError(f"forbidden lexical signal metadata keys: {', '.join(sorted(forbidden))}")
        return value


class ScannerFailure(BaseModel):
    code: str
    pattern_id: str | None = None
    block_id: str | None = None


class LexicalScanResult(BaseModel):
    input_id: str
    signals: list[LexicalSignal]
    scanner_status: ScannerStatus
    scanner_version: str
    warnings: list[str] = Field(default_factory=list)
    failures: list[ScannerFailure] = Field(default_factory=list)
