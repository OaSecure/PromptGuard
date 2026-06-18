from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.atoms.models import TextRange
from app.normalization.models import NormalizedDocument

SeverityHint = Literal["info", "low", "medium", "high", "critical"]
ScannerStatus = Literal["not_started", "completed", "partial", "timeout", "failed"]


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
